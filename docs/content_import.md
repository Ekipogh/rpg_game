The version-1 YAML catalog contains 3 hero classes (Warrior, Ranger, and Wizard)
with their configured base stats, growth ranges, and starting equipment, plus
235 polymorphic items, 48 monsters across levels
1–20, 452 loot entries, and 48 battle encounters. Copper, silver, and gold coins
credit 1, 10, and 100 money on receipt. Monster loot quantities and percentages
are imported directly; elemental resistances are damage multipliers.

Install requirements and apply migrations before importing:

For a deployed game, sign in to Django admin with a superuser account, open
**Hero classes**, and select **Import RPG content**. Upload `rpg_content.yaml`
and choose **Validate only**. Once validation succeeds, upload the same file
again and choose **Apply content**. The result or validation error appears on
the page. The direct URL is `/admin/hero/heroclass/import-content/`.
This uses the same transactional importer as the command below, requires no
server shell, and records successful applies in the Django admin log with the
acting user. Uploads are limited to 2 MiB and temporary files are removed after
each request. Take a database backup before applying. Deploy this admin tool
once before using it; migrations remain part of deployment, and new encounter
keys still require a code release. The upload changes database content, not the
release's bundled YAML file. Later CLI imports use their selected file.

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py import_rpg_content --dry-run
.venv/Scripts/python.exe manage.py import_rpg_content
```

An optional positional path selects another version-1 YAML file. The default is
`rpg_content.yaml` in the project root. Dry runs execute all
validation and database operations inside a transaction and roll them back.

Items and monsters are matched by unique name; reruns update them in place.
Hero classes are also matched by name, preserving their IDs, existing hero links,
and images when no image is specified. Duplicate existing class names are rejected
because the model does not enforce unique names. Growth ranges must be nonnegative
integers with minimum no greater than maximum. Importing classes does not recalculate
existing heroes' stats. Item `hero_class_restriction` values resolve to keys in
`hero_classes`; explicit null clears a restriction. The `hero_classes`
section is optional for compatibility with older version-1 files; each record uses
`key`, `name`, and HeroClass model fields such as `base_health` and `hp_gain_min`.
Each class may also include `initial_equipment`, a mapping of equipment slots to
item keys:

```yaml
initial_equipment:
  weapon: rustleaf_blade
  armor: padded_jerkin
  accessory: copper_charm
```

The importer stores these in `HeroClassEquipment` after importing items. Reruns
replace only the specified class loadout; `{}` clears it and an omitted field
retains it. Retained loadouts using updated items are revalidated against the final
imported state, including loadouts of classes omitted from the catalog. Wrong
slots, incompatible class restrictions, missing item keys, and
items requiring a level above 1 reject the entire import. Apply migrations and
rerun the import before creating characters with these loadouts.

Character creation uses the class's current database stats and equips its imported
loadout atomically. It creates no item templates or hardcoded potions. Equipped
items occupy equipment slots rather than duplicating inventory stock. Existing
heroes' equipment is not changed by imports. Classes without a loadout start
without equipped items.

Loot is matched by monster/item pair. Ambiguous existing duplicate loot and item
subclass conflicts cause an error rather than deleting existing data. Each listed
encounter's spawn roster is replaced to remove stale positions. Unlisted content,
player inventories, and saved battles are retained. Any invalid record rolls back
the entire import. Back up the database before updating an existing catalog.

Encounter definitions are code-managed, not database models. The bundled
`hero/content_encounters.json` registers these 48 keys on every process startup;
tiers are derived from the strongest monster threat in each supplied group.
Titles and level/zone descriptions are retained there. New encounter keys require
adding a definition to that catalog before importing. Restart running game/worker
processes after deploying the catalog. The importer does not change dungeon
level gating; recommended levels are descriptive. Starting encounters and later
paths exclude battle definitions without a configured roster of one to three
monsters. Unconfigured definitions remain registered so saved encounters can
still be read.
Stats and rewards still require gameplay balance testing.


Wizard basic attacks use the existing Wizard class and starting loadout. Bundled
channeling staffs explicitly configure `basic_attack_kind: magical`,
`magic_bonus` matching their existing ATK bonus, and `attack_range_max: 4`.
These are initial balance values.
Weapon elements affect projectile color only. MAG (including weapon/accessory
bonuses) attacks MDEF using the same integer formula, accuracy, critical RNG,
and timing as physical attacks, with no mana cost. Only a Wizard with an
explicitly magical weapon of range greater than one uses this profile; other
weapons/classes fall back to physical damage. Maintain Range still seeks maximum
range; Approach stops in range and Hold stays stationary.

Deploy with `python manage.py migrate`, then
`python manage.py import_rpg_content --dry-run` and
`python manage.py import_rpg_content`. Restart the web process and battle worker.
The migration defaults existing weapons to physical; importing opts catalog
staffs into magic without changing equipped item identities. New battles use
`magic-v1` with strict attack-profile fields in schema 1. Legacy `melee-v1` and
`ranged-v1` snapshots retain their wire shape and physical rules, and continue
without re-reading equipment. Existing battles retain their original stats.
Projectile animations are cosmetic and honor reduced motion; they never delay
HP reconciliation or introduce travel time into damage.
