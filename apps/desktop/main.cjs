const { app, BrowserWindow } = require('electron');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const path = require('node:path');
const readline = require('node:readline');
const fs = require('node:fs');
const root = path.resolve(__dirname, '../..');
const smoke = process.argv.includes('--smoke');
if (smoke) console.log(JSON.stringify({ event: 'desktop_start', electron: process.versions.electron }));
let service;
let window;
let stopping = false;
function stopService() {
  stopping = true;
  if (service && service.exitCode === null) {
    service.kill('SIGTERM');
    setTimeout(() => { if (service.exitCode === null) service.kill('SIGKILL'); }, 2000).unref();
  }
}
function fail(error) { console.error(error.message || error); stopService(); app.exit(1); }
app.whenReady().then(() => {
  if (smoke) console.log(JSON.stringify({ event: 'electron_ready' }));
  const token = randomBytes(32).toString('hex');
  service = spawn(path.join(root, '.venv/bin/python'), ['-m', 'urdftools', 'serve'], {
    cwd: root, env: { PATH: process.env.PATH, URDFTOOLS_SESSION_TOKEN: token }, stdio: ['ignore', 'pipe', 'pipe']
  });
  const startup = setTimeout(() => fail('Service startup timeout'), 15000);
  service.on('error', fail);
  service.on('exit', code => { if (!stopping) fail(`Service exited: ${code}`); });
  service.stderr.on('data', data => process.stderr.write(data));
  readline.createInterface({ input: service.stdout }).on('line', async line => {
    try {
      const event = JSON.parse(line);
      if (event.event !== 'listening' || window) return;
      const health = await fetch(`http://127.0.0.1:${event.port}/v1/health`, { headers: { Authorization: `Bearer ${token}` } });
      if (!health.ok) throw new Error('Service health failed');
      clearTimeout(startup);
      window = new BrowserWindow({ width: 1200, height: 800, show: !smoke, webPreferences: {
        offscreen: smoke,
        preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false
      }});
      window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
      window.webContents.on('will-navigate', event => event.preventDefault());
      await window.loadFile(path.join(root, 'dist/web/index.html'));
      if (smoke) {
        await window.webContents.executeJavaScript(`new Promise((resolve, reject) => {
          const until = Date.now() + 5000;
          function check() {
            if (document.querySelector('h1')) return resolve(true);
            if (Date.now() > until) return reject(new Error('React mount timeout'));
            setTimeout(check, 20);
          } check();
        })`);
        const title = await window.webContents.executeJavaScript('document.querySelector("h1").textContent');
        if (title !== '查看') throw new Error('Renderer did not mount');
        const isolated = await window.webContents.executeJavaScript(`typeof require === 'undefined' && window.urdftools.version === '0.1.0'`);
        if (!isolated) throw new Error('Renderer isolation/preload failed');
        await window.webContents.executeJavaScript(`document.querySelectorAll('nav button')[3].click()`);
        await new Promise(resolve => setTimeout(resolve, 100));
        const selected = await window.webContents.executeJavaScript(`document.querySelector('h1').textContent`);
        if (selected !== '评估') throw new Error('React workspace interaction failed');
        const image = await window.webContents.capturePage();
        const size = image.getSize();
        if (size.width < 100 || size.height < 100 || image.isEmpty()) throw new Error('Renderer capture empty');
        if (process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR) {
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'desktop.png'), image.toPNG());
        }
        console.log(JSON.stringify({ event: 'desktop_smoke', rendered: true, initial: title,
          selected, isolated, sandbox: window.webContents.getLastWebPreferences().sandbox,
          electron: process.versions.electron, capture: size }));
        app.quit();
      }
    } catch (error) { fail(error); }
  });
}).catch(fail);
app.on('window-all-closed', () => app.quit());
app.on('will-quit', stopService);
