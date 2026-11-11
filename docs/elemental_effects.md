# Elemental basic attacks

New encounters use `elemental-v1`. Existing `melee-v1`, `ranged-v1`, and
`magic-v1` snapshots retain their formulas, RNG consumption, and serialized
shapes. No database migration is required: snapshots and checkpoints are JSON.

A Wizard's equipped magical ranged weapon supplies the element. Physical
weapons remain physical, including ranged weapons with an element. These basic
attacks cost no mana and retain weapon range, accuracy, criticals, and cooldown.

| Element | Chance after a damaging hit | Effect | Boss adjustment |
| --- | --- | --- | --- |
| Fire | 30% | Burning: 20% of hit damage each second for four ticks; refreshes | Full |
| Ice | 25% | Chilled: movement speed reduced 40% for 3 seconds; another application replaces it with Frozen for 1.5 seconds, stopping movement only | Chilled only |
| Lightning | 30% | 35% of hit damage to the nearest other living enemy within 3 lanes, stable ID tie break | Full |
| Earth | 20% | Delay next attack 400 ms, maximum accumulated delay 1000 ms until that attack is processed | 200 ms per application |
| Wind | 20% | Push one lane away if in bounds and unoccupied | Immune |
| Holy | 100% | Heal 15% of damage actually applied, capped at maximum health | Full |
| Dark | 25% | Reduce effective ATK and MAG 15% for 4 seconds; refreshes | 8% |

Boss adjustments apply to enemies in boss-tier encounters. Effects require
positive applied damage. Except Holy's healing, they require the primary target
to survive. Holy includes damage applied on a lethal hit and cannot resurrect.
Lightning secondary damage never crits or procs effects.

Armor `elemental_resistances` maps element names to damage multipliers: 0 is
immune, 0.5 halves damage, 1 is normal, and 1.5 increases damage. Snapshot
multipliers use integer basis points. Each elemental damage instance applies
the recipient's multiplier, including burn ticks and chain hits. Percentages
round half up to an integer; low damage may round to zero, without a minimum
one override. Burn potency is calculated from the original resisted hit;
subsequent ticks apply the recipient's resistance again.

Accessory `status_immunities` accepts `burning` (also legacy `burn`), `chilled`,
`frozen`, `static_charge`, `stagger`, `gust`, and `withering`. Other existing
immunity names remain harmless. Chilled immunity prevents the Ice progression;
Frozen immunity permits Chilled but prevents its upgrade.

Statuses and timer changes live in checkpoints, using simulation milliseconds.
At equal timestamps the engine processes commands, then ticks and expiries in
combatant ID order, then movement and attacks in combatant ID order. The last
burn tick occurs before its expiry. Reapplication resets the burn tick schedule
and duration. Death clears statuses and cancels future actions; encounter end
clears all remaining statuses. Damage, healing, status application/expiry,
stagger and forced movement are emitted as events. The browser displays those
events and active status names; it does not resolve effects.

Validation: `manage.py test` and `node --test tests/js/fight.test.cjs`.
