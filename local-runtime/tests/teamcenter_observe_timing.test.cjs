const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'), 'utf8');
const start = source.indexOf('function observationTiming(');
assert(start >= 0, 'observation timing must be available');
const end = source.indexOf('\nfunction ', start + 1);
const lines = [];
let now = 0;
const context = {
  request: { command: 'observe' },
  Java: { type: name => ({
    'java.lang.System': { nanoTime: () => now, getProperty: () => 'TEMP' },
    'java.lang.ProcessHandle': { current: () => ({ pid: () => 123 }) },
    'java.nio.file.Paths': { get: (...parts) => parts.join('/') },
    'java.nio.file.Files': { write: (_, bytes) => lines.push(bytes) },
    'java.nio.file.StandardOpenOption': { CREATE: 1, APPEND: 2 },
    'java.lang.String': function(value) { this.getBytes = () => value; }
  }[name]) }
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
context.observationTiming('expand_start', 0);
now = 42000000000;
context.observationTiming('expand_done', 14416);
assert.deepEqual(JSON.parse(lines[1]), { stage: 'expand_done', elapsed_ms: 42000, count: 14416 });
context.request.command = 'search';
context.observationTiming('ignored', 9);
assert.equal(lines.length, 2);
context.request.command = 'children';
context.observationTiming('failed_line', 230);
assert.equal(lines.length, 3, 'lazy children SDK failures need safe local diagnostics too');
assert.deepEqual(JSON.parse(lines[2]), { stage: 'failed_line', elapsed_ms: 42000, count: 230 });
console.log('observation timing passed');
