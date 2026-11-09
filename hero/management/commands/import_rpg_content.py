"""Import the version-1 RPG content catalog without changing player data."""

from collections import Counter
from pathlib import Path

import yaml
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from battle.models import EncounterMonster
from hero.encounters import ENCOUNTER_DEFINITIONS
from hero.models import HeroClass, HeroClassEquipment, Monster, MonsterLoot
from item.models import Item, Weapon, Armor, Accessory, Consumable, Instant


ITEM_MODELS = {m.__name__: m for m in (Weapon, Armor, Accessory, Consumable, Instant)}


def records(data, section):
    rows = data[section]
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{section} must be a list of mappings.")
    return rows


def indexed(rows, field, label):
    result = {}
    for row in rows:
        key = row[field]
        if not isinstance(key, str) or not key.strip() or key in result:
            raise ValueError(f"Invalid or duplicate {label}: {key!r}")
        result[key] = row
    return result


def save_record(model, row, metadata, lookup, related_values=None):
    fields = {f.name for f in model._meta.fields
              if not f.primary_key and not f.is_relation}
    values = {k: v for k, v in row.items() if k not in metadata}
    unknown = set(values) - fields
    if unknown:
        raise ValueError(f"Unsupported {model.__name__} fields: {sorted(unknown)}")
    values.update(related_values or {})
    obj = model.objects.get(**lookup) if model.objects.filter(**lookup).exists() else model()
    for key, value in values.items():
        setattr(obj, key, value)
    if model is HeroClass:
        for stat in ("atk", "def", "mag", "mdef", "spd", "hp", "mp"):
            lower, upper = getattr(obj, f"{stat}_gain_min"), getattr(obj, f"{stat}_gain_max")
            if type(lower) is not int or type(upper) is not int or not 0 <= lower <= upper:
                raise ValueError(f"Invalid {stat} growth range for {obj.name!r}")
    obj.full_clean()
    obj.save()
    return obj


class Command(BaseCommand):
    help = "Create/update hero classes, RPG items, monsters, loot, and registered encounter groups from YAML."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(
            Path(settings.BASE_DIR) / "rpg_content.yaml"))
        parser.add_argument("--dry-run", action="store_true",
                            help="Validate the complete import, then roll back all writes.")

    def handle(self, *args, **options):
        try:
            data = yaml.safe_load(Path(options["path"]).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
                raise ValueError("Expected schema_version: 1.")
            if set(data) - {"schema_version", "notes", "hero_classes", "items", "monsters", "monster_loot", "encounters"}:
                raise ValueError("Unsupported top-level content sections.")
            sections = {s: records(data, s) for s in ("items", "monsters", "monster_loot", "encounters")}
            # Older version-1 files without class definitions remain supported.
            sections["hero_classes"] = records(data, "hero_classes") if "hero_classes" in data else []
            for section in ("hero_classes", "items", "monsters", "encounters"):
                indexed(sections[section], "key", f"{section} key")
            for section in ("hero_classes", "items", "monsters"):
                indexed(sections[section], "name", f"{section} name")
            with transaction.atomic():
                classes = {}
                for row in sections["hero_classes"]:
                    # HeroClass.name has no unique constraint; never pick an arbitrary row.
                    if HeroClass.objects.filter(name=row["name"]).count() > 1:
                        raise ValueError(f"Multiple existing hero classes named {row['name']!r}")
                    classes[row["key"]] = save_record(HeroClass, row, {"key", "initial_equipment"}, {"name": row["name"]})
                items = {}
                for row in sections["items"]:
                    model = ITEM_MODELS[row["model"]]
                    existing = Item.objects.filter(name=row["name"]).first()
                    if existing is not None and type(existing) is not model:
                        raise ValueError(f"Item {row['name']!r} already has a different model type.")
                    relations = {}
                    if "hero_class_restriction" in row:
                        key = row["hero_class_restriction"]
                        relations["hero_class_restriction"] = classes[key] if key is not None else None
                    items[row["key"]] = save_record(model, row,
                        {"key", "model", "hero_class_restriction"}, {"name": row["name"]}, relations)
                for row in sections["hero_classes"]:
                    if "initial_equipment" not in row:
                        continue
                    loadout = row["initial_equipment"]
                    if not isinstance(loadout, dict):
                        raise ValueError("initial_equipment must map slots to item keys.")
                    hero_class = classes[row["key"]]
                    HeroClassEquipment.objects.filter(hero_class=hero_class).delete()
                    for slot, key in loadout.items():
                        entry = HeroClassEquipment(hero_class=hero_class, slot=slot, item=items[key])
                        entry.full_clean()
                        entry.save()
                # Re-fetch related items after all updates and loadout replacements.
                # Retained loadouts can belong to classes omitted from this catalog.
                affected_loadouts = HeroClassEquipment.objects.filter(
                    Q(item_id__in=[item.pk for item in items.values()])
                    | Q(hero_class_id__in=[hero_class.pk for hero_class in classes.values()])
                ).prefetch_related("item")
                for entry in affected_loadouts:
                    entry.full_clean()
                monsters = {}
                for row in sections["monsters"]:
                    monsters[row["key"]] = save_record(Monster, row, {"key"}, {"name": row["name"]})
                seen_loot = set()
                for row in sections["monster_loot"]:
                    pair = (row["monster"], row["item"])
                    if pair in seen_loot:
                        raise ValueError(f"Duplicate loot pair: {pair}")
                    seen_loot.add(pair)
                    # Retain existing loot IDs and reject ambiguous existing duplicates.
                    lookup = dict(monster=monsters[pair[0]], item=items[pair[1]])
                    matches = MonsterLoot.objects.filter(**lookup)
                    if matches.count() > 1:
                        raise ValueError(f"Multiple existing loot rows for {pair}")
                    obj = matches.first() or MonsterLoot(**lookup)
                    if set(row) != {"monster", "item", "drop_chance", "min_quantity", "max_quantity"}:
                        raise ValueError(f"Invalid loot fields for {pair}")
                    for key in ("drop_chance", "min_quantity", "max_quantity"):
                        setattr(obj, key, row[key])
                    obj.full_clean()
                    obj.save()
                for row in sections["encounters"]:
                    if set(row) != {"key", "name", "kind", "recommended_level", "zone", "enemies"}:
                        raise ValueError("Invalid encounter fields.")
                    definition = ENCOUNTER_DEFINITIONS[row["key"]]
                    if definition.kind != "battle" or row["kind"] != "battle" or definition.title != row["name"]:
                        raise ValueError(f"Encounter {row['key']} does not match its registered definition.")
                    enemies = records({"enemies": row["enemies"]}, "enemies")
                    if not enemies or any(set(e) != {"monster", "quantity", "position_order"} for e in enemies):
                        raise ValueError("Invalid encounter enemies.")
                    positions = Counter(e["position_order"] for e in enemies)
                    if any(n > 1 for n in positions.values()):
                        raise ValueError("Duplicate encounter positions.")
                    # Replace only this named encounter's roster, including stale positions.
                    EncounterMonster.objects.filter(encounter_definition_key=row["key"]).delete()
                    for enemy in enemies:
                        obj = EncounterMonster(encounter_definition_key=row["key"],
                            monster=monsters[enemy["monster"]], quantity=enemy["quantity"],
                            position_order=enemy["position_order"])
                        obj.full_clean()
                        obj.save()
                if options["dry_run"]:
                    transaction.set_rollback(True)
        except (OSError, yaml.YAMLError, ValueError, TypeError, KeyError, ValidationError) as exc:
            raise CommandError(f"Content import failed: {exc}") from exc
        summary = ", ".join(f"{len(rows)} {name}" for name, rows in sections.items())
        self.stdout.write(self.style.SUCCESS(
            ("Dry run validated (rolled back): " if options["dry_run"] else "Imported: ") + summary))
