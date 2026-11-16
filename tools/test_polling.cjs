'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { createPoller } = require('../static/polling.js');

function timers(t) {
  let id = 0;
  const queue = new Map();
  t.mock.method(global, 'setTimeout', (fn) => { queue.set(++id, fn); return id; });
  t.mock.method(global, 'clearTimeout', (key) => queue.delete(key));
  return {
    get count() { return queue.size; },
    async next() {
      assert.ok(queue.size, 'expected a scheduled poll');
      const [key, fn] = queue.entries().next().value;
      queue.delete(key);
      fn();
      await flush();
    }
  };
}
async function flush() { for (let i = 0; i < 8; i++) await Promise.resolve(); }

test('slow requests finish before a second request starts', async (t) => {
  const clock = timers(t);
  let calls = 0, finish;
  const poller = createPoller(() => {
    calls++;
    return new Promise((resolve) => { finish = resolve; });
  }, 1000);
  poller.start();
  poller.start();
  assert.equal(calls, 1);
  assert.equal(clock.count, 0);
  finish();
  await flush();
  assert.equal(clock.count, 1);
  await clock.next();
  assert.equal(calls, 2);
  poller.stop();
  finish();
  await flush();
  assert.equal(clock.count, 0);
});

test('hidden or inactive pages skip work and can resume', async (t) => {
  const clock = timers(t);
  let visible = false, calls = 0;
  const poller = createPoller(async () => { calls++; }, 400, () => visible);
  poller.start();
  await clock.next();
  assert.equal(calls, 0);
  visible = true;
  await clock.next();
  assert.equal(calls, 1);
  visible = false;
  await clock.next();
  assert.equal(calls, 1);
  poller.stop();
  assert.equal(clock.count, 0);
});

test('network failures do not stop polling', async (t) => {
  const clock = timers(t);
  let calls = 0;
  const poller = createPoller(async () => {
    calls++;
    if (calls === 1) throw new Error('offline');
  }, 1000);
  poller.start();
  await flush();
  await clock.next();
  assert.equal(calls, 2);
  poller.stop();
});

test('stop/restart during an in-flight request keeps one timer', async (t) => {
  const clock = timers(t);
  let calls = 0, finish;
  const poller = createPoller(() => {
    calls++;
    return new Promise((resolve) => { finish = resolve; });
  }, 1000);
  poller.start();
  poller.stop();
  poller.start();
  assert.equal(calls, 1);
  finish();
  await flush();
  assert.equal(clock.count, 1);
  await clock.next();
  assert.equal(calls, 2);
  poller.stop();
  finish();
  await flush();
  assert.equal(clock.count, 0);
});
