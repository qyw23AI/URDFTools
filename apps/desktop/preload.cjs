const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('urdftools', Object.freeze({
  version: '0.1.0',
  importFile: file => ipcRenderer.invoke('import-source', webUtils.getPathForFile(file)),
  chooseImport: kind => ipcRenderer.invoke('choose-import', kind),
  selectImport: (operation, model) => ipcRenderer.invoke('select-import', operation, model),
  chooseCadStep: () => ipcRenderer.invoke('choose-cad-step'),
  modelCurrent: () => ipcRenderer.invoke('model-current'),
  modelApply: (recipe, expectedRevision) => ipcRenderer.invoke('model-apply', recipe, expectedRevision),
  agentSuggest: (instruction, expectedRevision) => ipcRenderer.invoke('agent-suggest', instruction, expectedRevision),
  agentApply: proposalId => ipcRenderer.invoke('agent-apply', proposalId),
  modelReconcile: config => ipcRenderer.invoke('model-reconcile', config),
  modelAcceptReturn: config => ipcRenderer.invoke('model-accept-return', config),
  cadPreview: config => ipcRenderer.invoke('cad-preview', config),
  saveCadConfig: config => ipcRenderer.invoke('save-cad-config', config),
  loadCadConfig: () => ipcRenderer.invoke('load-cad-config'),
  exportCadPackage: (config, densities) => ipcRenderer.invoke('export-cad-package', config, densities)
}));
