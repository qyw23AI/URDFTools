const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('urdftools', Object.freeze({ version: '0.1.0' }));
