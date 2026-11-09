"""Encounter content and immutable instances stored in a hero's dungeon JSON."""

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from uuid import uuid4

from django.db import models


class EncounterKind(models.TextChoices):
    BATTLE = "battle", "Battle"
    TRAP = "trap", "Trap"
    TREASURE = "treasure", "Treasure"
    NPC = "npc", "NPC"


class BattleTier(models.TextChoices):
    ENEMY = "enemy", "Enemy"
    MINIBOSS = "miniboss", "Miniboss"
    BOSS = "boss", "Boss"


@dataclass(frozen=True)
class EncounterDefinition:
    key: str
    title: str
    description: str
    kind: EncounterKind
    battle_tier: BattleTier | None = None

    def __post_init__(self):
        if self.kind not in EncounterKind.values:
            raise ValueError("Unknown encounter kind.")
        if self.kind == EncounterKind.BATTLE:
            if self.battle_tier not in BattleTier.values:
                raise ValueError("Battles require a valid battle tier.")
        elif self.battle_tier is not None:
            raise ValueError("Only battles can have a battle tier.")


ENCOUNTER_DEFINITIONS = MappingProxyType({
    definition.key: definition
    for definition in (
        EncounterDefinition("goblin_ambush", "Goblin ambush",
                            "A goblin blocks your path.", EncounterKind.BATTLE, BattleTier.ENEMY),
        EncounterDefinition("ogre_guard", "Ogre guard",
                            "An ogre guards the passage.", EncounterKind.BATTLE, BattleTier.MINIBOSS),
        EncounterDefinition("dungeon_guardian", "Dungeon guardian",
                            "A powerful guardian stands before you.", EncounterKind.BATTLE, BattleTier.BOSS),
        EncounterDefinition("spike_pit", "Spike pit",
                            "The floor gives way over hidden spikes.", EncounterKind.TRAP),
        EncounterDefinition("forgotten_cache", "Forgotten cache",
                            "You discover a cache of ancient knowledge.", EncounterKind.TREASURE),
        EncounterDefinition("wandering_healer", "Wandering healer",
                            "A friendly healer offers aid.", EncounterKind.NPC),
    ) + tuple(
        EncounterDefinition(**entry)
        for entry in json.loads(
            Path(__file__).with_name("content_encounters.json").read_text(encoding="utf-8")
        )
    )
})


@dataclass(frozen=True)
class Encounter:
    id: str
    definition_key: str
    floor: int

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Encounter ID must be a nonempty string.")
        if not isinstance(self.definition_key, str) or self.definition_key not in ENCOUNTER_DEFINITIONS:
            raise ValueError("Unknown encounter definition.")
        if type(self.floor) is not int or self.floor < 1:
            raise ValueError("Encounter floor must be a positive integer.")

    @classmethod
    def create(cls, definition_key, floor):
        return cls(str(uuid4()), definition_key, floor)

    @property
    def definition(self):
        return ENCOUNTER_DEFINITIONS[self.definition_key]

    @property
    def kind(self):
        return self.definition.kind

    @property
    def battle_tier(self):
        return self.definition.battle_tier

    def to_dict(self):
        # Kind and tier are derived from the definition to avoid conflicting data.
        return {"id": self.id, "definition_key": self.definition_key, "floor": self.floor}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or set(data) != {"id", "definition_key", "floor"}:
            raise ValueError("Invalid encounter data.")
        return cls(**data)
