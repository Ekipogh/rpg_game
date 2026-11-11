# Standalone battle daemon

Run from the project virtual environment, independently of the web server:

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py setup_battle_content
.venv\Scripts\python.exe battle_daemon.py
```

Other commands:

```powershell
.venv\Scripts\python.exe battle_daemon.py status
.venv\Scripts\python.exe battle_daemon.py run --once
.venv\Scripts\python.exe battle_daemon.py retry 12
```

`--once` runs one bounded pass; it does not fast-forward a whole fight.
`retry ID` requeues a paused fight and starts the worker. Stop an existing worker
before retrying. Simulation-limit fights require investigation rather than retry.
Ctrl+C or SIGTERM stops after the current transaction and releases the lease.
The daemon refuses startup with outstanding migrations. It does not migrate the
application database or launch a web server automatically.

## Encounter content

Create `EncounterMonster` records for each battle encounter definition
(`goblin_ambush`, `ogre_guard`, `dungeon_guardian`). Reference existing `hero.Monster`
records; set quantity and position order. Each composition must total one to
three monsters. Call `full_clean()` before saving configuration. Concurrent
configuration editors must serialize composition changes; model validation alone
cannot enforce an aggregate limit across simultaneous writes.

The optional `setup_battle_content` command creates editable starter Goblin, Ogre
guard, and Dungeon guardian templates and one-monster compositions. Existing
templates and compositions are retained. No loot items are invented. Missing or invalid content pauses
that fight with a recorded error. Fix configuration, then use `retry ID`.
Queries through the Django shell can inspect `Battle.error_code/error_message`.

## Processing and guarantees

Dungeon entry and path selection create pending battles atomically with the run
transition. The worker also discovers and adopts older saved encounters. It snapshots effective stats, loot tables, and independent enemy
instances. Normal victory returns to path choices; boss victory ends the run;
defeat returns home at 1 HP. XP and loot are awarded on victory and retained on
later run failure. Instant loot applies its full-stack effects immediately; it
never enters inventory. A money purse adds money at receipt. Resource effects
apply after combat damage, within the same resolution transaction. The result
report includes money gained, and the combat log records immediate item use. Automatic leveling is unchanged.

The worker applies queued `BattleCommand` rows in sequence order at the next
processed simulation boundary. The command UUID is the idempotency key; commands
use `select_target` (`{"target_id": "enemy:0"}`) or `set_movement_policy`
(`{"policy": "approach"}`, `{"policy": "maintain_range"}`, or `{"policy": "hold"}`). The session-authorized `POST /battle/<id>/commands/` endpoint validates CSRF,
allocates sequences transactionally, deduplicates UUID retries, and limits the
pending queue to 100 requests. The fight page polls
`GET /battle/<id>/state/?after_seq=N` every 500 ms while visible.
`GET /battle/<id>/events/?after_seq=N&limit=100` paginates logs; `before_seq=N`
loads older events. Responses exclude RNG seeds and reward probability tables.
Approach/Maintain Range/Hold controls live in the Movement policy card; clicking an enemy
selects a target. Terminal results link to path choices or home. Admin pages
provide read-only battle inspection and editable encounter compositions.

Each transaction fences the singleton worker lease before reads and validates it
again before commit. SQLite serializes the lease write and the bounded simulation
batch. Checkpoints, events, receipts, hero resources, inventory rewards, and dungeon
transitions commit together. Failed transactions can be retried without rewards
or events being delivered twice. Stale/expired workers cannot commit.

A second daemon cannot acquire a live lease. A crashed worker's lease expires
in 15 seconds. Worker startup resets in-memory monotonic clocks: saved fights
resume without simulating process downtime. A ten-minute simulation limit pauses
stalemates. Transient database failures use bounded backoff, and the process exits
after three consecutive failures. Other fight-specific errors pause only that fight.

Healing remains suppressed for the whole expedition, including path choices.
External resource changes during combat cause the fight to pause rather than
silently overwriting those changes. No healing task is started by combat damage.

The old placeholder resolve action is blocked for every fight. Missing
configuration pauses a fight; it never falls back to random damage.
Read-only GET requests do not create or advance battles.

## Linux service

`deployment/rpg_game-battle.service` runs the same standalone script from
`/opt/rpg_game/current`, using the `rpg-game` account and the shared environment
in `/etc/rpg_game/environment`. The [Ubuntu setup and deployment procedure](deployment_guide.md)
installs this unit, migrates the shared database, and starts the worker alongside
the web and healing services. Run one worker per SQLite database.

## Ranged basic attacks

`Weapon.attack_range_max` and `Monster.attack_range_max` configure physical
basic attack range (1?8 lanes). The minimum range is 1, so ranged actors can
still attack adjacent opponents. Bows and Archer monsters start with range 4;
other weapons and unarmed heroes use range 1. Player range comes from the equipped
weapon, independently of class. These values are editable in admin and YAML.
The migrations configure existing bows and Archers and transfer any configured
class range to that class's restricted weapons before removing the class field; importing the catalog also
configures them. Restart web and battle worker processes after migrating.

Approach stops once the target is in attack range; Hold prevents movement but
continues automatic attacks against targets in range. Ranged shots can pass other
combatants, including when selecting a target behind the front line. Accuracy,
evasion, defense, critical hits, and attack speed use the existing physical
attack formulas. No ammunition is consumed. Already saved `melee-v1` battles
continue with their original snapshots; new battles use `ranged-v1`.

Maintain Range moves toward a target beyond maximum attack range and away from a
target inside maximum range. It stops at the weapon's maximum range. If the next
lane is occupied or outside the battlefield, the actor stays in place until a
later movement opportunity.

The worker saves an accepted player movement policy on the hero, so later battles
reuse it. Until the player chooses a policy, melee weapons and unarmed heroes
default to Approach, while weapons with range greater than one default to Maintain
Range. Changing weapons does not replace an explicit saved preference.
