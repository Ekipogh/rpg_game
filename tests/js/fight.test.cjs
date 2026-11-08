const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../../static/js/fight.js'), 'utf8');

function waitingPage(hidden = false) {
  const timers = new Map();
  const listeners = {};
  let reloads = 0, nextTimer = 0;
  const document = {
    hidden,
    querySelector: () => ({dataset: {}, querySelector() { throw new Error('Unexpected fight UI access'); }}),
    addEventListener: (event, callback) => { listeners[event] = callback; },
  };
  vm.runInNewContext(source, {
    document,
    window: {location: {reload() { reloads++; }}},
    setTimeout(callback, delay) { timers.set(++nextTimer, {callback, delay}); return nextTimer; },
    clearTimeout: id => timers.delete(id),
    fetch() { throw new Error('Missing battles must not call battle endpoints'); },
  });
  return {document, timers, listeners, reloads: () => reloads};
}

test('an encounter without a battle refreshes the page after discovery delay', () => {
  const page = waitingPage();
  assert.equal(page.timers.size, 1);
  const retry = [...page.timers.values()][0];
  assert.equal(retry.delay, 2000);
  retry.callback();
  assert.equal(page.reloads(), 1);
});

test('discovery retries pause in hidden tabs and resume without duplicate timers', () => {
  const page = waitingPage();
  page.document.hidden = true;
  page.listeners.visibilitychange();
  assert.equal(page.timers.size, 0);
  page.document.hidden = false;
  page.listeners.visibilitychange();
  page.listeners.visibilitychange();
  assert.equal(page.timers.size, 1);
  assert.equal(page.reloads(), 0);
});

test('an initially hidden encounter waits until visible before retrying', () => {
  const page = waitingPage(true);
  assert.equal(page.timers.size, 0);
  page.document.hidden = false;
  page.listeners.visibilitychange();
  assert.equal(page.timers.size, 1);
});
