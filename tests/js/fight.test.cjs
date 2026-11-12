const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../../static/js/fight.js'), 'utf8');

test('item polling preserves focused buttons and updates stock and click data in place', () => {
  const functionSource = source.slice(source.indexOf('  function renderItems('), source.indexOf('  function render(data)'));
  const items = {children: [], append(button) { this.children.push(button); }};
  const empty = {};
  let created = 0, activeElement = null, used = [];
  const context = {
    find: name => name === 'items' ? items : empty,
    latest: {items: []},
    useItem: item => used.push(item),
    document: {createElement() {
      created++;
      return {dataset: {}, textContent: '', listeners: [],
        addEventListener(event, callback) { this.listeners.push(callback); },
        focus() { activeElement = this; },
        remove() {
          items.children.splice(items.children.indexOf(this), 1);
          if (activeElement === this) activeElement = null;
        }};
    }},
  };
  vm.createContext(context);
  vm.runInContext(functionSource + '; this.renderItems = renderItems;', context);
  const potion = {id: 1, name: 'Potion', quantity: 5, heal_amount: 10, mana_restore: 0};
  const mana = {id: 2, name: 'Mana', quantity: 2, heal_amount: 0, mana_restore: 20};
  const render = list => { context.latest = {items: list}; context.renderItems(list); };
  render([potion, mana]);
  const [first, second] = items.children;
  first.focus(); // Focus, or a pointer-down, survives the next polling update.
  render([{...potion}, {...mana}]);
  assert.equal(items.children[0], first);
  assert.equal(items.children[1], second);
  assert.equal(activeElement, first);
  assert.equal(created, 2);
  const changed = {...potion, quantity: 4, use_url: '/updated/'};
  render([changed, mana]);
  assert.equal(activeElement, first);
  assert.equal(first.textContent, 'Potion × 4');
  assert.equal(first.listeners.length, 1);
  first.listeners[0]();
  assert.equal(used[0], changed);
  second.focus();
  render([mana, {...potion, id: 3}]);
  assert.equal(items.children[0], second);
  assert.equal(activeElement, second);
  assert.equal(created, 3);
  assert.equal(empty.hidden, true);
  render([]);
  assert.equal(items.children.length, 0);
  assert.equal(empty.hidden, false);
});

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
