from __future__ import annotations

import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from world_core.models import Npc

TICKS_PER_YEAR = 365


def _find_ruleset() -> Path:
    override = os.environ.get("WORLD_RULESET_PATH")
    if override:
        return Path(override).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "docs" / "contracts" / "ruleset.v1.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("docs/contracts/ruleset.v1.yaml not found; set WORLD_RULESET_PATH")


@dataclass(frozen=True)
class RealmRule:
    realm: int
    name: str
    base_life_years: int
    base_qi_per_day: int
    stages: int
    difficulty: float


class Ruleset:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.version: str = raw["ruleset_version"]
        self.realms: dict[int, RealmRule] = {
            int(row["realm"]): RealmRule(
                realm=int(row["realm"]),
                name=str(row["name"]),
                base_life_years=int(row["base_life_years"]),
                base_qi_per_day=int(row["base_qi_per_day"]),
                stages=int(row["stages"]),
                difficulty=float(row["difficulty"]),
            )
            for row in raw["realms"]
        }
        self.techniques: dict[str, float] = {
            str(name): float(value)
            for name, value in raw["cultivation"]["technique_multiplier"].items()
        }
        self.qi_per_stage: dict[int, int] = {
            int(row["realm"]): int(row.get("qi_per_stage", 0)) for row in raw["realms"]
        }
        self.breakthrough = raw["breakthrough"]
        self.opportunity = raw["opportunity"]
        self.combat = raw["combat"]
        self.memory = raw["memory"]
        self.agents = raw["agents"]
        self.time = raw["time"]

    def realm(self, realm: int) -> RealmRule:
        try:
            return self.realms[realm]
        except KeyError as exc:
            raise ValueError(f"unknown realm {realm}") from exc

    def max_stage(self, realm: int) -> int:
        return self.realm(realm).stages

    def technique_multiplier(self, technique: str) -> float:
        return self.techniques.get(technique, self.techniques["basic"])

    def lifespan_ticks(self, realm: int, foundation: float) -> int:
        rule = self.realm(realm)
        return int(rule.base_life_years * TICKS_PER_YEAR * (0.9 + 0.2 * foundation))

    def daily_qi_gain(self, npc: Npc, aura_multiplier: float) -> int:
        rule = self.realm(npc.realm)
        aptitude = 0.6 + 0.8 * npc.aptitude
        technique = self.technique_multiplier(npc.technique)
        health = 0.5 + 0.5 * npc.health
        return int(rule.base_qi_per_day * aptitude * technique * aura_multiplier * health)

    def cap_qi(self, realm: int) -> int:
        rule = self.realm(realm)
        return self._qi_per_stage(realm) * max(0, rule.stages - 1)

    def stage_for_qi(self, realm: int, qi: int) -> int:
        rule = self.realm(realm)
        per_stage = self._qi_per_stage(realm)
        if per_stage <= 0:
            return 1
        return min(rule.stages, 1 + qi // per_stage)

    def next_stage_qi(self, realm: int, stage: int) -> int | None:
        rule = self.realm(realm)
        if stage >= rule.stages:
            return None
        return self._qi_per_stage(realm) * stage

    def _qi_per_stage(self, realm: int) -> int:
        return self.qi_per_stage.get(realm, 0)

    def breakthrough_probability(self, npc: Npc, *, pill_quality: float, support: float) -> float:
        weights = self.breakthrough["weights"]
        insight = npc.traits.get("insight", 0.5)
        injury = 1.0 - npc.health
        z = (
            float(self.breakthrough["intercept"])
            + float(weights["aptitude"]) * npc.aptitude
            + float(weights["foundation"]) * npc.foundation
            + float(weights["pill"]) * pill_quality
            + float(weights["insight"]) * insight
            + float(weights["support"]) * support
            + float(weights["injury"]) * injury
            + float(weights["difficulty"]) * self.realm(npc.realm).difficulty
        )
        low, high = self.breakthrough["probability_clip"]
        probability = 1.0 / (1.0 + math.exp(-z))
        return round(min(float(high), max(float(low), probability)), 6)

    def opportunity_probability(
        self,
        npc: Npc,
        *,
        base_weight: float,
        luck_bias: float,
        knowledge: float = 1.0,
    ) -> float:
        aptitude = 0.6 + 0.8 * npc.aptitude
        readiness = 0.5 + 0.5 * npc.health
        probability = base_weight * aptitude * knowledge * npc.luck * luck_bias * readiness
        return round(min(float(self.opportunity["max_probability"]), max(0.0, probability)), 6)

    def power(self, npc: Npc, *, support: float = 1.0) -> float:
        multipliers = self.combat["realm_multiplier"]
        realm_mult = float(multipliers[min(npc.realm, len(multipliers) - 1)])
        technique = self.technique_multiplier(npc.technique)
        health = 0.5 + 0.5 * npc.health
        return max(0.0001, realm_mult * technique * health * (0.9 + 0.2 * npc.luck) * support)

    def combat_win_probability(self, attacker_power: float, defender_power: float) -> float:
        k = float(self.combat["sigmoid_k"])
        probability = 1.0 / (1.0 + math.exp(-k * math.log(attacker_power / defender_power)))
        return round(min(0.98, max(0.02, probability)), 6)

    def pill_quality(self, item_id: str | None) -> float:
        if not item_id:
            return 0.0
        return float(self.breakthrough["pill"].get(item_id, {}).get("quality", 1.0))


@lru_cache(maxsize=1)
def load_ruleset(path: str | None = None) -> Ruleset:
    source = Path(path).expanduser().resolve() if path else _find_ruleset()
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "ruleset.v1":
        raise ValueError(f"unsupported ruleset at {source}")
    return Ruleset(raw)


RULESET = load_ruleset()
