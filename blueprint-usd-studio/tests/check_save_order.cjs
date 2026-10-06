// Run: node tests/check_save_order.cjs
// Exercise the real editor functions with controllable network completion.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
const save = source.slice(source.indexOf('let saveQueue ='), source.indexOf('async function setProject'));
const suggest = source.slice(source.indexOf('async function suggestFurniture('), source.indexOf("$('suggestFurniture').onclick"));
const tick = () => new Promise(setImmediate);

function editor() {
  const nodes = {}, puts = [], proposals = [];
  const state = {project: 'scratch', revision: 1, plan: {rooms: [{name: 'original'}]}};
  let disk;
  const context = {
    state, clearTimeout, calibration: () => true, refreshFurnitureReview: () => {},
    toast: () => {}, $: id => nodes[id] ??= {}, markChanged: () => state.revision++,
    request: (url, options) => new Promise(resolve => {
      if (options.method === 'PUT') {
        const snapshot = JSON.parse(options.body);
        puts.push({snapshot, complete: () => {disk = snapshot; resolve({ok: true});}});
      } else {
        const layout = disk.rooms[0].name;
        proposals.push({layout, complete: () => resolve({placements: [{id: 'for_' + layout}], decisions: []})});
      }
    }),
  };
  vm.createContext(context);
  vm.runInContext(save + '\n' + suggest, context);
  return {state, nodes, puts, proposals, context, stored: () => disk};
}

(async () => {
  const ordered = editor();
  const autosave = ordered.context.savePlan();
  await tick();
  ordered.state.plan.rooms[0].name = 'latest';
  ordered.state.revision++;
  const furnishing = ordered.context.suggestFurniture();
  await tick();
  assert.equal(ordered.puts.length, 1, 'Explicit save must wait for the earlier autosave');
  ordered.puts[0].complete();
  await tick();
  assert.equal(ordered.puts.length, 2);
  assert.equal(ordered.puts[0].snapshot.rooms[0].name, 'original');
  assert.equal(ordered.puts[1].snapshot.rooms[0].name, 'latest');
  assert.notEqual(ordered.nodes.saveState?.textContent, 'Saved', 'Old completion must not claim the new revision is saved');
  ordered.puts[1].complete();
  await tick();
  assert.equal(ordered.proposals[0].layout, 'latest');
  ordered.proposals[0].complete();
  await Promise.all([autosave, furnishing]);
  assert.equal(ordered.stored().rooms[0].name, 'latest');
  assert.equal(ordered.state.plan.asset_placements[0].id, 'for_latest');

  const stale = editor();
  const pending = stale.context.suggestFurniture();
  await tick();
  stale.puts[0].complete();
  await tick();
  stale.state.plan.rooms[0].name = 'edited during suggestion';
  stale.state.revision++;
  stale.proposals[0].complete();
  await pending;
  assert.equal(stale.state.plan.asset_placements, undefined, 'Reject proposals for an older revision');
  assert.match(stale.nodes.furnitureStatus.textContent, /layout changed/i);
  assert.equal(stale.state.furnishing, false);
  console.log('PASS: saves remain ordered, proposals use the newest saved snapshot, and stale results are rejected');
})().catch(error => {console.error(error); process.exitCode = 1;});
