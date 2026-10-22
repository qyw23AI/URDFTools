const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('urdftools', Object.freeze({
  version: '0.1.0',
  importFile: file => ipcRenderer.invoke('import-source', webUtils.getPathForFile(file)),
  chooseImport: kind => ipcRenderer.invoke('choose-import', kind),
  selectImport: (operation, model) => ipcRenderer.invoke('select-import', operation, model)
}));
