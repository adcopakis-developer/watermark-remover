const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('watermarkApp', {
  version: '1.1.0',
  platform: process.platform,
});
