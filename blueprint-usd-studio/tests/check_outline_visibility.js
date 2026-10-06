// Run: node tests/check_outline_visibility.js
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const source = readFileSync(join(__dirname, '../app/static/app.js'), 'utf8');
const drawing = source.slice(source.indexOf('function draw()'), source.indexOf('function createRoom('));
const labels = [], strokes = [];
const ctx = new Proxy({
  fillText(text) { labels.push(text); },
  stroke() { strokes.push(this.strokeStyle); },
}, {get(target, key) { return key in target ? target[key] : () => {}; }});
const proposal = {reviewName: 'Study', selected: false, max_dimension_relative_error: .1,
  pixel_polygon: [[10, 10], [80, 10], [80, 60], [10, 60]]};
const state = {image: {}, plan: {}, suggestions: [proposal], points: []};
const context = {state, ctx, canvas: {width: 1000, height: 700},
  centroid: () => [45, 35], allPlacements: () => []};
runInNewContext(drawing, context);
context.draw();
assert.equal(strokes.length, 1, 'An unchecked measurement conflict must remain visible for review');
assert.match(labels[0], /Study.*not selected/i);
const reviewStroke = strokes[0];
proposal.selected = true;
labels.length = strokes.length = 0;
context.draw();
assert.equal(strokes.length, 1);
assert.notEqual(strokes[0], reviewStroke, 'Selected and unselected proposals need distinct styling');
assert.equal(labels[0], 'Study');
assert.equal(state.plan.rooms, undefined, 'Drawing an uncertain outline must not accept it');
console.log('Unselected proposals stay visible and remain unaccepted.');
