const { app, BrowserWindow, ipcMain, dialog, protocol } = require('electron');
const { spawn } = require('node:child_process');
const { randomBytes, createHash } = require('node:crypto');
const path = require('node:path');
const readline = require('node:readline');
const fs = require('node:fs');
protocol.registerSchemesAsPrivileged([{ scheme: 'urdftools', privileges: {
  standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true
} }]);
const root = path.resolve(__dirname, '../..');
const mimeTypes = { '.urdf': 'application/xml', '.obj': 'text/plain; charset=utf-8',
  '.stl': 'model/stl', '.dae': 'model/vnd.collada+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.bmp': 'image/bmp' };
function setupAssetProtocol() {
  protocol.handle('urdftools', async request => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'asset' || request.method !== 'GET') throw new Error('invalid route');
      const parts = decodeURIComponent(url.pathname).split('/').slice(1);
      const [operation, container, ...relativeParts] = parts;
      if (!/^[0-9a-f-]{36}$/.test(operation) || container !== 'bundle' || relativeParts.length === 0) throw new Error('invalid path');
      const relative = relativeParts.join('/');
      const base = path.join(app.getPath('userData'), 'imports', operation);
      const record = JSON.parse(await fs.promises.readFile(path.join(base, 'report.json'), 'utf-8'));
      if (record.operation_id !== operation) throw new Error('operation mismatch');
      const asset = record.assets.find(a => a.path === relative);
      if (!asset) throw new Error('unlisted asset');
      const fullPath = path.resolve(base, 'bundle', relative);
      if (!fullPath.startsWith(path.resolve(base, 'bundle') + path.sep)) throw new Error('path escape');
      const content = await fs.promises.readFile(fullPath);
      if (content.byteLength !== asset.size ||
          createHash('sha256').update(content).digest('hex') !== asset.sha256) throw new Error('asset changed');
      return new Response(content, { status: 200, headers: {
        'Content-Type': mimeTypes[path.extname(relative).toLowerCase()] || 'application/octet-stream',
        'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'
      } });
    } catch {
      return new Response('Resource not available', { status: 404, headers: { 'Access-Control-Allow-Origin': '*' } });
    }
  });
}
const smoke = process.argv.includes('--smoke');
if (smoke) console.log(JSON.stringify({ event: 'desktop_start', electron: process.versions.electron }));
let service;
let window;
let stopping = false;
let importBusy = false;
let importWorker;
function importRequest(request) {
  if (importBusy) return Promise.reject(new Error('已有导入正在进行'));
  importBusy = true;
  return new Promise((resolve, reject) => {
    const worker = spawn(path.join(root, '.venv/bin/python'),
      ['-m', 'urdftools.importers', path.join(app.getPath('userData'), 'imports')],
      { cwd: root, env: { PATH: process.env.PATH, PYTHONPATH: path.join(root, 'python') }, stdio: ['pipe', 'pipe', 'pipe'] });
    importWorker = worker;
    let output = ''; let errors = '';
    worker.stdin.on('error', () => {});
    const deadline = setTimeout(() => worker.kill('SIGKILL'), 120000);
    worker.stdout.on('data', data => { output += data; if (output.length > 32 * 1024 * 1024) worker.kill('SIGKILL'); });
    worker.stderr.on('data', data => { errors = (errors + data).slice(-4096); });
    worker.on('error', reject);
    worker.on('close', code => {
      clearTimeout(deadline);
      importWorker = null;
      if (code !== 0) return reject(new Error(errors || '导入进程失败或超时'));
      try { resolve(JSON.parse(output.trim().split(/\r?\n/).find(line => line.trim().startsWith('{')))); }
      catch (error) { reject(new Error(`Python worker returned invalid JSON: ${String(error)}; stdout tail: ${output.slice(-1000)}`)); }
    });
    worker.stdin.end(JSON.stringify(request));
  }).finally(() => { importBusy = false; });
}
ipcMain.handle('import-source', async (event, source) => {
  if (!window || event.sender !== window.webContents || typeof source !== 'string' || !path.isAbsolute(source)) throw new Error('无效的本地输入');
  return importRequest({ action: 'import', source });
});
ipcMain.handle('choose-import', async (event, kind) => {
  if (!window || event.sender !== window.webContents) throw new Error('无效窗口');
  const choice = await dialog.showOpenDialog(window, { properties: [kind === 'folder' ? 'openDirectory' : 'openFile'],
    filters: kind === 'folder' ? [] : [{ name: 'URDF / ZIP', extensions: ['urdf', 'zip'] }] });
  return choice.canceled ? null : importRequest({ action: 'import', source: choice.filePaths[0] });
});
ipcMain.handle('select-import', (event, operation_id, model) => {
  if (!window || event.sender !== window.webContents || typeof operation_id !== 'string' || typeof model !== 'string') throw new Error('无效选择');
  return importRequest({ action: 'select', operation_id, model });
});
let cadSource = null;
let cadExchangeDirectory = null;
function runPythonWorker(python, script, args, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    const child = spawn(path.join(root, python), [path.join(root, script), ...args],
      { cwd: root, env: { PATH: process.env.PATH }, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = ''; let errors = '';
    const deadline = setTimeout(() => child.kill('SIGKILL'), timeoutMs);
    child.stdout.on('data', data => {
      output += data;
      if (output.length > 16 * 1024 * 1024) child.kill('SIGKILL');
    });
    child.stderr.on('data', data => { errors = (errors + data).slice(-8192); });
    child.on('error', reject);
    child.on('close', code => {
      clearTimeout(deadline);
      if (code !== 0) return reject(new Error(errors || 'Python worker failed or timed out'));
      try { resolve(JSON.parse(output.trim().split(/\r?\n/).find(line => line.trim().startsWith('{')))); }
      catch (error) { reject(new Error(`Python worker returned invalid JSON: ${String(error)}; stdout tail: ${output.slice(-1000)}`)); }
    });
  });
}
function cadWorker(args) {
  return runPythonWorker('.tools/cad-venv/bin/python', 'scripts/cad_joint_wizard.py', args);
}
function assertRenderer(event) {
  if (!window || event.sender !== window.webContents) throw new Error('无效窗口');
}
const modelProject = () => path.join(app.getPath('userData'), 'modeling', 'project');
ipcMain.handle('model-current', async event => {
  assertRenderer(event);
  const project = modelProject();
  const pointer = path.join(project, 'current.json');
  if (!fs.existsSync(pointer)) return { revision: 0, recipe: { schema_version: 1, parts: [] } };
  const current = JSON.parse(await fs.promises.readFile(pointer, 'utf-8'));
  const revision = path.join(project, 'revisions', String(current.revision).padStart(6, '0'));
  const recipe = JSON.parse(await fs.promises.readFile(path.join(revision, 'recipe.json'), 'utf-8'));
  return { revision: current.revision, recipe };
});
ipcMain.handle('model-apply', async (event, recipe, expectedRevision) => {
  assertRenderer(event);
  if (!recipe || typeof recipe !== 'object' || !Number.isSafeInteger(expectedRevision) || expectedRevision < 0) throw new Error('无效建模请求');
  const encoded = JSON.stringify(recipe);
  if (encoded.length > 4 * 1024 * 1024) throw new Error('建模配方过大');
  const temporary = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'model-request-'));
  try {
    const recipePath = path.join(temporary, 'recipe.json');
    await fs.promises.writeFile(recipePath, encoded, { mode: 0o600 });
    const result = await runPythonWorker('.tools/model-venv/bin/python', 'scripts/model_project.py',
      [recipePath, '--project', modelProject(), '--expected-revision', String(expectedRevision)], 300000);
    const step = path.join(result.package, 'assembly.step');
    const assembly = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/model_assembly.py',
      [result.package, '--output', step], 180000);
    const discovery = await cadWorker([step]);
    cadSource = step;
    return { ...result, assembly, discovery };
  } finally { await fs.promises.rm(temporary, { recursive: true, force: true }); }
});
ipcMain.handle('choose-cad-step', async event => {
  assertRenderer(event);
  const fixture = smoke ? (process.env.URDFTOOLS_CAD_EXCHANGE_SMOKE || process.env.URDFTOOLS_CAD_WIZARD_SMOKE) : null;
  let original;
  if (fixture) original = fixture;
  else {
    const choice = await dialog.showOpenDialog(window, { properties: ['openFile'],
      filters: [{ name: 'STEP / STP / FreeCAD / IGES / BREP', extensions: ['step', 'stp', 'FCStd', 'igs', 'iges', 'brep', 'brp'] }] });
    if (choice.canceled) return null;
    original = choice.filePaths[0];
  }
  const extension = path.extname(original).toLowerCase();
  if (!['.step', '.stp', '.fcstd', '.igs', '.iges', '.brep', '.brp'].includes(extension)) throw new Error('不支持的 CAD 格式');
  let source = original;
  let generatedDirectory = null;
  let exchangeReport = null;
  try {
    if (!['.step', '.stp'].includes(extension)) {
      generatedDirectory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'cad-exchange-'));
      source = path.join(generatedDirectory, 'converted.step');
      if (extension === '.fcstd') {
        exchangeReport = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/freecad_bridge.py',
          [original, '--output', source], 300000);
      } else {
        const args = [original, '--output', source];
        if (['.brep', '.brp'].includes(extension)) {
          const choice = await dialog.showMessageBox(window, { type: 'question', buttons: ['毫米 mm', '米 m', '取消'],
            cancelId: 2, defaultId: 0, message: 'BREP 文件没有单位，请选择原文件使用的长度单位' });
          if (choice.response === 2) return null;
          args.push('--brep-unit', choice.response === 0 ? 'mm' : 'm');
        }
        exchangeReport = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/cad_exchange.py', args, 180000);
      }
    }
    const result = await cadWorker([source]);
    if (cadExchangeDirectory) await fs.promises.rm(cadExchangeDirectory, { recursive: true, force: true });
    cadSource = source;
    cadExchangeDirectory = generatedDirectory;
    generatedDirectory = null;
    return { ...result, exchangeReport };
  } finally {
    if (generatedDirectory) await fs.promises.rm(generatedDirectory, { recursive: true, force: true });
  }
});
ipcMain.handle('cad-preview', async (event, config) => {
  assertRenderer(event);
  if (!cadSource || !config || typeof config !== 'object') throw new Error('请先选择 STEP 文件');
  const encoded = JSON.stringify(config);
  if (encoded.length > 1024 * 1024) throw new Error('转换配置过大');
  const directory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'cad-preview-'));
  try {
    const configPath = path.join(directory, 'config.json');
    const previewPath = path.join(directory, 'preview.urdf');
    await fs.promises.writeFile(configPath, encoded, { mode: 0o600 });
    await cadWorker([cadSource, '--config', configPath, '--preview', previewPath]);
    return await importRequest({ action: 'import', source: previewPath });
  } finally {
    await fs.promises.rm(directory, { recursive: true, force: true });
  }
});
ipcMain.handle('save-cad-config', async (event, config) => {
  assertRenderer(event);
  if (!cadSource || !config || typeof config !== 'object') throw new Error('没有可保存的配置');
  const encoded = JSON.stringify(config, null, 2) + '\n';
  if (encoded.length > 1024 * 1024) throw new Error('转换配置过大');
  const choice = await dialog.showSaveDialog(window, { defaultPath: 'cad-joints.json',
    filters: [{ name: 'JSON 配置', extensions: ['json'] }] });
  if (choice.canceled) return false;
  await fs.promises.writeFile(choice.filePath, encoded, { mode: 0o600 });
  return true;
});
ipcMain.handle('load-cad-config', async event => {
  assertRenderer(event);
  if (!cadSource) throw new Error('请先选择 STEP 文件');
  const choice = await dialog.showOpenDialog(window, { properties: ['openFile'],
    filters: [{ name: 'JSON 配置', extensions: ['json'] }] });
  if (choice.canceled) return null;
  const file = choice.filePaths[0];
  if ((await fs.promises.stat(file)).size > 1024 * 1024) throw new Error('转换配置过大');
  const result = await cadWorker([cadSource, '--config', file]);
  return result.configuration;
});
ipcMain.handle('export-cad-package', async (event, config, densities) => {
  assertRenderer(event);
  if (!cadSource || !config || typeof config !== 'object' || !densities || typeof densities !== 'object') {
    throw new Error('请先选择 STEP 并填写转换配置与密度');
  }
  const encodedConfig = JSON.stringify(config), encodedDensities = JSON.stringify(densities);
  if (encodedConfig.length > 1024*1024 || encodedDensities.length > 1024*1024) throw new Error('转换配置过大');
  let destination = smoke ? process.env.URDFTOOLS_CAD_EXPORT_SMOKE : null;
  if (!destination) {
    const choice = await dialog.showSaveDialog(window, { defaultPath: 'urdftools_robot.zip',
      filters: [{ name: 'URDF / ROS ZIP', extensions: ['zip'] }] });
    if (choice.canceled) return null;
    destination = choice.filePath;
  }
  if (path.extname(destination).toLowerCase() !== '.zip') throw new Error('导出目标必须是 ZIP');
  const directory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'cad-export-'));
  const temporaryDestination = destination + '.partial-' + randomBytes(6).toString('hex');
  try {
    const configPath = path.join(directory, 'config.json');
    const densitiesPath = path.join(directory, 'densities.json');
    const zipPath = path.join(directory, 'robot.zip');
    await fs.promises.writeFile(configPath, encodedConfig, { mode: 0o600 });
    await fs.promises.writeFile(densitiesPath, encodedDensities, { mode: 0o600 });
    const exported = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/cad_export_package.py',
      [cadSource, '--config', configPath, '--densities', densitiesPath, '--output', zipPath], 300000);
    const validation = await runPythonWorker('.tools/sim-venv/bin/python', 'scripts/validate_cad_package.py', [zipPath], 120000);
    if (validation.status !== 'passed') throw new Error('独立交叉校验未通过');
    await fs.promises.copyFile(zipPath, temporaryDestination);
    await fs.promises.rename(temporaryDestination, destination);
    return { path: destination, sha256: exported.sha256, validation };
  } finally {
    await fs.promises.rm(temporaryDestination, { force: true });
    await fs.promises.rm(directory, { recursive: true, force: true });
  }
});
function stopService() {
  stopping = true;
  if (importWorker) importWorker.kill('SIGTERM');
  if (service && service.exitCode === null) {
    service.kill('SIGTERM');
    setTimeout(() => { if (service.exitCode === null) service.kill('SIGKILL'); }, 2000).unref();
  }
}
function fail(error) { console.error(error.message || error); stopService(); app.exit(1); }
app.whenReady().then(() => {
  setupAssetProtocol();
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
        if (process.env.URDFTOOLS_MODEL_SMOKE) {
          const runModelSmoke = require(path.join(root, 'scripts/m01_desktop_smoke_hook.cjs'));
          await runModelSmoke(window, process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
        }
        if (process.env.URDFTOOLS_IMPORT_SMOKE) {
          const fixture = process.env.URDFTOOLS_IMPORT_SMOKE;
          const waitFor = async expression => {
            const until = Date.now() + 15000;
            while (Date.now() < until) {
              if (await window.webContents.executeJavaScript(expression)) return;
              await new Promise(resolve => setTimeout(resolve, 30));
            }
            throw new Error('Import UI timeout: ' + expression);
          };
          window.webContents.debugger.attach('1.3');
          const target = await window.webContents.executeJavaScript(`(() => { const rect = document.querySelector('[aria-label="本地导入"]').getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + Math.min(100, rect.height / 2)), rect: rect.toJSON() }; })()`);
          const dragData = { items: [], files: [fixture], dragOperationsMask: 1 };
          window.webContents.on('console-message', ({ level, message }) => console.log(JSON.stringify({ event: 'renderer_console', level, message })));
          for (const type of ['dragEnter', 'dragOver', 'drop']) {
            await window.webContents.debugger.sendCommand('Input.dispatchDragEvent', { type, x: target.x, y: target.y, data: dragData });
          }
          console.log(JSON.stringify({ event: 'drag_diagnostics', target, dom: await window.webContents.executeJavaScript(`({ errors: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent), status: document.querySelector('[data-import-status]')?.getAttribute('data-import-status'), text: document.querySelector('main')?.textContent.slice(0, 200) })`) }));
          await waitFor(`document.querySelector('[data-import-status="selection_required"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelectorAll('article button')[0].click()`);
          await waitFor(`document.querySelector('[data-import-status="ready"]') !== null`);
          const first = await window.webContents.executeJavaScript(`document.querySelector('article button[aria-pressed=true]').textContent`);
          if (!first.includes('中文样机')) throw new Error('Wrong model selected');
          await window.webContents.executeJavaScript(`document.querySelectorAll('article button')[1].click()`);
          await waitFor(`document.querySelector('[data-import-status="failed"]') !== null`);
          const findings = await window.webContents.executeJavaScript(`document.querySelector('main').textContent`);
          if (!findings.includes('missing_resource') || !findings.includes('02缺失.urdf#element[')) throw new Error('Missing located error');
          window.webContents.debugger.detach();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'import.png'), (await window.webContents.capturePage()).toPNG());
          console.log(JSON.stringify({ event: 'desktop_import_smoke', nativeDrag: true, multiModel: true, selectedReady: first, missingLocated: true }));
        }
        if (process.env.URDFTOOLS_VIEWER_SMOKE) {
          const fixture = process.env.URDFTOOLS_VIEWER_SMOKE;
          const waitFor = async expression => {
            const until = Date.now() + (process.env.URDFTOOLS_VIEWER_S06_SMOKE ? 90000 : 20000);
            while (Date.now() < until) {
              if (await window.webContents.executeJavaScript(expression)) return;
              await new Promise(resolve => setTimeout(resolve, 60));
            }
            throw new Error('Viewer UI timeout: ' + expression + ' | ' +
              await window.webContents.executeJavaScript("document.querySelector('main').textContent.slice(-600)"));
          };
          const rect = await window.webContents.executeJavaScript(`(() => { const r = document.querySelector('[aria-label="本地导入"]').getBoundingClientRect(); return {x:Math.round(r.left+r.width/2),y:Math.round(r.top+45)}; })()`);
          window.webContents.debugger.attach('1.3');
          const data = { items: [], files: [fixture], dragOperationsMask: 1 };
          for (const type of ['dragEnter', 'dragOver', 'drop']) {
            await window.webContents.debugger.sendCommand('Input.dispatchDragEvent', { type, x: rect.x, y: rect.y, data });
          }
          await waitFor(`document.querySelector('[data-import-status="ready"]') !== null`);
          if (process.env.URDFTOOLS_VIEWER_S06_SMOKE) {
            console.log(JSON.stringify({ event: 'desktop_viewer_import_ready', model: process.env.URDFTOOLS_VIEWER_S06_SMOKE, fixture }));
            window.webContents.debugger.detach();
          } else {
          await waitFor(`Number(document.querySelector('[data-mesh-count]')?.dataset.meshCount) >= 2`);
          await waitFor(`document.querySelector('input[aria-label="shoulder"]') !== null`);
          const before = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="shoulder"]').focus()`);
          window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
          window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
          await waitFor(`Number(document.querySelector('input[aria-label="shoulder"]')?.value) > 1.19`);
          const after = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          if (!after || after === before) throw new Error('Joint did not rotate');
          const range = await window.webContents.executeJavaScript(`(() => {const s = document.querySelector('input[aria-label="shoulder"]'); return {value:Number(s.value),min:Number(s.min),max:Number(s.max)};})()`);
          if (range.min !== -1.2 || range.max !== 1.2) throw new Error('Incorrect joint limits');
          const png = (await window.webContents.capturePage()).toPNG();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'viewer.png'), png);
          window.webContents.debugger.detach();
          console.log(JSON.stringify({ event: 'desktop_viewer_smoke', meshCount: 2, joint: 'shoulder',
            value: range.value, limits: [range.min, range.max], quaternion: after, screenshotBytes: png.length }));
          }
        }
        if (process.env.URDFTOOLS_VIEWER_S05_SMOKE) {
          window.webContents.on('console-message', ({ level, message }) => console.log(JSON.stringify({ event: 's05_renderer_console', level, message })));
          console.log(JSON.stringify({ event: 's05_step', step: 'start' }));
          const waitFor = async expression => {
            const until = Date.now() + 20000;
            while (Date.now() < until) {
              if (await window.webContents.executeJavaScript(expression)) return;
              await new Promise(resolve => setTimeout(resolve, 50));
            }
            throw new Error('S05 analysis UI timeout: ' + expression + ' | ' +
              await window.webContents.executeJavaScript("document.querySelector('main').textContent.slice(-1200)"));
          };
          await waitFor(`Number(document.querySelector('[data-tree-link-count]')?.dataset.treeLinkCount) === 2`);
          await waitFor(`Number(document.querySelector('[data-collision-count]')?.dataset.collisionCount) === 1`);
          await waitFor(`Number(document.querySelector('[data-mass-known-count]')?.dataset.massKnownCount) === 1`);
          await waitFor(`document.querySelector('[data-overall-bounds]')?.dataset.overallBounds !== ''`);
          console.log(JSON.stringify({ event: 's05_step', step: 'initial-ui-ready' }));
          const before = await window.webContents.executeJavaScript(`(() => {
            const v = document.querySelector('[aria-label="三维机器人查看器"]');
            return {
              meshCount:Number(v.dataset.meshCount), linkCount:Number(v.dataset.treeLinkCount),
              jointCount:Number(v.dataset.treeJointCount), visualCount:Number(v.dataset.visualCount),
              collisionCount:Number(v.dataset.collisionCount), collisionStyledMeshCount:Number(v.dataset.collisionStyledMeshCount),
              massKnownCount:Number(v.dataset.massKnownCount),
              massUnknownCount:Number(v.dataset.massUnknownCount), totalKnownMass:Number(v.dataset.totalKnownMass),
              massComplete:v.dataset.massComplete === 'true', physicsFingerprint:v.dataset.physicsFingerprint,
              bounds:v.dataset.overallBounds.split(',').map(Number)
            };
          })()`);
          console.log(JSON.stringify({ event: 's05_step', step: 'initial-metrics', before }));
          if (before.linkCount !== 2 || before.jointCount !== 1 || before.visualCount !== 2 ||
              before.collisionCount !== 1 || before.massKnownCount !== 1 || before.massUnknownCount !== 1 ||
              before.massComplete || Math.abs(before.totalKnownMass - 1.25) > 0.001 ||
              before.bounds.length !== 3 || before.bounds.some(n => !(n > 0))) {
            throw new Error('Incorrect structure/physics/measurement values: ' + JSON.stringify(before));
          }
          console.log(JSON.stringify({ event: 's05_step', step: 'metrics-valid' }));
          await window.webContents.executeJavaScript(`document.querySelector('[data-structure-node="joint:shoulder"]').click()`);
          await waitFor(`document.querySelector('[data-selected-node]')?.dataset.selectedNode === 'joint:shoulder'`);
          const jointPosition = await window.webContents.executeJavaScript(`document.querySelector('[data-selected-position]')?.dataset.selectedPosition`);
          if (!jointPosition || jointPosition.split(',').length !== 3) throw new Error('Joint world position missing');
          console.log(JSON.stringify({ event: 's05_step', step: 'joint-selected', jointPosition }));
          await window.webContents.executeJavaScript(`document.querySelector('[data-structure-node="link:body"]').click()`);
          await waitFor(`document.querySelector('[data-selected-node]')?.dataset.selectedNode === 'link:body'`);
          const selectedDimensions = await window.webContents.executeJavaScript(`document.querySelector('[data-selected-dimensions]')?.dataset.selectedDimensions`);
          if (!selectedDimensions || selectedDimensions.split(',').length !== 3 ||
              selectedDimensions.split(',').some(n => !(Number(n) > 0))) {
            throw new Error('Selected link bounding box invalid: ' + selectedDimensions);
          }
          console.log(JSON.stringify({ event: 's05_step', step: 'link-selected', selectedDimensions }));
          const slider = await window.webContents.executeJavaScript(`(() => { const s=document.querySelector('input[aria-label="shoulder"]'); return {value:Number(s.value),min:Number(s.min),max:Number(s.max)}; })()`);
          if (slider.min !== -1.2 || slider.max !== 1.2 || Math.abs(slider.value - 1.2) > 0.011) {
            throw new Error('Joint slider value/limits invalid: ' + JSON.stringify(slider));
          }
          console.log(JSON.stringify({ event: 's05_step', step: 'joint-range', slider }));
          const fingerprint = before.physicsFingerprint;
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="显示碰撞体"]').click()`);
          await waitFor(`Number(document.querySelector('[data-visible-collision-count]')?.dataset.visibleCollisionCount) === 1`);
          await waitFor(`Number(document.querySelector('[data-mesh-count]')?.dataset.meshCount) >= 3`);
          const afterCollision = await window.webContents.executeJavaScript(`document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint`);
          if (afterCollision !== fingerprint) throw new Error('Collision toggle changed URDF physics values');
          console.log(JSON.stringify({ event: 's05_step', step: 'collision-visible' }));
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="显示视觉模型"]').click()`);
          await waitFor(`Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) === 0`);
          await waitFor(`Number(document.querySelector('[data-visible-collision-count]')?.dataset.visibleCollisionCount) === 1`);
          const afterHiddenVisual = await window.webContents.executeJavaScript(`document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint`);
          if (afterHiddenVisual !== fingerprint) throw new Error('Visual toggle changed URDF physics values');
          console.log(JSON.stringify({ event: 's05_step', step: 'visual-hidden' }));
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="显示视觉模型"]').click()`);
          await waitFor(`Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) === 2`);
          await waitFor(`document.querySelector('[data-visual-visible]')?.dataset.visualVisible === 'true' && document.querySelector('input[aria-label="显示视觉模型"]')?.checked === true`);
          console.log(JSON.stringify({ event: 's05_step', step: 'visual-restored' }));
          await waitFor(`Number(document.querySelector('[data-com-marker-count]')?.dataset.comMarkerCount) === 1`);
          await window.webContents.executeJavaScript(`document.querySelector('button[aria-label="隔离选中 Link"]').click()`);
          await waitFor(`document.querySelector('[data-isolated-link]')?.dataset.isolatedLink === 'body'`);
          await waitFor(`Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) === 1`);
          await waitFor(`Number(document.querySelector('[data-visible-collision-count]')?.dataset.visibleCollisionCount) === 1`);
          const afterIsolation = await window.webContents.executeJavaScript(`document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint`);
          if (afterIsolation !== fingerprint) throw new Error('Isolation changed URDF physics values');
          await window.webContents.executeJavaScript(`document.querySelector('button[aria-label="隔离选中 Link"]').click()`);
          await waitFor(`document.querySelector('[data-isolated-link]')?.dataset.isolatedLink === ''`);
          await waitFor(`Number(document.querySelector('[data-visible-visual-count]')?.dataset.visibleVisualCount) === 2`);
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="显示已知质心"]').click()`);
          await waitFor(`Number(document.querySelector('[data-visible-com-marker-count]')?.dataset.visibleComMarkerCount) === 0`);
          const afterComHidden = await window.webContents.executeJavaScript(`document.querySelector('[data-physics-fingerprint]')?.dataset.physicsFingerprint`);
          if (afterComHidden !== fingerprint) throw new Error('COM marker toggle changed URDF physics values');
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="显示已知质心"]').click()`);
          await waitFor(`Number(document.querySelector('[data-visible-com-marker-count]')?.dataset.visibleComMarkerCount) === 1`);
          await window.webContents.executeJavaScript(`document.querySelector('button[aria-label="重置视角"]').click()`);
          await waitFor(`Number(document.querySelector('[data-view-reset-count]')?.dataset.viewResetCount) === 1`);
          const exportPath = path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'viewer-export.png');
          const exportPromise = new Promise((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error('Screenshot download timed out')), 12000);
            window.webContents.session.once('will-download', (event, item) => {
              item.setSavePath(exportPath);
              item.once('done', (_downloadEvent, state) => {
                clearTimeout(timeout);
                if (state !== 'completed') return reject(new Error('Screenshot download failed: ' + state));
                try { resolve({ state, bytes: fs.statSync(exportPath).size }); }
                catch (error) { reject(error); }
              });
            });
          });
          await window.webContents.executeJavaScript(`document.querySelector('button[aria-label="导出三维截图"]').click()`);
          const exportResult = await exportPromise;
          if (exportResult.bytes < 1000) throw new Error('Exported screenshot is unexpectedly small');
          await waitFor(`document.querySelector('[data-screenshot-ready]')?.dataset.screenshotReady === 'true'`);
          console.log(JSON.stringify({ event: 's05_step', step: 'isolation-com-view-screenshot', exportResult }));
          const final = await window.webContents.executeJavaScript(`(() => {
            const v=document.querySelector('[aria-label="三维机器人查看器"]');
            return {
              meshCount:Number(v.dataset.meshCount), linkCount:Number(v.dataset.treeLinkCount),
              jointCount:Number(v.dataset.treeJointCount), visualCount:Number(v.dataset.visualCount),
              visibleVisualCount:Number(v.dataset.visibleVisualCount), collisionCount:Number(v.dataset.collisionCount),
              collisionStyledMeshCount:Number(v.dataset.collisionStyledMeshCount),
              visibleCollisionCount:Number(v.dataset.visibleCollisionCount), massKnownCount:Number(v.dataset.massKnownCount),
              massUnknownCount:Number(v.dataset.massUnknownCount), totalKnownMass:Number(v.dataset.totalKnownMass),
              massComplete:v.dataset.massComplete === 'true', physicsFingerprint:v.dataset.physicsFingerprint,
              visualVisible:v.dataset.visualVisible === 'true', collisionVisible:v.dataset.collisionVisible === 'true',
              visualChecked:document.querySelector('input[aria-label="显示视觉模型"]').checked,
              collisionChecked:document.querySelector('input[aria-label="显示碰撞体"]').checked,
              comMarkerCount:Number(v.dataset.comMarkerCount), visibleComMarkerCount:Number(v.dataset.visibleComMarkerCount),
              comVisible:v.dataset.comVisible === 'true', isolatedLink:v.dataset.isolatedLink,
              viewResetCount:Number(v.dataset.viewResetCount), screenshotReady:v.dataset.screenshotReady === 'true',
              bounds:v.dataset.overallBounds.split(',').map(Number), selectedDimensions:v.dataset.selectedDimensions.split(',').map(Number),
              joint:'shoulder', jointValue:Number(document.querySelector('input[aria-label="shoulder"]').value)
            };
          })()`);
          final.physicsUnchanged = final.physicsFingerprint === fingerprint;
          delete final.physicsFingerprint;
          final.isolationRestored = final.isolatedLink === '' && final.visibleVisualCount === 2;
          final.comMarkerVerified = final.comMarkerCount === 1 && final.visibleComMarkerCount === 1 && final.comVisible;
          final.screenshotExportBytes = exportResult.bytes;
          const png = (await window.webContents.capturePage()).toPNG();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'viewer-analysis.png'), png);
          console.log(JSON.stringify({ event: 's05_step', step: 'screenshot', bytes: png.length }));
          console.log(JSON.stringify({ event: 'desktop_viewer_s05_smoke', ...final,
            jointPosition:jointPosition, screenshotBytes:png.length }));
        }
        if (process.env.URDFTOOLS_VIEWER_S06_SMOKE) {
          const runS06ViewerSmoke = require(path.join(root, 'scripts/s06_desktop_smoke_hook.cjs'));
          await runS06ViewerSmoke(window, path, fs, process.env.URDFTOOLS_VIEWER_S06_SMOKE);
        }
        if (process.env.URDFTOOLS_CAD_EXCHANGE_SMOKE) {
          const waitForExchange = async expression => {
            const until = Date.now() + 90000;
            while (Date.now() < until) {
              if (await window.webContents.executeJavaScript(expression)) return;
              await new Promise(resolve => setTimeout(resolve, 80));
            }
            throw new Error('FreeCAD exchange UI timeout: ' + expression + ' | ' +
              await window.webContents.executeJavaScript("document.querySelector('main').textContent.slice(-1000)"));
          };
          await window.webContents.executeJavaScript(`document.querySelectorAll('nav button')[1].click()`);
          await waitForExchange(`[...document.querySelectorAll('button')].some(b => b.textContent === '选择 CAD 文件')`);
          await window.webContents.executeJavaScript(`([...document.querySelectorAll('button')].find(b => b.textContent === '选择 CAD 文件')).click()`);
          await waitForExchange(`document.querySelector('.cad-wizard aside')?.textContent.includes('STEP drops FreeCAD feature history') === true`);
          const details = await window.webContents.executeJavaScript(`document.querySelector('.cad-wizard').textContent`);
          if (!details.includes('BaseBracket') || !details.includes('ArmLink') || !details.includes('未确认关节：1')) {
            throw new Error('FreeCAD exchange failed to show two parts and explicit loss report');
          }
          const png = (await window.webContents.capturePage()).toPNG();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'freecad-exchange.png'), png);
          console.log(JSON.stringify({ event: 'desktop_freecad_exchange_smoke', partCount: 2,
            lossVisible: true, screenshotBytes: png.length }));
        }
        if (process.env.URDFTOOLS_CAD_WIZARD_SMOKE) {
          const waitForCad = async expression => {
            const until = Date.now() + 60000;
            while (Date.now() < until) {
              if (await window.webContents.executeJavaScript(expression)) return;
              await new Promise(resolve => setTimeout(resolve, 60));
            }
            throw new Error('CAD wizard UI timeout: ' + expression + ' | ' +
              await window.webContents.executeJavaScript("document.querySelector('main').textContent.slice(-800)"));
          };
          await window.webContents.executeJavaScript(`document.querySelectorAll('nav button')[1].click()`);
          await waitForCad(`document.querySelector('button') && [...document.querySelectorAll('button')].some(b => b.textContent === '选择 CAD 文件')`);
          await window.webContents.executeJavaScript(`([...document.querySelectorAll('button')].find(b => b.textContent === '选择 CAD 文件')).click()`);
          await waitForCad(`document.querySelector('[aria-label="OffsetPart_joint type"]') !== null`);
          const discovered = await window.webContents.executeJavaScript(`document.querySelector('.cad-wizard').textContent`);
          if (!discovered.includes('BasePart') || !discovered.includes('OffsetPart') ||
              !discovered.includes('未确认关节：1')) throw new Error('CAD parts/candidate missing');
          await window.webContents.executeJavaScript(`(() => {
            const el=document.querySelector('[aria-label="OffsetPart_joint type"]');
            const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;
            setter.call(el,'revolute'); el.dispatchEvent(new Event('change',{bubbles:true}));
          })()`);
          await waitForCad(`document.querySelector('[aria-label="OffsetPart_joint limits"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="OffsetPart_joint confirmed"]').click()`);
          await waitForCad(`Number(document.querySelector('[aria-label="三维机器人查看器"]')?.dataset.treeLinkCount) === 2`);
          const event = await window.webContents.executeJavaScript(`(() => {
            const v=document.querySelector('[aria-label="三维机器人查看器"]');
            const slider=document.querySelector('input[aria-label="OffsetPart_joint"]');
            return {linkCount:Number(v.dataset.treeLinkCount),jointCount:Number(v.dataset.treeJointCount),
              meshCount:Number(v.dataset.meshCount),jointMin:Number(slider?.min),jointMax:Number(slider?.max),
              unconfirmed:document.querySelector('.cad-wizard').textContent.includes('未确认关节：0')};
          })()`);
          if (event.jointCount !== 1 || event.meshCount < 2 || event.jointMin !== -1 ||
              event.jointMax !== 1 || !event.unconfirmed) throw new Error('CAD preview mismatch: '+JSON.stringify(event));
          const initialQuaternion = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="OffsetPart_joint"]').focus()`);
          window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
          window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
          await waitForCad(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion !== '${initialQuaternion}'`);
          const zQuaternion = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          const axisInput = '[aria-label="OffsetPart_joint axis"]';
          await window.webContents.executeJavaScript(`(() => { const el=document.querySelector('${axisInput}'); el.focus(); el.value='1 0 0'; el.dispatchEvent(new FocusEvent('focusout',{bubbles:true})); el.blur(); })()`);
          await waitForCad(`document.querySelector('.cad-wizard').textContent.includes('未确认关节：1')`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="OffsetPart_joint confirmed"]').click()`);
          await waitForCad(`Number(document.querySelector('[aria-label="三维机器人查看器"]')?.dataset.treeLinkCount) === 2`);
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="OffsetPart_joint"]').focus()`);
          window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
          window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
          await waitForCad(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion && document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion !== '${zQuaternion}'`);
          const xQuaternion = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          const z = zQuaternion.split(',').map(Number), x = xQuaternion.split(',').map(Number);
          if (Math.abs(z[2]) < 0.4 || Math.abs(z[0]) > 0.01 || Math.abs(x[0]) < 0.4 || Math.abs(x[2]) > 0.01) {
            throw new Error('Corrected CAD joint axis did not change rotation: '+JSON.stringify({zQuaternion,xQuaternion}));
          }
          const png = (await window.webContents.capturePage()).toPNG();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-wizard.png'), png);
          console.log(JSON.stringify({ event: 'desktop_cad_wizard_smoke', ...event, zQuaternion, xQuaternion, screenshotBytes: png.length }));
          if (process.env.URDFTOOLS_CAD_EXPORT_SMOKE) {
            const setNumber = async (label, value) => {
              await window.webContents.executeJavaScript(`(() => {
                const el=document.querySelector('[aria-label="${label}"]');
                const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
                setter.call(el,'${value}'); el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
              })()`);
            };
            await window.webContents.executeJavaScript(`([...document.querySelectorAll('button')].find(b => b.textContent === '导出并交叉校验 URDF / ROS ZIP')).click()`);
            await waitForCad(`[...document.querySelectorAll('[role="alert"]')].some(x => x.textContent.includes('缺少明确的材料密度'))`);
            await setNumber('BasePart density', 2700);
            await setNumber('OffsetPart density', 2700);
            await setNumber('OffsetPart_joint effort', 10);
            await setNumber('OffsetPart_joint velocity', 2);
            await waitForCad(`document.querySelector('.cad-wizard').textContent.includes('未确认关节：1')`);
            await window.webContents.executeJavaScript(`document.querySelector('[aria-label="OffsetPart_joint confirmed"]').click()`);
            await window.webContents.executeJavaScript(`([...document.querySelectorAll('button')].find(b => b.textContent === '导出并交叉校验 URDF / ROS ZIP')).click()`);
            await waitForCad(`[...document.querySelectorAll('[role="status"]')].some(x => x.textContent.includes('导出完成'))`);
            const output = process.env.URDFTOOLS_CAD_EXPORT_SMOKE;
            const size = fs.statSync(output).size;
            const summary = await window.webContents.executeJavaScript(`[...document.querySelectorAll('[role="status"]')].find(x => x.textContent.includes('导出完成'))?.textContent`);
            if (size < 1000 || !summary.includes('训练就绪：尚未验证')) throw new Error('CAD ZIP export report invalid');
            fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-export.png'), (await window.webContents.capturePage()).toPNG());
            console.log(JSON.stringify({ event: 'desktop_cad_export_smoke', zipBytes: size, summary }));
          }
        }
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
