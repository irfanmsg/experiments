// Run: node tests/check_printed_length.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function printedLength('), source.indexOf('function calibration(')), context);
for (const [text, metres] of [
  ['13\'3"', 4.0386], ['13′3″', 4.0386], ['13 ft 3 in', 4.0386],
  ['13 feet', 3.9624], ['0\'6"', .1524], ['4.03 m', 4.03], ['4.03', 4.03],
  ['4.03 metres', 4.03], ['.5 m', .5], [' 10 FT ', 3.048],
]) assert.ok(Math.abs(context.printedLength(text) - metres) < 1e-10, text);
for (const text of ['', '0', '-3 m', '13 3', '13\'12"', '13\'3" x 10\'0"', 'NaN', 'Infinity', '4 cm', '3e2']) {
  assert.equal(context.printedLength(text), null, text);
}
console.log('PASS: printed metric and imperial lengths convert exactly; ambiguous or invalid entries are rejected');
