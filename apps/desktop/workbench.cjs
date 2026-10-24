const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
module.exports = function registerWorkbench({ipcMain, app, dialog, assertRenderer, importRequest, runPythonWorker, modelProject}) {
  const store = () => path.join(app.getPath('userData'), 'imports');
  const library = () => path.join(app.getPath('userData'), 'cad-library');
  async function worker(action, data, cad = false) {
    const temp = await fs.mkdtemp(path.join(app.getPath('userData'), 'urdf-edit-'));
    try {
      const request = path.join(temp, 'request.json');
      await fs.writeFile(request, JSON.stringify({...data, store:store(), output:data.output || path.join(temp, 'bundle')}));
      const result = await runPythonWorker(cad ? '.tools/model-venv/bin/python' : '.venv/bin/python',
        'scripts/urdf_workbench.py', [action, request], 180000);
      if (action === 'export') return result;
      const report = await importRequest({action:'import', source:path.dirname(result.path)});
      if (report.status !== 'ready') throw new Error('URDF 校验失败：' + JSON.stringify(report.findings) + JSON.stringify(report.models.map(m=>m.findings)));
      return report;
    } finally { await fs.rm(temp, {recursive:true, force:true}); }
  }
  async function add(name, report) {
    await fs.mkdir(library(), {recursive:true});
    const entry = {id:randomUUID(), name:String(name).slice(0,120), report};
    await fs.writeFile(path.join(library(), entry.id + '.json'), JSON.stringify(entry), {flag:'wx'});
    return entry;
  }
  ipcMain.handle('workbench-apply', async (event, xml, baseline) => {
    assertRenderer(event);
    if (typeof xml !== 'string' || xml.length > 8*1024*1024) throw new Error('URDF 内容无效或过大');
    return worker('prepare', {xml, baseline});
  });
  ipcMain.handle('workbench-export', async (event, operation) => {
    assertRenderer(event);
    const choice = process.argv.includes('--smoke') && process.env.URDFTOOLS_WORKBENCH_EXPORT ? {filePath:process.env.URDFTOOLS_WORKBENCH_EXPORT,canceled:false} :
      await dialog.showSaveDialog({defaultPath:'robot.urdf.zip', filters:[{name:'URDF 资源包',extensions:['zip']}]});
    if (choice.canceled) return null;
    return worker('export', {operation, output:choice.filePath});
  });
  ipcMain.handle('cad-library-list', async event => {
    assertRenderer(event); await fs.mkdir(library(), {recursive:true});
    return Promise.all((await fs.readdir(library())).filter(n=>n.endsWith('.json')).map(async n=>JSON.parse(await fs.readFile(path.join(library(),n),'utf8'))));
  });
  ipcMain.handle('cad-library-remove', async (event,id) => {
    assertRenderer(event);
    if (!/^[a-f0-9-]{36}$/.test(id)) throw new Error('无效模块编号');
    await fs.unlink(path.join(library(), id + '.json'));
  });
  ipcMain.handle('cad-library-import', async (event, unit) => {
    assertRenderer(event);
    if (!['mm','m'].includes(unit)) throw new Error('请选择网格单位');
    const choice = process.argv.includes('--smoke') && process.env.URDFTOOLS_WORKBENCH_CAD ? {filePaths:[process.env.URDFTOOLS_WORKBENCH_CAD],canceled:false} :
      await dialog.showOpenDialog({properties:['openFile'],filters:[{name:'CAD 模块',extensions:['step','stp','stl','obj']}]});
    if (choice.canceled) return null;
    const source = choice.filePaths[0];
    const report = await worker('cad',{source,unit}, /\.(step|stp)$/i.test(source));
    return add(path.basename(source),report);
  });
  ipcMain.handle('cad-library-generated', async event => {
    assertRenderer(event);
    const project = modelProject();
    const {revision} = JSON.parse(await fs.readFile(path.join(project,'current.json'),'utf8'));
    if (!Number.isSafeInteger(revision) || revision < 1) throw new Error('请先生成 CAD');
    const source = path.join(project,'revisions',String(revision).padStart(6,'0'),'assembly.step');
    return add('Agent CAD · ' + revision, await worker('cad',{source,unit:'mm'},true));
  });
};
