import { mountDataEnvironmentSettings } from './data_environment.mjs';

// Load independently of the settings page's asynchronous configuration startup.
export function initializeEnvironmentSettings(document, business, electronAPI) {
  return mountDataEnvironmentSettings(document, document.getElementById('data-environment-settings'),
    (id, payload) => business.invoke(id, { version: 1, payload }, async () => true),
    { visibleOnFailure: true, ...(electronAPI?.getDataEnvironment ? { readActive: () => electronAPI.getDataEnvironment() } : {}) });
}

if (typeof document !== 'undefined') initializeEnvironmentSettings(document, window.AI00Business, window.electronAPI);
