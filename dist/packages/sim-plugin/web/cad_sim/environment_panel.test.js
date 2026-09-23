const assert = require('assert');
const { JSDOM } = require('jsdom');

const dom = new JSDOM('<aside id="panel"><button id="toggle"></button><div class="cs-environment-panel-content"></div></aside>');
global.document = dom.window.document;
global.window = dom.window;
require('./environment_workspace.js');

const panel = document.getElementById('panel');
const button = document.getElementById('toggle');
const values = new Map();
const storage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
const toggle = global.AI00SimulationEnvironmentWorkspace.createPanelToggle({ panel, button, storage });

assert.equal(panel.classList.contains('collapsed'), false);
button.click();
assert.equal(panel.classList.contains('collapsed'), true);
assert.equal(button.getAttribute('aria-expanded'), 'false');
assert.equal(values.get('ai00.simulation.environment-panel-collapsed'), '1');
button.click();
assert.equal(panel.classList.contains('collapsed'), false);
assert.equal(button.getAttribute('aria-expanded'), 'true');
toggle.destroy();

console.log('environment panel: PASS');
