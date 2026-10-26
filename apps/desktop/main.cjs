const { app, BrowserWindow, ipcMain, dialog, protocol } = require('electron');
const { spawn } = require('node:child_process');
const { randomBytes, createHash } = require('node:crypto');
const path = require('node:path');
const readline = require('node:readline');
const fs = require('node:fs');
const { createCadDraftStore } = require('./cadDraftStore.cjs');
protocol.registerSchemesAsPrivileged([{ scheme: 'urdftools', privileges: {
  standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true
} }]);
const root = path.resolve(__dirname, '../..');
const mimeTypes = { '.urdf': 'application/xml', '.obj': 'text/plain; charset=utf-8',
  '.stl': 'model/stl', '.dae': 'model/vnd.collada+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.bmp': 'image/bmp' };
const resultMedia = new Map();
const resultAssets = new Map();
const cadMeshAssets = new Map();
function setupAssetProtocol() {
  protocol.handle('urdftools', async request => {
    try {
      const url = new URL(request.url);
      if (url.hostname === 'cad-mesh' && request.method === 'GET') {
        const item = cadMeshAssets.get(url.pathname.slice(1));
        if (!item) throw new Error('unknown CAD mesh');
        const bytes = await fs.promises.readFile(item.path);
        if (bytes.length !== item.size) throw new Error('CAD mesh changed');
        return new Response(bytes, { status: 200, headers: {
          'Content-Type': 'model/stl', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store'
        } });
      }
      if (url.hostname === 'result-asset' && request.method === 'GET') {
        const segments = url.pathname.split('/').slice(1).map(decodeURIComponent);
        const runId = segments.shift();
        const item = resultAssets.get(runId + ':' + segments.join('/'));
        if (!item) throw new Error('unknown project asset');
        const bytes = await fs.promises.readFile(item.path);
        if (bytes.byteLength !== item.size || createHash('sha256').update(bytes).digest('hex') !== item.sha256)
          throw new Error('project asset changed');
        return new Response(bytes, { status: 200, headers: {
          'Content-Type': mimeTypes[path.extname(item.relative).toLowerCase()] || 'application/octet-stream',
          'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'
        } });
      }
      if (url.hostname === 'result' && request.method === 'GET') {
        const sha = url.pathname.slice(1);
        const item = resultMedia.get(sha);
        if (!/^[0-9a-f]{64}$/.test(sha) || !item) throw new Error('unknown result video');
        const stat = await fs.promises.stat(item.path);
        if (stat.size > 128 * 1024 * 1024) throw new Error('result video exceeds desktop playback limit');
        const bytes = await fs.promises.readFile(item.path);
        if (createHash('sha256').update(bytes).digest('hex') !== sha)
          throw new Error('result video changed or exceeds desktop playback limit');
        const range = request.headers.get('range');
        const match = range && /^bytes=(\d+)-(\d*)$/.exec(range);
        if (range && !match) return new Response(null, { status: 416 });
        const start = match ? Number(match[1]) : 0;
        const end = match && match[2] ? Math.min(Number(match[2]), bytes.length - 1) : bytes.length - 1;
        if (start > end || start >= bytes.length) return new Response(null, { status: 416 });
        const headers = { 'Content-Type': item.mime, 'Accept-Ranges': 'bytes', 'Content-Length': String(end-start+1),
          'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
        if (match) headers['Content-Range'] = `bytes ${start}-${end}/${bytes.length}`;
        return new Response(bytes.subarray(start, end + 1), { status: match ? 206 : 200, headers });
      }
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
    } catch (cause) {
      console.error(JSON.stringify({ event: 'asset_request_failed', url: request.url, error: String(cause) }));
      return new Response('Resource not available', { status: 404, headers: { 'Access-Control-Allow-Origin': '*' } });
    }
  });
}
const smoke = process.argv.includes('--smoke');
const resultStore = () => smoke && process.env.URDFTOOLS_B08_SMOKE_STORE ?
  process.env.URDFTOOLS_B08_SMOKE_STORE : path.join(app.getPath('userData'), 'external-results');
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
ipcMain.handle('import-example', event => {
  if (!window || event.sender !== window.webContents) throw new Error('无效窗口');
  return importRequest({ action: 'import', source: path.join(root, 'examples/robot_demo') });
});
ipcMain.handle('result-runs', async event => {
  assertRenderer(event);
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['list', '--store', resultStore()]);
});
ipcMain.handle('result-project', async (event, runId, name, isStandard) => {
  assertRenderer(event);
  if (typeof runId !== 'string' || !runId || runId.length > 160 ||
      typeof name !== 'string' || !name.trim() || name.length > 120 || typeof isStandard !== 'boolean')
    throw new Error('无效项目设置');
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['project', '--store', resultStore(), '--run-id', runId, '--name', name, ...(isStandard ? ['--standard'] : [])]);
});
ipcMain.handle('result-series', async (event, runId) => {
  assertRenderer(event);
  if (typeof runId !== 'string' || !runId || runId.length > 160) throw new Error('无效实验编号');
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['series', '--store', resultStore(), '--run-id', runId]);
});
ipcMain.handle('result-scene', async (event, runId) => {
  assertRenderer(event);
  if (typeof runId !== 'string' || !runId || runId.length > 160) throw new Error('无效实验编号');
  const scene = await runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['scene', '--store', resultStore(), '--run-id', runId]);
  for (const item of scene.assets) {
    if (typeof item.path !== 'string' || !/^[0-9a-f]{64}$/.test(item.sha256) ||
        !Number.isSafeInteger(item.size) || item.size < 0) continue;
    resultAssets.set(runId + ':' + item.path, {
      relative: item.path, sha256: item.sha256, size: item.size,
      path: path.join(resultStore(), 'results', 'blobs', item.sha256.slice(0, 2), item.sha256)
    });
  }
  return scene;
});
ipcMain.handle('result-pairs', async (event, candidate) => {
  assertRenderer(event);
  if (typeof candidate !== 'string' || !candidate || candidate.length > 160) throw new Error('无效候选项目');
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['pairs', '--store', resultStore(), '--candidate', candidate]);
});
ipcMain.handle('result-save-pair', async (event, candidate, reference, requestId, mode) => {
  assertRenderer(event);
  if ([candidate, reference].some(value => typeof value !== 'string' || !value || value.length > 160) ||
      (requestId !== null && (typeof requestId !== 'string' || !/^[a-f0-9]{32}$/.test(requestId))) ||
      (mode !== null && mode !== 'webcodex' && mode !== 'cli')) throw new Error('无效对比记录');
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['save-pair', '--store', resultStore(), '--candidate', candidate, '--reference', reference,
      ...(requestId ? ['--request-id', requestId] : []), ...(mode ? ['--mode', mode] : [])]);
});
ipcMain.handle('result-import', async event => {
  assertRenderer(event);
  const choice = smoke && process.env.URDFTOOLS_B08_SMOKE_SOURCE ?
    { canceled: false, filePaths: [process.env.URDFTOOLS_B08_SMOKE_SOURCE] } :
    await dialog.showOpenDialog(window, { properties: ['openDirectory'] });
  if (choice.canceled) return null;
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['import', '--store', resultStore(), '--source', choice.filePaths[0]], 300000);
});
ipcMain.handle('result-import-native', async (event, algorithm, chooseVideos) => {
  assertRenderer(event);
  if (typeof algorithm !== 'string' || !algorithm.trim() || algorithm.length > 80 ||
      typeof chooseVideos !== 'boolean') throw new Error('请填写算法名称');
  const source = await dialog.showOpenDialog(window, {
    title: '选择 MyHIMLoco 或 WMP 训练目录（包含 config.json 和 TensorBoard 文件）',
    properties: ['openDirectory']
  });
  if (source.canceled) return null;
  let videos = null;
  if (chooseVideos) {
    const chosen = await dialog.showOpenDialog(window, {
      title: '选择视频目录（可取消；训练目录内的视频会自动发现）', properties: ['openDirectory']
    });
    if (!chosen.canceled) videos = chosen.filePaths[0];
  }
  return runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['import-native', '--store', resultStore(), '--source', source.filePaths[0],
      '--algorithm', algorithm.trim(), ...(videos ? ['--videos', videos] : [])], 300000);
});
ipcMain.handle('result-compare', async (event, reference, candidate) => {
  assertRenderer(event);
  for (const runId of [reference, candidate]) {
    if (typeof runId !== 'string' || !runId || runId.length > 160) throw new Error('无效实验编号');
  }
  const result = await runPythonWorker('.tools/results-venv/bin/python', 'scripts/b08_results_worker.py',
    ['compare', '--store', resultStore(),
      '--reference', reference, '--candidate', candidate]);
  for (const media of [...result.reference_media, ...result.candidate_media]) {
    const sha = media.source_sha256;
    if (!/^[0-9a-f]{64}$/.test(sha) || !['.mp4', '.webm'].includes(path.extname(media.path).toLowerCase())) continue;
    resultMedia.set(sha, { path: path.join(resultStore(), 'results', 'blobs', sha.slice(0, 2), sha),
      mime: path.extname(media.path).toLowerCase() === '.mp4' ? 'video/mp4' : 'video/webm' });
  }
  return result;
});
ipcMain.handle('select-import', (event, operation_id, model) => {
  if (!window || event.sender !== window.webContents || typeof operation_id !== 'string' || typeof model !== 'string') throw new Error('无效选择');
  return importRequest({ action: 'select', operation_id, model });
});
ipcMain.handle('viewer-settle', async (event, operation, modelName, joints, limits) => {
  assertRenderer(event);
  if (typeof operation !== 'string' || !/^[0-9a-f-]{36}$/.test(operation) ||
      typeof modelName !== 'string' || !modelName.endsWith('.urdf') ||
      !joints || typeof joints !== 'object' || Array.isArray(joints) || Object.keys(joints).length > 256 ||
      Object.entries(joints).some(([name, value]) => typeof name !== 'string' || name.length > 160 ||
        typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 100) ||
      !limits || typeof limits !== 'object' || Array.isArray(limits) || Object.keys(limits).length > 256 ||
      Object.entries(limits).some(([name, enabled]) => name.length > 160 || typeof enabled !== 'boolean'))
    throw new Error('无效重力计算输入');
  const base = path.join(app.getPath('userData'), 'imports', operation);
  const record = JSON.parse(await fs.promises.readFile(path.join(base, 'report.json'), 'utf8'));
  const asset = record.assets.find(item => item.path === modelName);
  if (record.operation_id !== operation || record.status !== 'ready' || record.selected_model !== modelName ||
      !asset) throw new Error('模型尚未准备好');
  const modelFile = path.resolve(base, 'bundle', modelName);
  if (!modelFile.startsWith(path.resolve(base, 'bundle') + path.sep)) throw new Error('模型路径越界');
  const bytes = await fs.promises.readFile(modelFile);
  if (bytes.length !== asset.size || createHash('sha256').update(bytes).digest('hex') !== asset.sha256)
    throw new Error('已导入 URDF 的内容发生变化');
  return runPythonWorker('.tools/sim-venv/bin/python', 'scripts/viewer_gravity_worker.py',
    ['--model', modelFile, '--joints', JSON.stringify(joints), '--limits', JSON.stringify(limits)], 45000);
});
let cadSource = null;
let cadExchangeDirectory = null;
let cadMeshDirectory = null;
let pendingCadReturn = null;
function runPythonWorker(python, script, args, timeoutMs = 120000, extraEnv = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(path.join(root, python), [path.join(root, script), ...args],
      { cwd: root, env: { PATH: process.env.PATH, PYTHONPATH: path.join(root, 'python'), ...extraEnv }, stdio: ['ignore', 'pipe', 'pipe'] });
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
// WebCodex is a ChatGPT conversation tool, not a callable local model API.
// Requests remain in a private local queue. The user explicitly sends the
// handoff prompt into a connected ChatGPT web conversation.
const webcodexStore = () => smoke && process.env.URDFTOOLS_WEBCODEX_STORE ?
  process.env.URDFTOOLS_WEBCODEX_STORE : path.join(app.getPath('userData'), 'WebCodexAgent');
function webcodexBridge(args, timeoutMs = 160000) {
  const cliEnvironment = args[0] === 'run-cli' ?
    { HOME: process.env.HOME, CODEX_HOME: process.env.CODEX_HOME } : {};
  return runPythonWorker('.tools/model-venv/bin/python', 'scripts/webcodex_agent_bridge.py',
    ['--store', webcodexStore(), ...args], timeoutMs, cliEnvironment);
}
function agentMode(mode) {
  if (mode !== 'webcodex' && mode !== 'cli') throw new Error('无效 Agent 模式');
  return mode;
}
ipcMain.handle('webcodex-create-model', async (event, instruction, expectedRevision, mode = 'webcodex') => {
  assertRenderer(event);
  if (typeof instruction !== 'string' || !instruction.trim() || instruction.length > 2000 ||
    !Number.isSafeInteger(expectedRevision) || expectedRevision < 1) throw new Error('无效建模 Agent 输入或版本');
  return webcodexBridge(['create-model', '--mode', agentMode(mode), '--instruction', instruction,
    '--project', modelProject(), '--revision', String(expectedRevision)]);
});
ipcMain.handle('webcodex-create-analysis', async (event, instruction, mode = 'webcodex') => {
  assertRenderer(event);
  if (typeof instruction !== 'string' || !instruction.trim() || instruction.length > 2000)
    throw new Error('分析说明不能为空且不超过 2000 字');
  // This phase intentionally uses clearly labeled synthetic evaluation
  // fixtures. It NEVER silently treats a user's imported model as equivalent.
  return webcodexBridge(['create-analysis', '--mode', agentMode(mode), '--instruction', instruction]);
});
ipcMain.handle('webcodex-create-import-analysis', async (event, operation, instruction, mode = 'webcodex') => {
  assertRenderer(event);
  if (typeof operation !== 'string' || !/^[a-f0-9-]{36}$/.test(operation) ||
      typeof instruction !== 'string' || !instruction.trim() || instruction.length > 2000)
    throw new Error('无效 URDF 导入或分析指令');
  const base=path.join(app.getPath('userData'), 'imports', operation);
  const reportPath=path.join(base, 'report.json');
  const report=JSON.parse(await fs.promises.readFile(reportPath, 'utf8'));
  if (report.operation_id!==operation || report.status!=='ready' ||
      typeof report.selected_model!=='string' ||
      !report.models.some(model=>model.path===report.selected_model && model.status==='ready'))
    throw new Error('请先完成原始 URDF 模型导入');
  const bundleRoot=path.resolve(base,'bundle');
  const fullPath=path.resolve(bundleRoot,report.selected_model);
  if (!fullPath.startsWith(bundleRoot+path.sep) ||
      path.extname(fullPath).toLowerCase()!=='.urdf')
    throw new Error('导入模型不是可访问的 URDF 文件');
  const current=await fs.promises.realpath(fullPath);
  if (!current.startsWith(bundleRoot+path.sep)) throw new Error('URDF 模型路径跨出导入资源');
  return webcodexBridge(['create-urdf','--mode',agentMode(mode),'--instruction',instruction,'--urdf',current]);
});
ipcMain.handle('webcodex-create-result-analysis', async (event, reference, candidate, instruction, mode = 'webcodex') => {
  assertRenderer(event);
  if (typeof reference !== 'string' || !reference || reference.length > 160 ||
      typeof candidate !== 'string' || !candidate || candidate.length > 160 || reference === candidate ||
      typeof instruction !== 'string' || !instruction.trim() || instruction.length > 2000)
    throw new Error('无效的训练结果对比分析请求');
  return webcodexBridge(['create-result-analysis', '--mode', agentMode(mode),
    '--instruction', instruction, '--result-store', resultStore(),
    '--reference', reference, '--candidate', candidate]);
});
ipcMain.handle('webcodex-status', async (event, requestId) => {
  assertRenderer(event);
  if (typeof requestId !== 'string' || !/^[a-f0-9]{32}$/.test(requestId))
    throw new Error('无效 WebCodex 请求编号');
  return webcodexBridge(['status', '--id', requestId]);
});
ipcMain.handle('agent-cli-run', async (event, requestId) => {
  assertRenderer(event);
  if (typeof requestId !== 'string' || !/^[a-f0-9]{32}$/.test(requestId))
    throw new Error('无效 Agent 请求编号');
  return webcodexBridge(['run-cli', '--id', requestId], 300000);
});
ipcMain.handle('webcodex-copy', (event, prompt) => {
  assertRenderer(event);
  if (typeof prompt !== 'string' || prompt.length > 4500 || !prompt.includes('@web-codex-tunnel'))
    throw new Error('只允许复制已声明的 WebCodex 提示');
  require('electron').clipboard.writeText(prompt);
  return true;
});
ipcMain.handle('webcodex-open', async (event, requestId) => {
  assertRenderer(event);
  if (typeof requestId !== 'string' || !/^[a-f0-9]{32}$/.test(requestId))
    throw new Error('无效 WebCodex 请求编号');
  const ticket = await webcodexBridge(['status', '--id', requestId]);
  if (ticket.status !== 'awaiting_chatgpt_web_reply' || !ticket.prompt)
    throw new Error('此请求已完成或不可交接');
  require('electron').clipboard.writeText(ticket.prompt);
  await require('electron').shell.openExternal('https://chatgpt.com/');
  return {request_id: requestId, copied: true, opened: true};
});

let agentBusy = false;
async function agentRequest(action, payload) {
  if (agentBusy) throw new Error('已有建模建议正在处理');
  agentBusy = true;
  let temporary;
  try {
    temporary = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'agent-request-'));
    const request = path.join(temporary, 'request.json');
    await fs.promises.writeFile(request, JSON.stringify(payload), { mode: 0o600 });
    return await runPythonWorker('.tools/model-venv/bin/python', 'scripts/a01_agent_model.py',
      [action, '--project', modelProject(), '--request', request], 240000,
      { HOME: process.env.HOME, CODEX_HOME: process.env.CODEX_HOME });
  } finally { agentBusy = false; if (temporary) await fs.promises.rm(temporary, { recursive: true, force: true }); }
}
// Legacy Codex CLI suggestion endpoint intentionally disabled: web bridge only.
ipcMain.handle('agent-apply', async (event, proposalId) => {
  assertRenderer(event);
  if (typeof proposalId !== 'string' || !/^[0-9a-f]{32}$/.test(proposalId)) throw new Error('无效建议编号');
  const result = await agentRequest('apply', { proposal_id: proposalId, human_confirmed: true });
  const step = path.join(result.package, 'assembly.step');
  const assembly = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/model_assembly.py',
    [result.package, '--output', step], 180000);
  const discovery = await cadWorker([step]);
  cadSource = step;
  await fs.promises.rm(path.join(modelProject(), 'return.json'), { force: true });
  return { ...result, assembly, discovery };
});
ipcMain.handle('model-current', async event => {
  assertRenderer(event);
  const project = modelProject();
  const pointer = path.join(project, 'current.json');
  if (!fs.existsSync(pointer)) return { revision: 0, recipe: { schema_version: 1, parts: [] }, built: null };
  const current = JSON.parse(await fs.promises.readFile(pointer, 'utf-8'));
  const revision = path.join(project, 'revisions', String(current.revision).padStart(6, '0'));
  const recipe = JSON.parse(await fs.promises.readFile(path.join(revision, 'recipe.json'), 'utf-8'));
  const report = JSON.parse(await fs.promises.readFile(path.join(revision, 'report.json'), 'utf-8'));
  let step = path.join(revision, 'assembly.step');
  let configuration = null;
  let returnWarning = null;
  const returnPath = path.join(project, 'return.json');
  if (fs.existsSync(returnPath)) {
    try {
      const saved = JSON.parse(await fs.promises.readFile(returnPath, 'utf-8'));
      if (saved.model_revision !== current.revision) throw new Error('回流记录对应旧建模版本');
      const hash = createHash('sha256').update(await fs.promises.readFile(saved.step)).digest('hex');
      if (hash !== saved.sha256 || saved.configuration.source_sha256 !== hash) throw new Error('回流 STEP 或配置已变化');
      step = saved.step; configuration = saved.configuration;
    } catch (error) { returnWarning = String(error); }
  }
  if (!fs.existsSync(step)) return { revision: current.revision, recipe, built: null,
    returnWarning: returnWarning || '本版本缺少装配 STEP，请重新生成' };
  let discovery;
  if (configuration) {
    const directory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'model-restore-'));
    try {
      const configPath = path.join(directory, 'config.json');
      await fs.promises.writeFile(configPath, JSON.stringify(configuration), { mode: 0o600 });
      discovery = await cadWorker([step, '--config', configPath]);
    } catch (error) {
      returnWarning = `回流配置未通过校验：${String(error)}`;
      step = path.join(revision, 'assembly.step');
      discovery = await cadWorker([step]);
      configuration = null;
    } finally { await fs.promises.rm(directory, { recursive: true, force: true }); }
  } else discovery = await cadWorker([step]);
  cadSource = step;
  cadExchangeDirectory = configuration ? path.dirname(step) : null;
  const digest = createHash('sha256').update(await fs.promises.readFile(step)).digest('hex');
  return { revision: current.revision, recipe,
    built: { revision: current.revision, package: revision, report,
      assembly: { path: step, sha256: digest, parts: discovery.draft.parts.map(part => part.name) }, discovery },
    returnWarning };
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
    await fs.promises.rm(path.join(modelProject(), 'return.json'), { force: true });
    return { ...result, assembly, discovery };
  } finally { await fs.promises.rm(temporary, { recursive: true, force: true }); }
});
ipcMain.handle('model-reconcile', async (event, config) => {
  assertRenderer(event);
  if (!cadSource || !config || typeof config !== 'object') throw new Error('请先生成建模版本并完成 Link 分组');
  const encoded = JSON.stringify(config);
  if (encoded.length > 1024*1024 || typeof config.source_sha256 !== 'string') throw new Error('无效的来源配置');
  const currentHash = createHash('sha256').update(await fs.promises.readFile(cadSource)).digest('hex');
  if (currentHash !== config.source_sha256) throw new Error('建模来源已变化，请先重新生成');
  const fixture = smoke ? process.env.URDFTOOLS_MODEL_RETURN_SMOKE : null;
  let source = fixture;
  if (!source) {
    const choice = await dialog.showOpenDialog(window, { properties: ['openFile'],
      filters: [{ name: 'FreeCAD FCStd', extensions: ['FCStd'] }] });
    if (choice.canceled) return null;
    source = choice.filePaths[0];
  }
  if (path.extname(source).toLowerCase() !== '.fcstd') throw new Error('回流文件必须是 FCStd');
  const mapping = {};
  for (const link of config.links || []) for (const part of link.parts || []) {
    if (Object.hasOwn(mapping, part)) throw new Error('一个 CAD 零件被分给多个 Link');
    mapping[part] = link.name;
  }
  const directory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'cad-return-'));
  try {
    const step = path.join(directory, 'returned.step');
    const mapPath = path.join(directory, 'mapping.json');
    await fs.promises.writeFile(mapPath, JSON.stringify(mapping), { mode: 0o600 });
    const exchange = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/freecad_bridge.py',
      [source, '--output', step], 300000);
    const proposal = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/model_reconcile.py',
      [cadSource, step, '--baseline-sha256', currentHash, '--mapping', mapPath], 180000);
    if (pendingCadReturn) await fs.promises.rm(pendingCadReturn.directory, { recursive: true, force: true });
    pendingCadReturn = { directory, step, proposal, baseline: cadSource, baselineHash: currentHash,
      source, sourceHash: exchange.source_sha256 };
    return { proposal, exchange };
  } catch (error) {
    await fs.promises.rm(directory, { recursive: true, force: true });
    throw error;
  }
});
ipcMain.handle('model-accept-return', async (event, config) => {
  assertRenderer(event);
  const pending = pendingCadReturn;
  if (!pending || pending.proposal.status !== 'review_required' || pending.proposal.conflicts.length) {
    throw new Error('回流存在冲突或没有待审阅方案，不能应用');
  }
  if (!config || config.source_sha256 !== pending.baselineHash || cadSource !== pending.baseline) {
    throw new Error('原始建模配置已变化，请重新比较');
  }
  const candidateHash = createHash('sha256').update(await fs.promises.readFile(pending.step)).digest('hex');
  if (candidateHash !== pending.proposal.returned_sha256) throw new Error('回流 STEP 在审阅后发生变化');
  const rename = Object.fromEntries(pending.proposal.relinks.map(item => [item.baseline_part, item.returned_part]));
  const fresh = await cadWorker([pending.step]);
  const updated = { ...config, source_sha256: fresh.draft.source_sha256,
    links: config.links.map(link => ({ ...link, parts: link.parts.map(part => rename[part]) })),
    joints: config.joints.map(joint => ({ ...joint, confirmed: false })) };
  const directory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'cad-return-check-'));
  try {
    const configPath = path.join(directory, 'config.json');
    await fs.promises.writeFile(configPath, JSON.stringify(updated), { mode: 0o600 });
    const checked = await cadWorker([pending.step, '--config', configPath]);
    const returnPath = path.join(modelProject(), 'return.json');
    const record = { model_revision: JSON.parse(await fs.promises.readFile(path.join(modelProject(), 'current.json'), 'utf-8')).revision,
      step: pending.step, sha256: candidateHash, baseline_sha256: pending.baselineHash,
      source_fcstd: pending.source, source_sha256: pending.sourceHash,
      configuration: updated, accepted_at: new Date().toISOString() };
    const temporaryRecord = returnPath + '.partial-' + randomBytes(6).toString('hex');
    await fs.promises.writeFile(temporaryRecord, JSON.stringify(record), { mode: 0o600 });
    await fs.promises.rename(temporaryRecord, returnPath);
    if (cadExchangeDirectory) await fs.promises.rm(cadExchangeDirectory, { recursive: true, force: true });
    cadSource = pending.step;
    cadExchangeDirectory = pending.directory;
    pendingCadReturn = null;
    return checked;
  } finally { await fs.promises.rm(directory, { recursive: true, force: true }); }
});
const cadDraftStore = () => createCadDraftStore(path.join(app.getPath('userData'), 'cad-draft'));
let cadDraftWrite = Promise.resolve();
let cadDraftPending = 0;
function queueCadDraftWrite(action) {
  cadDraftPending += 1;
  cadDraftWrite = cadDraftWrite.catch(() => {}).then(action).finally(() => { cadDraftPending -= 1; });
  return cadDraftWrite;
}
async function importCadSource(original, persistDraft = true) {
  if (typeof original !== 'string' || !original) throw new Error('请选择本地 CAD 文件');
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
    const meshDirectory = await fs.promises.mkdtemp(path.join(app.getPath('userData'), 'cad-mesh-'));
    let meshParts;
    try {
      const meshResult = await runPythonWorker('.tools/cad-venv/bin/python', 'scripts/cad_part_meshes.py',
        [source, meshDirectory], 300000);
      const token = randomBytes(16).toString('hex');
      meshParts = meshResult.parts.map(item => ({name: item.name,
        url: `urdftools://cad-mesh/${token}/${item.file}`, color: item.color}));
      if (meshParts.length !== result.draft.parts.length ||
          meshParts.some((item, index) => item.name !== result.draft.parts[index].name))
        throw new Error('CAD mesh parts do not match imported assembly');
      cadMeshAssets.clear();
      meshResult.parts.forEach(item => cadMeshAssets.set(`${token}/${item.file}`,
        { path: path.join(meshDirectory, item.file), size: item.size }));
    } catch (cause) {
      await fs.promises.rm(meshDirectory, { recursive: true, force: true });
      throw cause;
    }
    if (cadMeshDirectory) await fs.promises.rm(cadMeshDirectory, { recursive: true, force: true });
    cadMeshDirectory = meshDirectory;
    if (cadExchangeDirectory) await fs.promises.rm(cadExchangeDirectory, { recursive: true, force: true });
    cadSource = source;
    cadExchangeDirectory = generatedDirectory;
    generatedDirectory = null;
    if (persistDraft) await queueCadDraftWrite(() => cadDraftStore().begin(source, result.draft, exchangeReport));
    return { ...result, exchangeReport, meshParts };
  } finally {
    if (generatedDirectory) await fs.promises.rm(generatedDirectory, { recursive: true, force: true });
  }
}
ipcMain.handle('choose-cad-step', async event => {
  assertRenderer(event);
  const fixture = smoke ? (process.env.URDFTOOLS_CAD_EXCHANGE_SMOKE || process.env.URDFTOOLS_CAD_WIZARD_SMOKE || process.env.URDFTOOLS_CAD_AXIS_SMOKE) : null;
  if (fixture) return importCadSource(fixture);
  const choice = await dialog.showOpenDialog(window, { properties: ['openFile'],
    filters: [{ name: 'STEP / STP / FreeCAD / IGES / BREP', extensions: ['step', 'stp', 'FCStd', 'igs', 'iges', 'brep', 'brp'] }] });
  if (choice.canceled) return null;
  return importCadSource(choice.filePaths[0]);
});
ipcMain.handle('import-cad-file', async (event, source) => {
  assertRenderer(event);
  if (typeof source !== 'string' || !path.isAbsolute(source)) throw new Error('请拖入本地 CAD 文件');
  return importCadSource(source);
});
ipcMain.handle('cad-draft-load', async event => {
  assertRenderer(event);
  await cadDraftWrite;
  const record = await cadDraftStore().read();
  if (!record) return null;
  const discovery = await importCadSource(cadDraftStore().sourcePath(record), false);
  if (discovery.draft.source_sha256 !== record.source_sha256)
    throw new Error('CAD 暂存源文件已改变，请重新导入原始模型');
  discovery.draft.source_name = record.source_name;
  discovery.exchangeReport = record.exchange_report;
  const ui = record.ui?.source_sha256 === record.source_sha256 &&
    record.ui?.config?.source_sha256 === record.source_sha256 ? record.ui : null;
  return { discovery, ui, updated_at: record.updated_at };
});
ipcMain.handle('cad-draft-save', async (event, ui) => {
  assertRenderer(event);
  return queueCadDraftWrite(() => cadDraftStore().save(ui));
});
ipcMain.handle('cad-draft-clear', async event => {
  assertRenderer(event);
  await queueCadDraftWrite(() => cadDraftStore().clear());
  return true;
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
    await cadWorker([cadSource, '--config', configPath, '--preview', previewPath, '--mesh-preview']);
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
    return { path: destination, sha256: exported.sha256, validation, massProperties: exported.metadata?.links || [] };
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
    cwd: root, env: { PATH: process.env.PATH, PYTHONPATH: path.join(root, 'python'), URDFTOOLS_SESSION_TOKEN: token }, stdio: ['ignore', 'pipe', 'pipe']
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
      // Electron's built-in Ctrl+- zoom persisted at the webContents level and the
      // corresponding Ctrl++ accelerator varies by keyboard layout (often Ctrl+Shift+=).
      // Start at 100% and handle both directions here so panels cannot get stranded small.
      window.webContents.setZoomLevel(0);
      window.webContents.on('before-input-event', (inputEvent, input) => {
        if (input.type !== 'keyDown' || (!input.control && !input.meta) || input.alt) return;
        const key = String(input.key || '').toLowerCase();
        const code = String(input.code || '').toLowerCase();
        const zoomOut = key === '-' || key === '_' || key === 'subtract' || code === 'minus' || code === 'numpadsubtract';
        const zoomIn = key === '+' || key === '=' || key === 'add' || code === 'equal' || code === 'numpadadd';
        if (key === '0' || code === 'digit0' || code === 'numpad0') {
          inputEvent.preventDefault();
          window.webContents.setZoomLevel(0);
        } else if (zoomOut || zoomIn) {
          inputEvent.preventDefault();
          const current = window.webContents.getZoomLevel();
          window.webContents.setZoomLevel(Math.max(-3, Math.min(4, current + (zoomIn ? 0.5 : -0.5))));
        }
      });
      window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
      window.webContents.on('will-navigate', event => event.preventDefault());
      window.webContents.on('render-process-gone', (_event, details) =>
        console.error(JSON.stringify({ event: 'viewer_renderer_gone', reason: details.reason, exitCode: details.exitCode })));
      if (!smoke) window.webContents.on('console-message', ({ level, message, sourceId, lineNumber }) => {
        if (level === 'error') console.error(JSON.stringify({ event: 'viewer_console_error', message, sourceId, lineNumber }));
      });
      await window.loadFile(smoke && process.env.URDFTOOLS_SMOKE_WEB_DIR ?
        path.join(process.env.URDFTOOLS_SMOKE_WEB_DIR, 'index.html') : path.join(root, 'dist/web/index.html'));
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
        if (title !== '打开机器人模型') throw new Error('Renderer did not mount');
        const isolated = await window.webContents.executeJavaScript(`typeof require === 'undefined' && window.urdftools.version === '0.1.0'`);
        if (!isolated) throw new Error('Renderer isolation/preload failed');
        if (process.env.URDFTOOLS_CAD_DRAFT_RESTORE_SMOKE) {
          const until = Date.now() + 90000;
          const verifyFont = Boolean(process.env.URDFTOOLS_FONT_RESTORE_SMOKE);
          let restored = null;
          while (Date.now() < until) {
            restored = await window.webContents.executeJavaScript(`(() => ({
              confirmed:document.querySelector('.cad-wizard')?.textContent.includes('1/1 个关节已确认'),
              density:document.querySelector('input[aria-label="BasePart density"]')?.value,
              step:document.querySelector('.cad-flow button[aria-current="step"]')?.textContent.trim(),
              fontSize:document.querySelector('.text-size-value')?.textContent
            }))()`);
            if (restored.confirmed && restored.density === '2700' &&
                restored.step?.includes('验证导出') && (!verifyFont || restored.fontSize === '110%')) break;
            await new Promise(resolve => setTimeout(resolve, 80));
          }
          if (!restored?.confirmed || restored.density !== '2700' ||
              !restored.step?.includes('验证导出') || (verifyFont && restored.fontSize !== '110%') ||
              !cadSource?.includes('cad-draft'))
            throw new Error('CAD draft restart restore mismatch: ' + JSON.stringify(restored));
          console.log(JSON.stringify({event:'desktop_cad_draft_restore_smoke', restored, cachedSource:true}));
        }
        if (process.env.URDFTOOLS_WORKBENCH_SMOKE) {
          await require(path.join(root, 'scripts/urdf_workbench_smoke_hook.cjs'))(window, process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
        }
        if (process.env.URDFTOOLS_Q01_SMOKE) {
          await window.webContents.executeJavaScript("document.querySelector('button[aria-label=\"打开内置示例\"]').click()");
          let loaded = false;
          for (let tries = 0; tries < 240; tries++) {
            loaded = await window.webContents.executeJavaScript(`(() => {
              const v = document.querySelector('[data-import-status="ready"] [aria-label="三维机器人查看器"]');
              return !!v && Number(v.dataset.treeLinkCount) === 2 &&
                Number(v.dataset.treeJointCount) === 1 && Number(v.dataset.meshCount) >= 1;
            })()`);
            if (loaded) break;
            await new Promise(resolve => setTimeout(resolve, 100));
          }
          if (!loaded) throw new Error('Bundled example was not imported and rendered: ' +
            await window.webContents.executeJavaScript("document.querySelector('main')?.textContent.slice(-700)"));
          const summary = await window.webContents.executeJavaScript(`(() => {
            const v = document.querySelector('[aria-label="三维机器人查看器"]');
            return {links: Number(v.dataset.treeLinkCount), joints: Number(v.dataset.treeJointCount),
              meshes: Number(v.dataset.meshCount), status: document.querySelector('[data-import-status]')?.dataset.importStatus};
          })()`);
          if (summary.status !== 'ready' || summary.links !== 2 || summary.joints !== 1 || summary.meshes < 1)
            throw new Error('Bundled example semantic mismatch: ' + JSON.stringify(summary));
          const screenshot = (await window.webContents.capturePage()).toPNG();
          if (screenshot.length < 1000) throw new Error('Bundled example screenshot empty');
          if (process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR)
            fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'portable-example.png'), screenshot);
          console.log(JSON.stringify({event:'q01_portable_example', ...summary, screenshotBytes:screenshot.length,
            isolated, sandbox:window.webContents.getLastWebPreferences().sandbox}));
          app.quit();
          return;
        }
        if (process.env.URDFTOOLS_WEBCODEX_SMOKE) {
          const capabilities=await window.webContents.executeJavaScript("({create:typeof window.urdftools.webcodexCreateAnalysis,status:typeof window.urdftools.webcodexStatus,copy:typeof window.urdftools.webcodexCopyPrompt,open:typeof window.urdftools.webcodexOpen,cli:typeof window.urdftools.agentCliRun})");
          if (Object.values(capabilities).some(value=>value!=='function'))
            throw new Error('WebCodex Electron preload bridge absent');
          await window.webContents.executeJavaScript("([...document.querySelectorAll('aside button')].find(button=>button.textContent.includes('创建网页 ChatGPT 分析请求'))).click()");
          let pending=false;
          for(let tries=0;tries<150;tries++) {
            pending=await window.webContents.executeJavaScript("document.querySelector('[data-webcodex-status=\"awaiting_chatgpt_web_reply\"]')!==null");
            if(pending) break;
            await new Promise(resolve=>setTimeout(resolve,100));
          }
          if(!pending) throw new Error('React WebCodex request was not created');
          const requestId=await window.webContents.executeJavaScript("document.querySelector('[data-webcodex-status] code')?.textContent");
          if(!/^[0-9a-f]{32}$/.test(requestId)) throw new Error('Invalid WebCodex request id');
          const pendingResponse=await webcodexBridge(['status','--id',requestId]);
          if(pendingResponse.status!=='awaiting_chatgpt_web_reply' ||
             !pendingResponse.prompt.includes('@web-codex-tunnel'))
            throw new Error('WebCodex bridge pending status mismatch');
          await window.webContents.executeJavaScript("([...document.querySelectorAll('aside button')].find(button=>button.textContent.includes('复制 WebCodex 对话提示'))).click()");
          const {clipboard}=require('electron');
          const copied=clipboard.readText();
          if(!copied.includes(requestId) || !copied.includes('@web-codex-tunnel'))
            throw new Error('WebCodex handoff was not copied');
          if(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR)
            fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR,'webcodex-agent.png'),
                             (await window.webContents.capturePage()).toPNG());
          const imported=await importRequest({action:'import',
            source:path.join(root,'tests/fixtures/E00/quadruped_zero_axis.urdf')});
          if(imported.status!=='ready') throw new Error('Imported URDF fixture failed');
          const analysis=await window.webContents.executeJavaScript(
            "window.urdftools.webcodexCreateImportedAnalysis("+
            JSON.stringify(imported.operation_id)+",'请定位关节零轴并给出证据ID')");
          const importedRow=JSON.parse(fs.readFileSync(analysis.request_path,'utf8'));
          if(analysis.status!=='awaiting_chatgpt_web_reply' ||
             importedRow.payload.bundle.evidence[0]?.rule!=='invalid_joint_axis' ||
             importedRow.payload.original_urdf_not_sent!==true)
            throw new Error('Imported URDF actual IPC/static evidence invalid');
          const cliDraft=await window.webContents.executeJavaScript(
            "window.urdftools.webcodexCreateAnalysis('检查五类原因','cli')");
          const cliRow=JSON.parse(fs.readFileSync(cliDraft.request_path,'utf8'));
          if(cliDraft.status!=='awaiting_codex_cli_run' || cliDraft.prompt!==null ||
             cliRow.policy.provider!=='codex_cli_chatgpt' || cliRow.policy.no_codex_cli!==false)
            throw new Error('Explicit CLI request mode or consent boundary invalid');
          await window.webContents.executeJavaScript(
            "document.querySelector('input[name=\"analysis-agent-mode\"][value=\"cli\"]')?.click()");
          const cliSelected=await window.webContents.executeJavaScript(
            "document.querySelector('input[name=\"analysis-agent-mode\"][value=\"cli\"]')?.checked && [...document.querySelectorAll('aside button')].some(b=>b.textContent.includes('运行 Codex CLI 分析'))");
          if(!cliSelected) throw new Error('CLI mode is not selectable in Electron renderer');
          console.log(JSON.stringify({event:'desktop_webcodex_imported_urdf_smoke',
            source:'unverified_imported_fixture',rule:'invalid_joint_axis',
            xml_not_submitted:true,local_file_checked:true}));
          console.log(JSON.stringify({event:'desktop_webcodex_agent_smoke',
            request_id:requestId,clipboard_verified:true,model_cli_calls:0,
            web_chatgpt_requested:false,pending:true,source:'synthetic_fixture',
            renderer_isolated:isolated}));
          console.log(JSON.stringify({event:'desktop_agent_dual_mode_smoke',
            cli_request_created:true,cli_model_called:false,webcodex_request_created:true,
            model_modes_selectable:true}));
        }

        if (process.env.URDFTOOLS_MODEL_RESTORE_SMOKE) {
          await window.webContents.executeJavaScript(`([...document.querySelectorAll('nav button')].find(button => button.textContent === '建模')).click()`);
          const deadline = Date.now() + 15000;
          let restored = false;
          while (Date.now() < deadline) {
            restored = await window.webContents.executeJavaScript(`document.querySelector('[aria-label="STEP 转换向导"]')?.textContent.includes('0/1 个关节已确认') && document.querySelector('main')?.textContent.includes('returned.step')`);
            if (restored) break;
            await new Promise(resolve => setTimeout(resolve, 50));
          }
          if (!restored) throw new Error('Accepted FreeCAD return was not restored after restart');
          console.log(JSON.stringify({ event: 'desktop_model_restore_smoke', restored: true }));
        }
        if (process.env.URDFTOOLS_MODEL_SMOKE) {
          const runModelSmoke = require(path.join(root, 'scripts/m01_desktop_smoke_hook.cjs'));
          await runModelSmoke(window, process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
          if (process.env.URDFTOOLS_AGENT_SMOKE) {
            const runAgentSmoke = require(path.join(root, 'scripts/a01_desktop_smoke_hook.cjs'));
            await runAgentSmoke(window, process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
          }
          if (process.env.URDFTOOLS_MODEL_RETURN_SMOKE) {
            const runReturnSmoke = require(path.join(root, 'scripts/m02_desktop_smoke_hook.cjs'));
            await runReturnSmoke(window, process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
          }
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
          } else if (process.env.URDFTOOLS_Q00_VIEWER_SMOKE) {
            await waitFor(`Number(document.querySelector('[data-mesh-count]')?.dataset.meshCount) >= 2`);
            await waitFor(`document.querySelector('input[aria-label="OffsetPart_joint"]') !== null`);
            const before = await window.webContents.executeJavaScript(
              `document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
            await window.webContents.executeJavaScript(
              `document.querySelector('input[aria-label="OffsetPart_joint"]').focus()`);
            window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
            window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
            await waitFor(`Number(document.querySelector('input[aria-label="OffsetPart_joint"]')?.value) > 0.99`);
            const after = await window.webContents.executeJavaScript(
              `document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
            if (!after || before === after) throw new Error('STEP-exported joint did not rotate');
            const meshCount = await window.webContents.executeJavaScript(
              `Number(document.querySelector('[data-mesh-count]').dataset.meshCount)`);
            fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-roundtrip-viewer.png'),
              (await window.webContents.capturePage()).toPNG());
            window.webContents.debugger.detach();
            console.log(JSON.stringify({event: 'desktop_q00_viewer_smoke', meshCount,
              jointPoseChanged: true, exportedZip: fixture}));
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
          if (!details.includes('BaseBracket') || !details.includes('ArmLink') || !details.includes('0/1 个关节已确认')) {
            throw new Error('FreeCAD exchange failed to show two parts and explicit loss report');
          }
          const png = (await window.webContents.capturePage()).toPNG();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'freecad-exchange.png'), png);
          console.log(JSON.stringify({ event: 'desktop_freecad_exchange_smoke', partCount: 2,
            lossVisible: true, screenshotBytes: png.length }));
        }
        if (process.env.URDFTOOLS_CAD_AXIS_SMOKE) {
          const waitForAxis = async expression => {
            const until = Date.now() + 120000;
            while (Date.now() < until) {
              if (await window.webContents.executeJavaScript(expression)) return;
              await new Promise(resolve => setTimeout(resolve, 100));
            }
            throw new Error('CAD real axis UI timeout: ' + expression + ' | ' +
              await window.webContents.executeJavaScript("document.querySelector('.cad-wizard')?.textContent.slice(-900)"));
          };
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('nav[aria-label="工作区"] button')].find(b => b.textContent === 'CAD转换URDF').click()`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b => b.textContent === '选择 CAD 文件').click()`);
          await waitForAxis(`document.querySelector('[aria-label="选择零件 shenti"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="选择零件 shenti"]').click()`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-tree-toolbar .cad-primary').click()`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-create-dialog .cad-primary').click()`);
          await waitForAxis(`document.querySelector('[aria-label="选择零件 fake_servo_2_1"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="选择零件 fake_servo_2_1"]').click()`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-tree-toolbar .cad-primary').click()`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-create-dialog .cad-primary').click()`);
          await waitForAxis(`document.querySelector('[aria-label="编辑关节 link_001_joint"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="编辑关节 link_001_joint"]').click()`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-joint-actions button')].find(b => b.textContent.includes('显示全部轴')).click()`);
          await waitForAxis(`Number(document.querySelector('.cad-part-canvas')?.dataset.candidateCount) >= 1`);
          const count = await window.webContents.executeJavaScript(`Number(document.querySelector('.cad-part-canvas').dataset.candidateCount)`);
          const point = await window.webContents.executeJavaScript(`JSON.parse(document.querySelector('.cad-part-canvas').dataset.candidateScreenPositions)[0]`);
          await window.webContents.executeJavaScript(`(() => {
            const canvas=document.querySelector('.cad-part-canvas canvas'); const rect=canvas.getBoundingClientRect();
            canvas.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,button:0,clientX:rect.left+${point[0]},clientY:rect.top+${point[1]}}));
          })()`);
          await waitForAxis(`document.querySelector('.cad-part-canvas')?.dataset.hoveredCandidate === '0'`);
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-real-axis-hover.png'),
            (await window.webContents.capturePage()).toPNG());
          await window.webContents.executeJavaScript(`(() => {
            const canvas=document.querySelector('.cad-part-canvas canvas'); const rect=canvas.getBoundingClientRect();
            const x=rect.left+${point[0]}, y=rect.top+${point[1]};
            canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,clientX:x,clientY:y}));
            canvas.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,clientX:x,clientY:y}));
          })()`);
          await waitForAxis(`document.querySelector('.cad-part-canvas')?.dataset.candidateCount === '0'`);
          const png = (await window.webContents.capturePage()).toPNG();
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-real-axis.png'), png);
          console.log(JSON.stringify({event:'desktop_cad_real_axis_smoke',candidateCount:count,hovered:true,selected:true,
            candidateScreen:point, modelPosition:await window.webContents.executeJavaScript(`document.querySelector('.cad-part-canvas').dataset.modelPosition`),
            screenshotBytes:png.length}));
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
          await waitForCad(`document.querySelector('[aria-label="选择零件 BasePart"]') !== null`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('nav[aria-label="工作区"] button')].find(b => b.textContent === '评估').click()`);
          await waitForCad(`document.querySelector('.tool-workspace[aria-label="评估"]:not([hidden])') !== null`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('nav[aria-label="工作区"] button')].find(b => b.textContent === 'CAD转换URDF').click()`);
          await waitForCad(`document.querySelector('[aria-label="选择零件 BasePart"]') !== null && document.querySelector('[aria-label="CAD 转 URDF 工作区"]')?.textContent.includes('two_part_mm.step')`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="选择零件 BasePart"]').click()`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-tree-toolbar .cad-primary').click()`);
          await waitForCad(`document.querySelector('[role="dialog"][aria-label="创建 Link"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-create-dialog .cad-primary').click()`);
          await waitForCad(`document.querySelector('[aria-label="选择零件 OffsetPart"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="选择零件 OffsetPart"]').click()`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-tree-toolbar .cad-primary').click()`);
          await waitForCad(`document.querySelector('[role="dialog"][aria-label="创建 Link"]') !== null`);
          await window.webContents.executeJavaScript(`(() => {
            const el=document.querySelector('[aria-label="新 Link 名称"]');
            const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
            setter.call(el,'OffsetPart'); el.dispatchEvent(new Event('input',{bubbles:true}));
          })()`);
          await waitForCad(`document.querySelector('[aria-label="新 Link 名称"]')?.value === 'OffsetPart'`);
          await window.webContents.executeJavaScript(`document.querySelector('.cad-create-dialog .cad-primary').click()`);
          await waitForCad(`document.querySelector('[aria-label="编辑关节 OffsetPart_joint"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="显示 Link OffsetPart"]').click()`);
          await waitForCad(`document.querySelector('[aria-label="隐藏 Link OffsetPart"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="隐藏 Link OffsetPart"]').click()`);
          await waitForCad(`document.querySelector('[aria-label="显示 Link OffsetPart"]') !== null`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="编辑关节 OffsetPart_joint"]').click()`);
          await waitForCad(`document.querySelector('[aria-label="OffsetPart_joint type"]') !== null`);
          await waitForCad(`document.querySelector('.cad-part-canvas')?.dataset.jointOrigin?.length > 0 && document.querySelector('.cad-part-canvas')?.dataset.jointAxis?.length > 0`);
          await new Promise(resolve => setTimeout(resolve, 180));
          fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-joint-editor.png'), (await window.webContents.capturePage()).toPNG());
          if (process.env.URDFTOOLS_FONT_SMOKE) {
            const beforeFonts = await window.webContents.executeJavaScript(`(() => ({
              panelZoom:parseFloat(getComputedStyle(document.querySelector('.cad-joint-work-window .floating-panel-body')).zoom),
              titleHeight:document.querySelector('.cad-joint-work-window .floating-panel-head strong').getBoundingClientRect().height,
              fixedButtonHeight:document.querySelector('.cad-flow button').getBoundingClientRect().height
            }))()`);
            await window.webContents.executeJavaScript(`(() => {
              const handle=document.querySelector('.cad-joint-work-window .resize-ne');
              handle.setPointerCapture=()=>{};
              const rect=handle.getBoundingClientRect(), x=rect.left+rect.width/2, y=rect.top+rect.height/2;
              handle.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:1,button:0,clientX:x,clientY:y}));
              handle.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerId:1,button:0,buttons:1,clientX:x+140,clientY:y-110}));
              handle.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:1,button:0,clientX:x+140,clientY:y-110}));
            })()`);
            await waitForCad(`parseFloat(getComputedStyle(document.querySelector('.cad-joint-work-window .floating-panel-body')).zoom)>1.2`);
            await window.webContents.executeJavaScript(`document.querySelector('[aria-label="放大固定栏字体"]').click()`);
            await waitForCad(`document.querySelector('.text-size-value')?.textContent === '110%'`);
            const afterFonts = await window.webContents.executeJavaScript(`(() => ({
              panelZoom:parseFloat(getComputedStyle(document.querySelector('.cad-joint-work-window .floating-panel-body')).zoom),
              titleHeight:document.querySelector('.cad-joint-work-window .floating-panel-head strong').getBoundingClientRect().height,
              fixedButtonHeight:document.querySelector('.cad-flow button').getBoundingClientRect().height,
              stored:localStorage.getItem('urdftools:fixed-text-scale:v1')
            }))()`);
            if (afterFonts.panelZoom <= beforeFonts.panelZoom * 1.2 ||
                afterFonts.titleHeight <= beforeFonts.titleHeight * 1.2 ||
                afterFonts.fixedButtonHeight <= beforeFonts.fixedButtonHeight * 1.05 ||
                afterFonts.stored !== '1.1')
              throw new Error('Font scaling interaction mismatch: ' + JSON.stringify({beforeFonts, afterFonts}));
            fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-font-scale.png'),
              (await window.webContents.capturePage()).toPNG());
            console.log(JSON.stringify({event:'desktop_font_scale_smoke',beforeFonts,afterFonts}));
          }
          await window.webContents.executeJavaScript(`(() => {
            const canvas = document.querySelector('.cad-part-canvas canvas');
            const bounds = canvas.getBoundingClientRect();
            for (const fx of [0.35,0.4,0.45,0.5,0.55,0.6,0.65]) for (const fy of [0.45,0.5,0.55]) {
              const x = bounds.left + bounds.width * fx, y = bounds.top + bounds.height * fy;
              canvas.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, button: 0, clientX: x, clientY: y}));
              canvas.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, button: 0, clientX: x, clientY: y}));
            }
          })()`);
          await waitForCad(`document.querySelector('.cad-controls [role="status"]')?.textContent.includes('已从') === true`);
          const beforeDrag = await window.webContents.executeJavaScript(`(() => {
            const el=document.querySelector('.cad-part-canvas');
            return {model:el.dataset.modelQuaternion,camera:el.dataset.cameraPosition};
          })()`);
          await window.webContents.executeJavaScript(`(() => {
            const canvas=document.querySelector('.cad-part-canvas canvas');
            const bounds=canvas.getBoundingClientRect();
            const x=bounds.left+bounds.width*0.5, y=bounds.top+bounds.height*0.5;
            canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,clientX:x,clientY:y}));
            canvas.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,button:0,clientX:x+70,clientY:y+30}));
            canvas.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:0,clientX:x+70,clientY:y+30}));
          })()`);
          await waitForCad(`document.querySelector('.cad-part-canvas')?.dataset.modelQuaternion !== '${beforeDrag.model}'`);
          const afterDrag = await window.webContents.executeJavaScript(`(() => {
            const el=document.querySelector('.cad-part-canvas');
            return {model:el.dataset.modelQuaternion,camera:el.dataset.cameraPosition};
          })()`);
          if (beforeDrag.camera !== afterDrag.camera) throw new Error('CAD camera moved instead of robot');
          const beforePan = await window.webContents.executeJavaScript(`document.querySelector('.cad-part-canvas').dataset.modelPosition`);
          await window.webContents.executeJavaScript(`(() => {
            const canvas=document.querySelector('.cad-part-canvas canvas');
            const bounds=canvas.getBoundingClientRect();
            const x=bounds.left+bounds.width*0.5, y=bounds.top+bounds.height*0.5;
            canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:2,clientX:x,clientY:y}));
            canvas.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,button:2,clientX:x+80,clientY:y+25}));
            canvas.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,button:2,clientX:x+80,clientY:y+25}));
          })()`);
          await waitForCad(`document.querySelector('.cad-part-canvas')?.dataset.modelPosition !== '${beforePan}'`);
          const discovered = await window.webContents.executeJavaScript(`document.querySelector('.cad-wizard').textContent`);
          if (!discovered.includes('base_link') || !discovered.includes('OffsetPart') ||
              !discovered.includes('0/1 个关节已确认')) throw new Error('CAD parts/candidate missing');
          await window.webContents.executeJavaScript(`(() => {
            const el=document.querySelector('[aria-label="OffsetPart_joint type"]');
            const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;
            setter.call(el,'revolute'); el.dispatchEvent(new Event('change',{bubbles:true}));
          })()`);
          await waitForCad(`document.querySelector('[aria-label="OffsetPart_joint 下限"]') !== null && document.querySelector('[aria-label="OffsetPart_joint 上限"]') !== null`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b => b.textContent === '确认完成')?.click()`);
          await window.webContents.executeJavaScript(`(() => { const button=[...document.querySelectorAll('.cad-panel-switches button')].find(b => b.textContent === '关节试转'); if (button?.getAttribute('aria-pressed') === 'false') button.click(); })()`);
          await waitForCad(`document.querySelector('[aria-label="试转 OffsetPart_joint"]') !== null`);
          const beforeTrial = await window.webContents.executeJavaScript(`document.querySelector('.cad-part-canvas')?.dataset.motionMatrix`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="试转 OffsetPart_joint"]').focus()`);
          window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
          window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
          await waitForCad(`document.querySelector('.cad-part-canvas')?.dataset.motionMatrix !== '${beforeTrial}'`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-panel-switches button')].find(b => b.textContent === '关节试转')?.click()`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-flow button')].find(b => b.textContent.includes('验证导出'))?.click()`);
          await waitForCad(`Number(document.querySelector('[aria-label="三维机器人查看器"]')?.dataset.treeLinkCount) === 2`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('[role="tab"]')].find(tab => tab.textContent.trim() === '关节')?.click()`);
          await waitForCad(`document.querySelector('input[aria-label="OffsetPart_joint"]') !== null`);
          const event = await window.webContents.executeJavaScript(`(() => {
            const v=document.querySelector('[aria-label="三维机器人查看器"]');
            const slider=document.querySelector('input[aria-label="OffsetPart_joint"]');
            return {linkCount:Number(v.dataset.treeLinkCount),jointCount:Number(v.dataset.treeJointCount),
              meshCount:Number(v.dataset.meshCount),jointMin:Number(slider?.min),jointMax:Number(slider?.max),
              unconfirmed:document.querySelector('.cad-wizard').textContent.includes('1/1 个关节已确认')};
          })()`);
          if (event.jointCount !== 1 || event.meshCount < 2 || event.jointMin !== -1 ||
              event.jointMax !== 1 || !event.unconfirmed) throw new Error('CAD preview mismatch: '+JSON.stringify(event));
          const initialQuaternion = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          await window.webContents.executeJavaScript(`document.querySelector('input[aria-label="OffsetPart_joint"]').focus()`);
          window.webContents.sendInputEvent({ type: 'keyDown', keyCode: 'End' });
          window.webContents.sendInputEvent({ type: 'keyUp', keyCode: 'End' });
          await waitForCad(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion !== '${initialQuaternion}'`);
          const zQuaternion = await window.webContents.executeJavaScript(`document.querySelector('[data-joint-quaternion]')?.dataset.jointQuaternion`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-flow button')].find(b => b.textContent.includes('配置 Link / Joint'))?.click()`);
          await window.webContents.executeJavaScript(`document.querySelector('[aria-label="编辑关节 OffsetPart_joint"]')?.click()`);
          await waitForCad(`document.querySelector('[aria-label="OffsetPart_joint type"]') !== null`);
          const axisInput = '[aria-label="OffsetPart_joint axis"]';
          await window.webContents.executeJavaScript(`(() => { const el=document.querySelector('${axisInput}'); el.focus(); el.value='1 0 0'; el.dispatchEvent(new FocusEvent('focusout',{bubbles:true})); el.blur(); })()`);
          await waitForCad(`document.querySelector('.cad-wizard').textContent.includes('0/1 个关节已确认')`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b => b.textContent === '确认完成')?.click()`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-flow button')].find(b => b.textContent.includes('验证导出'))?.click()`);
          await waitForCad(`Number(document.querySelector('[aria-label="三维机器人查看器"]')?.dataset.treeLinkCount) === 2`);
          await window.webContents.executeJavaScript(`[...document.querySelectorAll('[role="tab"]')].find(tab => tab.textContent.trim() === '关节')?.click()`);
          await waitForCad(`document.querySelector('input[aria-label="OffsetPart_joint"]') !== null`);
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
            await window.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('导出 URDF / ROS ZIP 并检查'))?.click()`);
            await waitForCad(`[...document.querySelectorAll('[role="alert"]')].some(x => x.textContent.includes('缺少明确的材料密度'))`);
            await setNumber('BasePart density', 2700);
            await setNumber('OffsetPart density', 2700);
            await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-flow button')].find(b => b.textContent.includes('配置 Link / Joint'))?.click()`);
            await window.webContents.executeJavaScript(`document.querySelector('[aria-label="编辑关节 OffsetPart_joint"]')?.click()`);
            await waitForCad(`document.querySelector('[aria-label="OffsetPart_joint type"]') !== null`);
            await setNumber('OffsetPart_joint effort', 10);
            await setNumber('OffsetPart_joint velocity', 2);
            await waitForCad(`document.querySelector('.cad-wizard').textContent.includes('0/1 个关节已确认')`);
            await window.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b => b.textContent === '确认完成')?.click()`);
            await window.webContents.executeJavaScript(`[...document.querySelectorAll('.cad-flow button')].find(b => b.textContent.includes('验证导出'))?.click()`);
            await window.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('导出 URDF / ROS ZIP 并检查'))?.click()`);
            await waitForCad(`[...document.querySelectorAll('[role="status"]')].some(x => x.textContent.includes('导出完成'))`);
            const output = process.env.URDFTOOLS_CAD_EXPORT_SMOKE;
            const size = fs.statSync(output).size;
            const summary = await window.webContents.executeJavaScript(`[...document.querySelectorAll('[role="status"]')].find(x => x.textContent.includes('导出完成'))?.textContent`);
            if (size < 1000 || !summary.includes('训练就绪：尚未验证')) throw new Error('CAD ZIP export report invalid');
            fs.writeFileSync(path.join(process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR, 'cad-export.png'), (await window.webContents.capturePage()).toPNG());
            console.log(JSON.stringify({ event: 'desktop_cad_export_smoke', zipBytes: size, summary }));
          }
          if (process.env.URDFTOOLS_CAD_DRAFT_SMOKE) {
            const checkpoint = path.join(app.getPath('userData'), 'cad-draft', 'draft.json');
            const deadline = Date.now() + 15000;
            let saved;
            while (Date.now() < deadline) {
              try { saved = JSON.parse(await fs.promises.readFile(checkpoint, 'utf8')); }
              catch { /* waiting for the first atomic write */ }
              if (saved?.ui?.config?.joints?.[0]?.confirmed && saved.ui.densities?.BasePart === '2700' &&
                  saved.ui.step === 'export') break;
              await new Promise(resolve => setTimeout(resolve, 50));
            }
            if (!saved?.ui?.config?.joints?.[0]?.confirmed || saved.ui.densities?.BasePart !== '2700')
              throw new Error('CAD draft did not save Link/Joint and density settings');
            console.log(JSON.stringify({event:'desktop_cad_draft_smoke', saved:true,
              source:saved.source_name, jointCount:saved.ui.config.joints.length}));
          }
        }
        await window.webContents.executeJavaScript(`[...document.querySelectorAll('nav button')].find(button => button.textContent === '评估').click()`);
        await new Promise(resolve => setTimeout(resolve, 100));
        const selected = await window.webContents.executeJavaScript(`document.querySelector('.tool-workspace h1')?.textContent`);
        if (selected !== '评估') throw new Error('React workspace interaction failed');
        if (process.env.URDFTOOLS_MEDIA_SMOKE) {
          const runMediaSmoke = require(path.join(root, 'scripts/b07_desktop_smoke_hook.cjs'));
          await runMediaSmoke(window, process.env.URDFTOOLS_MEDIA_SMOKE,
            process.env.URDFTOOLS_MEDIA_REPORT, process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
        }
        if (process.env.URDFTOOLS_B08_SMOKE_SOURCE) {
          const runResultsSmoke = require(path.join(root, 'scripts/b08_desktop_smoke_hook.cjs'));
          await runResultsSmoke(window, process.env.URDFTOOLS_B08_SMOKE_RUN_ID,
            process.env.URDFTOOLS_SMOKE_ARTIFACT_DIR);
        }
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
let cadDraftQuitWaited = false;
app.on('before-quit', event => {
  if (!cadDraftPending || cadDraftQuitWaited) return;
  event.preventDefault();
  cadDraftQuitWaited = true;
  Promise.race([cadDraftWrite.catch(() => {}), new Promise(resolve => setTimeout(resolve, 5000))])
    .finally(() => app.quit());
});
app.on('will-quit', stopService);

require('./workbench.cjs')({ipcMain, app, dialog, assertRenderer, importRequest, runPythonWorker, modelProject});
