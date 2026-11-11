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


test('elemental projectiles are cosmetic, respect reduced motion, and clean up', () => {
  const functionSource = source.slice(source.indexOf('  function projectile(event)'), source.indexOf('  function append(events)'));
  let reduced = false, appended = 0, removed = 0, frames;
  const cards = ['hero', 'enemy:0'].map((id, index) => ({dataset: {combatant: id},
    getBoundingClientRect: () => ({x: index * 100, y: 0, width: 20, height: 20})}));
  const orb = {style: {}, setAttribute() {}, remove() { removed++; },
    animate(value) { frames = value; return this.animation = {}; }};
  const context = {window: {matchMedia: () => ({matches: reduced})},
    find: () => ({children: cards, getBoundingClientRect: () => ({x: 0, y: 0, width: 900, height: 100})}),
    latest: {combatants: [{combatant_id: 'enemy:0', lane: 8}]},
    document: {createElement: () => orb, body: {append() { appended++; }}}};
  vm.createContext(context);
  vm.runInContext(functionSource + '; this.projectile = projectile;', context);
  const event = {event_type: 'attack', actor_id: 'hero', target_id: 'enemy:0',
    payload: {presentation_kind: 'projectile', element: 'fire'}};
  context.projectile(event);
  assert.equal(appended, 1);
  assert.equal(orb.style.background, '#ff8c32');
  assert.equal(frames.length, 2);
  orb.animation.onfinish();
  assert.equal(removed, 1);
  reduced = true;
  context.projectile(event);
  assert.equal(appended, 1);
  reduced = false;
  cards.pop(); // A lethal hit still animates to the authoritative target lane.
  context.projectile(event);
  assert.equal(appended, 2);
  orb.animation.oncancel();
  assert.equal(removed, 2);
  context.projectile({...event, payload: {ranged: true}});
  assert.equal(appended, 2);
});
