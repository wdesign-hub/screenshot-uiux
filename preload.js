const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('api', {
  capture: (opts) => ipcRenderer.invoke('capture', opts),
  chooseFolder: () => ipcRenderer.invoke('choose-folder'),
  login: (url) => ipcRenderer.invoke('do-login', url),
  checkAuth: () => ipcRenderer.invoke('check-auth'),
  onProgress: (cb) => ipcRenderer.on('progress', (_, data) => cb(data))
});