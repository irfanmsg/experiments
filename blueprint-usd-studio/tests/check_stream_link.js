// Run: node tests/check_stream_link.js
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');

const source = readFileSync(join(__dirname, '../app/static/app.js'), 'utf8');
const startStream = source.slice(source.indexOf('async function startStream()'), source.indexOf('function renderAssets()'));
const viewer = 'http://10.46.71.211:8088/?signal_port=49100';

function setup(responses) {
  const message = { textContent: '' };
  const link = { href: 'http://old-host:8088/', hidden: false, removeAttribute() { this.href = ''; } };
  const nodes = {
    streamLink: link,
    streamPanel: { hidden: true, querySelector: () => message },
    streamButton: {}, streamQuality: { value: 'hd' }, streamPhysics: { checked: true },
  };
  const calls = [];
  const timers = new Map();
  let nextTimer = 0;
  const context = {
    $: id => nodes[id],
    state: { project: 'scene-id', generated: { style: 'home_luxury' } },
    location: { hostname: '127.0.0.1' },
    request: async (path, options) => {
      calls.push({ path, options });
      const response = await responses.shift();
      if (response instanceof Error) throw response;
      return response;
    },
    toast: () => {},
    setInterval: callback => { timers.set(++nextTimer, callback); return nextTimer; },
    clearInterval: id => timers.delete(id),
  };
  runInNewContext(startStream, context);
  return { start: context.startStream, link, panel: nodes.streamPanel, message, calls,
    poll: async () => { assert.equal(timers.size, 1); await [...timers.values()][0](); } };
}

function unavailable(check) {
  assert.equal(check.link.href, '', 'pending/error must clear the previous viewer address');
  assert.equal(check.link.hidden, true, 'pending/error must hide the viewer link');
}

(async () => {
  let release;
  const check = setup([new Promise(resolve => { release = resolve; }),
    { phase: 'rendering_first_frame', running: true }, { phase: 'ready', running: true }]);
  const starting = check.start();
  unavailable(check);
  release({ phase: 'loading', running: true, client_url: viewer });
  await starting;
  assert.equal(check.panel.hidden, false, 'startup status must remain visible');
  unavailable(check);
  await check.poll();
  unavailable(check);
  await check.poll();
  assert.equal(check.link.href, viewer);
  assert.equal(check.link.hidden, false);
  assert.deepEqual(JSON.parse(check.calls[0].options.body), { style: 'home_luxury', quality: 'hd', physics: true });
  assert.equal(check.calls[0].path, '/api/projects/scene-id/stream');

  for (const phase of ['ready', 'running', 'client_connected']) {
    const ready = setup([{ phase, running: true, client_url: viewer }]);
    await ready.start();
    assert.equal(ready.link.href, viewer, `initial ${phase} must expose the viewer`);
    assert.equal(ready.link.hidden, false);
  }
  const fallback = setup([{ phase: 'ready', running: true }]);
  await fallback.start();
  assert.equal(fallback.link.href, 'http://127.0.0.1:8088/?signal_port=49100');
  for (const response of [{ phase: 'error', running: false, client_url: viewer }, new Error('Startup failed')]) {
    const failed = setup([response]);
    await failed.start();
    unavailable(failed);
  }
  for (const response of [{ phase: 'error', running: false }, new Error('Status unavailable')]) {
    const failed = setup([{ phase: 'loading', running: true, client_url: viewer }, response]);
    await failed.start();
    await failed.poll();
    unavailable(failed);
  }
  let releaseOldPoll;
  const restarted = setup([{ phase: 'loading', running: true, client_url: 'http://old-host:8088/' },
    new Promise(resolve => { releaseOldPoll = resolve; }), { phase: 'loading', running: true, client_url: viewer }]);
  await restarted.start();
  const oldPoll = restarted.poll();
  await restarted.start();
  releaseOldPoll({ phase: 'ready', running: true });
  await oldPoll;
  unavailable(restarted);
  console.log('Viewer link stays unavailable until the RTX stream is ready.');
})().catch(error => { console.error(error); process.exitCode = 1; });
