/* Server-authoritative fight display. Animation never advances simulation. */
(() => {
  'use strict';
  const root = document.querySelector('#live-fight');
  if (!root) return;
  const find = (name) => root.querySelector(`[data-${name}]`);
  if (!root.dataset.stateUrl) return;
  let sequence = 0, revision = -1, timer, busy = false, done = false;
  let latest = null, pending = null, connected = false;
  const names = new Map();
  const log = find('log');
  const text = (name, value) => { find(name).textContent = value; };
  const statusNames = {PENDING: 'Preparing fight', ACTIVE: 'In progress', RESOLVING: 'Resolving', FINISHED: 'Finished', PAUSED_ERROR: 'Paused'};
  const rejection = reason => ({
    battle_finished: 'The fight has ended.', invalid_target: 'That target is no longer reachable.',
    unsupported_policy: 'That movement policy is unavailable.', invalid_command: 'That action is unavailable.',
    stale_sequence: 'That action has already been handled.', invalid_payload: 'That action could not be read.'
  }[reason] || 'The action is no longer available.');
  function controls() {
    const enabled = connected && latest?.worker_available && latest.status === 'ACTIVE' && !pending;
    root.querySelectorAll('[data-policy], [data-enemy]').forEach(button => {
      button.disabled = !enabled || button.dataset.dead === 'true';
    });
  }
  async function read(url, options) {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || (response.status === 403 ? 'Session expired. Reload this page.' : 'Unable to reach this fight.'));
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function actorName(id) { return names.get(id) || id || 'Combatant'; }
  function describe(event) {
    const a = actorName(event.actor_id), b = actorName(event.target_id), p = event.payload || {};
    switch (event.event_type) {
      case 'move': return `${a} moves from lane ${p.from_lane} to ${p.to_lane}.`;
      case 'attack': return `${a} attacks ${b}.`;
      case 'miss': return `${a} misses ${b}.`;
      case 'critical': return `${a} lands a critical hit.`;
      case 'damage': return `${b} takes ${p.applied} damage (${p.health} HP remaining).`;
      case 'defeat': return `${a} is defeated.`;
      case 'instant_use': return `${a} immediately uses ${p.name} × ${p.quantity}.${p.money_change ? ` +${p.money_change} money.` : ''}${p.health_change ? ` +${p.health_change} HP.` : ''}${p.mana_change ? ` +${p.mana_change} MP.` : ''}`;
      case 'target_change': return event.target_id ? `${a} targets ${b}.` : `${a} has no target.`;
      case 'battle_complete': return p.result === 'victory' ? `Victory! +${p.experience} XP.` : 'Defeat. Returned home with 1 HP.';
      default: return event.event_type;
    }
  }
  function logNode(event) {
    const p = document.createElement('p');
    p.className = 'fight-log-entry';
    p.dataset.sequence = event.sequence;
    p.textContent = `${(event.simulation_time_ms / 1000).toFixed(1)}s · ${describe(event)}`;
    return p;
  }
  function append(events) {
    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 35;
    for (const event of events) {
      if (event.sequence <= sequence) continue;
      log.append(logNode(event)); sequence = event.sequence;
    }
    while (log.children.length > 500) log.firstElementChild.remove();
    find('older').hidden = !(Number(log.querySelector('[data-sequence]')?.dataset.sequence) > 1);
    if (atBottom) log.scrollTop = log.scrollHeight;
  }
  function render(data) {
    latest = data;
    text('status', statusNames[data.status] || data.status);
    text('connection', data.error || (!data.worker_available && data.status !== 'FINISHED' ? 'Combat is paused while the battle server reconnects.' : ''));
    const stage = find('combatants');
    const living = new Set(data.combatants.filter(actor => actor.health > 0).map(actor => actor.combatant_id));
    stage.querySelectorAll('[data-combatant]').forEach(card => {
      if (!living.has(card.dataset.combatant)) card.remove();
    });
    for (const actor of data.combatants) {
      names.set(actor.combatant_id, actor.name);
      if (!actor.health) continue;
      let card = Array.from(stage.children).find(node => node.dataset.combatant === actor.combatant_id);
      if (!card) {
        card = document.createElement(actor.team === 'enemy' ? 'button' : 'div');
        card.dataset.combatant = actor.combatant_id;
        card.append(document.createElement('strong'), document.createElement('small'), document.createElement('small'));
        if (actor.team === 'enemy') card.addEventListener('click', () => send('select_target', {target_id: actor.combatant_id}));
        stage.append(card);
      }
      card.className = `fight-combatant fight-${actor.team === 'hero' ? 'hero' : 'opponent'}`;
      card.style.gridColumn = actor.lane + 1;
      card.style.gridRow = '1';
      card.children[0].textContent = actor.name;
      card.children[1].textContent = `${actor.health}/${actor.max_health} HP`;
      card.children[2].textContent = `${actor.mana}/${actor.max_mana} MP`;
      if (actor.team === 'enemy') {
        card.type = 'button'; card.dataset.enemy = actor.combatant_id;
        card.setAttribute('aria-label', `Target ${actor.name}, lane ${actor.lane}, ${actor.health} health`);
        const hero = data.combatants.find(c => c.team === 'hero');
        card.setAttribute('aria-pressed', String(hero?.current_target_id === actor.combatant_id));
      }
    }
    const hero = data.combatants.find(c => c.team === 'hero');
    if (hero) {
      text('health-text', `${hero.health} / ${hero.max_health} HP`);
      text('mana-text', `${hero.mana} / ${hero.max_mana} MP`);
      find('health').value = hero.health; find('health').max = hero.max_health;
      find('mana').value = hero.mana; find('mana').max = Math.max(1, hero.max_mana);
      text('target', `Target: ${hero.current_target_id ? actorName(hero.current_target_id) : 'none'}`);
      text('intention', hero.movement_policy === 'hold' ? 'Holding position.' : 'Approaching your target until within melee range.');
      const remaining = Math.max(0, (hero.next_attack_at_ms ?? data.simulation_time_ms) - data.simulation_time_ms);
      find('attack').value = hero.next_attack_at_ms === null ? 0 : 1 - remaining / hero.attack_interval_ms;
      text('attack-text', hero.next_attack_at_ms === null ? 'Stopped' : `${(remaining / 1000).toFixed(2)}s`);
      root.querySelectorAll('[data-policy]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.policy === hero.movement_policy)));
    }
    if (pending) {
      const receipt = data.commands.find(c => c.id === pending.id);
      if (receipt) {
        find('retry-command').hidden = true;
        if (receipt.status !== 'QUEUED') {
          text('command-status', receipt.status === 'ACCEPTED' ? 'Command applied.' : rejection(receipt.reason));
          pending = null;
        }
      }
    }
    if (data.status === 'FINISHED') {
      find('result').hidden = false;
      const result = data.result;
      const loot = result?.loot?.length ? `Loot received: ${result.loot.map(drop => `${drop.name} × ${drop.quantity}`).join(', ')}.` : 'No loot received.';
      const money = result?.money_change ? ` +${result.money_change} money.` : '';
      text('result', data.outcome === 'VICTORY' ? `Victory! +${result?.experience || 0} XP.${money} ${loot}` : 'Defeat. You returned home with 1 HP; previously earned rewards are retained.');
      const link = find('continue'); link.hidden = false; link.href = data.next_url;
      link.textContent = data.next_url.includes('dungeon') ? 'Choose your next path' : 'Return home';
    }
    controls();
  }
  async function poll() {
    if (busy || document.hidden || done) return;
    clearTimeout(timer); busy = true;
    let more = false;
    try {
      const data = await read(`${root.dataset.stateUrl}?after_seq=${sequence}`);
      connected = true;
      if (data.revision >= revision) {
        revision = data.revision; render(data); append(data.events);
        more = data.has_more;
        done = data.status === 'FINISHED' && !more;
      }
    } catch (error) {
      connected = false;
      text('connection', error.status === 404 ? 'This fight is no longer available for the selected hero. Return to the dungeon.' : 'Connection interrupted. Reconnecting…');
      if (error.status === 404) done = true;
      controls();
    } finally {
      busy = false;
      if (!done) timer = setTimeout(poll, more ? 0 : 500);
    }
  }
  async function transmit() {
    if (!pending) return;
    find('retry-command').hidden = true;
    text('command-status', 'Waiting for the battle server…');
    controls();
    try {
      const receipt = await read(root.dataset.commandUrl, {method: 'POST', headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': root.querySelector('[name=csrfmiddlewaretoken]').value
      }, body: JSON.stringify(pending)});
      if (receipt.status !== 'QUEUED') {
        text('command-status', receipt.status === 'ACCEPTED' ? 'Command applied.' : rejection(receipt.reason));
        pending = null;
      }
      poll();
    } catch (error) {
      text('command-status', error.message);
      if (error.status && error.status < 500) pending = null;
      else find('retry-command').hidden = false; // Reuse the UUID after an uncertain delivery.
      controls();
    }
  }
  function send(command_type, payload) {
    if (pending) return;
    const id = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() :
      '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    pending = {id, command_type, payload};
    transmit();
  }
  root.querySelectorAll('[data-policy]').forEach(button => button.addEventListener('click', () => send('set_movement_policy', {policy: button.dataset.policy})));
  find('retry-command').addEventListener('click', transmit);
  find('older').addEventListener('click', async () => {
    const button = find('older'); button.disabled = true;
    try {
      const first = log.querySelector('[data-sequence]');
      const data = await read(`${root.dataset.eventsUrl}?before_seq=${first?.dataset.sequence || 1}`);
      const height = log.scrollHeight;
      const nodes = data.events.map(logNode);
      log.prepend(...nodes);
      log.scrollTop += log.scrollHeight - height;
      button.hidden = !data.has_older;
    } catch (_) { text('command-status', 'Could not load older events. Try again.'); }
    finally { button.disabled = false; }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); else clearTimeout(timer); });
  poll();
})();
