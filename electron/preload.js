const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('watermarkApp', {
  version: '1.0.0',
  platform: process.platform,
});
