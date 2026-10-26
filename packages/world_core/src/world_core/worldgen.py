from __future__ import annotations

import uuid
from typing import Any

from world_core.checksum import SIM_VERSION
from world_core.models import (
    Belief,
    Faction,
    Goal,
    Item,
    Location,
    Npc,
    Opportunity,
    Relationship,
    SecretRealm,
    WorldState,
    belief_key,
    relationship_key,
)
from world_core.ruleset import RULESET, TICKS_PER_YEAR

_ID_NAMESPACE = uuid.UUID("6f1a55f2-3f6c-4ff1-9a7e-54cf53e1d2a0")


def stable_id(kind: str, key: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"{kind}:{key}"))


def world_id(seed: int) -> str:
    return stable_id("world", str(seed))


def npc_id(key: str) -> str:
    return stable_id("npc", key)


def faction_id(key: str) -> str:
    return stable_id("faction", key)


WORLD_ID = world_id(42)
PLAYER_ID = npc_id("xie_wujiu")
PROTAGONIST_ID = npc_id("shen_yan")
FACTION_XUANYUE = faction_id("xuanyue")
FACTION_CHIXIAO = faction_id("chixiao")

LOC_STONE_TOWN = "location_stone_town"
LOC_XUANYUE_SECT = "location_xuanyue_sect"
LOC_BLACKWOOD_FOREST = "location_blackwood_forest"
LOC_RUINED_TEMPLE = "location_ruined_temple"
LOC_MISTY_VALLEY = "location_misty_valley"
LOC_ANCIENT_CAVE = "location_ancient_cave"
LOC_CHIXIAO_OUTPOST = "location_chixiao_outpost"
LOC_BLACK_MARKET = "location_black_market"

ITEM_MAP_FRAGMENT = "item_map_fragment"
ITEM_FOUNDATION_PILL = "item_foundation_pill"
ITEM_SPIRIT_SWORD = "item_spirit_sword"
ITEM_TALISMAN = "item_talisman"
ITEM_PLAYER_KNIFE = "item_player_knife"
ITEM_HERB_BUNDLE = "item_herb_bundle"
ITEM_QI_PILL = "item_qi_pill"
ITEM_MARKET_TOKEN = "item_market_token"
ITEM_JADE_SLIP = "item_jade_slip"

REALM_ANCIENT_CAVE = "realm_ancient_cave"
OPP_FOUNDATION_PILL = "opp_foundation_pill"

PUBLIC_LOCATIONS = [
    LOC_STONE_TOWN,
    LOC_XUANYUE_SECT,
    LOC_BLACKWOOD_FOREST,
    LOC_RUINED_TEMPLE,
    LOC_MISTY_VALLEY,
    LOC_CHIXIAO_OUTPOST,
    LOC_BLACK_MARKET,
]

REALM_CLOSE_TICK = 15 * TICKS_PER_YEAR


def _goal(goal_id: str, kind: str, priority: float, **params: Any) -> Goal:
    return Goal(goal_id=goal_id, kind=kind, priority=priority, params=params)


def _make_npc(
    *,
    key: str,
    name: str,
    role: str,
    faction: str | None,
    location: str,
    realm: int,
    stage: int,
    age_years: int,
    aptitude: float,
    luck: float,
    technique: str,
    wealth: int,
    traits: dict[str, float],
    goals: list[Goal],
    inventory: list[str],
    foundation: float = 0.5,
    health: float = 0.98,
) -> Npc:
    per_stage = RULESET.qi_per_stage.get(realm, 0)
    return Npc(
        npc_id=npc_id(key),
        name=name,
        canonical_role=role,
        faction_id=faction,
        birth_tick=-age_years * TICKS_PER_YEAR,
        lifespan_ticks=RULESET.lifespan_ticks(realm, foundation),
        realm=realm,
        stage=stage,
        qi=max(0, (stage - 1) * per_stage),
        foundation=foundation,
        health=health,
        wealth=wealth,
        aptitude=aptitude,
        luck=luck,
        technique=technique,
        location_id=location,
        traits=traits,
        goals=goals,
        known_locations=list(PUBLIC_LOCATIONS),
        inventory=inventory,
    )


def _locations() -> dict[str, Location]:
    return {
        LOC_STONE_TOWN: Location(
            location_id=LOC_STONE_TOWN,
            name="青石镇",
            kind="town",
            aura_multiplier=0.8,
            adjacency=[LOC_XUANYUE_SECT, LOC_BLACK_MARKET],
        ),
        LOC_XUANYUE_SECT: Location(
            location_id=LOC_XUANYUE_SECT,
            name="玄岳宗",
            kind="sect",
            faction_id=FACTION_XUANYUE,
            aura_multiplier=1.1,
            adjacency=[LOC_STONE_TOWN, LOC_BLACKWOOD_FOREST],
        ),
        LOC_BLACKWOOD_FOREST: Location(
            location_id=LOC_BLACKWOOD_FOREST,
            name="落鸦林",
            kind="wilderness",
            aura_multiplier=0.7,
            adjacency=[LOC_XUANYUE_SECT, LOC_RUINED_TEMPLE, LOC_CHIXIAO_OUTPOST],
        ),
        LOC_RUINED_TEMPLE: Location(
            location_id=LOC_RUINED_TEMPLE,
            name="山间破庙",
            kind="ruin",
            aura_multiplier=0.5,
            adjacency=[LOC_BLACKWOOD_FOREST, LOC_MISTY_VALLEY],
            stash=[ITEM_MAP_FRAGMENT],
        ),
        LOC_MISTY_VALLEY: Location(
            location_id=LOC_MISTY_VALLEY,
            name="迷雾谷",
            kind="wilderness",
            aura_multiplier=0.9,
            adjacency=[LOC_RUINED_TEMPLE, LOC_ANCIENT_CAVE],
        ),
        LOC_ANCIENT_CAVE: Location(
            location_id=LOC_ANCIENT_CAVE,
            name="无名古修洞府",
            kind="secret_realm",
            aura_multiplier=2.0,
            adjacency=[LOC_MISTY_VALLEY],
        ),
        LOC_CHIXIAO_OUTPOST: Location(
            location_id=LOC_CHIXIAO_OUTPOST,
            name="赤霄门外据点",
            kind="outpost",
            faction_id=FACTION_CHIXIAO,
            aura_multiplier=0.9,
            adjacency=[LOC_BLACKWOOD_FOREST],
        ),
        LOC_BLACK_MARKET: Location(
            location_id=LOC_BLACK_MARKET,
            name="黑石集市",
            kind="shop",
            aura_multiplier=0.5,
            adjacency=[LOC_STONE_TOWN],
        ),
    }


def _factions() -> dict[str, Faction]:
    return {
        FACTION_XUANYUE: Faction(
            faction_id=FACTION_XUANYUE,
            name="玄岳宗",
            kind="sect",
            leader_id=npc_id("lu_xuanji"),
            treasury=12000,
            income_per_30d=480,
            upkeep_per_member=8,
        ),
        FACTION_CHIXIAO: Faction(
            faction_id=FACTION_CHIXIAO,
            name="赤霄门",
            kind="sect",
            leader_id=npc_id("huo_ran"),
            treasury=9000,
            income_per_30d=420,
            upkeep_per_member=8,
        ),
    }


def _items() -> dict[str, Item]:
    return {
        ITEM_MAP_FRAGMENT: Item(
            item_id=ITEM_MAP_FRAGMENT,
            name="残破洞府图",
            kind="map",
            unique=True,
            location_id=LOC_RUINED_TEMPLE,
            properties={
                "points_to": LOC_MISTY_VALLEY,
                "realm_id": REALM_ANCIENT_CAVE,
                "description": "半幅兽皮图，标注迷雾谷深处有一处古修遗府。",  # noqa: RUF001
            },
        ),
        ITEM_FOUNDATION_PILL: Item(
            item_id=ITEM_FOUNDATION_PILL,
            name="筑基丹",
            kind="pill",
            unique=True,
            hidden=True,
            properties={"quality": 1.0, "description": "古修遗留的筑基丹，药力浑厚。"},  # noqa: RUF001
        ),
        ITEM_SPIRIT_SWORD: Item(
            item_id=ITEM_SPIRIT_SWORD,
            name="赤鳞剑",
            kind="weapon",
            unique=True,
            owner_id=npc_id("pei_lie"),
            properties={"quality": 0.8},
        ),
        ITEM_TALISMAN: Item(
            item_id=ITEM_TALISMAN,
            name="旧护身符",
            kind="talisman",
            owner_id=PROTAGONIST_ID,
            properties={"quality": 0.3, "description": "入门时师父所赠。"},
        ),
        ITEM_PLAYER_KNIFE: Item(
            item_id=ITEM_PLAYER_KNIFE,
            name="短刀",
            kind="weapon",
            owner_id=PLAYER_ID,
            properties={"quality": 0.2},
        ),
        ITEM_HERB_BUNDLE: Item(
            item_id=ITEM_HERB_BUNDLE,
            name="灵草囊",
            kind="herb",
            owner_id=npc_id("qiao_yun"),
            properties={"quality": 0.4},
        ),
        ITEM_QI_PILL: Item(
            item_id=ITEM_QI_PILL,
            name="聚气丹",
            kind="pill",
            owner_id=npc_id("su_zhi"),
            properties={"quality": 0.5},
        ),
        ITEM_MARKET_TOKEN: Item(
            item_id=ITEM_MARKET_TOKEN,
            name="黑市令牌",
            kind="token",
            owner_id=npc_id("shi_san"),
            properties={},
        ),
        ITEM_JADE_SLIP: Item(
            item_id=ITEM_JADE_SLIP,
            name="玄岳玉简",
            kind="manual",
            owner_id=npc_id("lu_xuanji"),
            properties={"technique": "sect"},
        ),
    }


def _npcs() -> dict[str, Npc]:
    cautious = {"caution": 0.8, "ambition": 0.5, "loyalty": 0.6, "insight": 0.5, "aggression": 0.3}
    rows: list[dict[str, Any]] = [
        dict(
            key="xie_wujiu",
            name="谢无咎",
            role="player",
            faction=None,
            location=LOC_STONE_TOWN,
            realm=1,
            stage=1,
            age_years=19,
            aptitude=0.62,
            luck=1.0,
            technique="basic",
            wealth=30,
            traits={"caution": 0.6, "ambition": 0.7, "loyalty": 0.4, "insight": 0.6},
            goals=[_goal("goal_explore", "explore", 0.8)],
            inventory=[ITEM_PLAYER_KNIFE],
        ),
        dict(
            key="shen_yan",
            name="沈砚",
            role="protagonist",
            faction=FACTION_XUANYUE,
            location=LOC_XUANYUE_SECT,
            realm=1,
            stage=9,
            age_years=18,
            aptitude=0.88,
            luck=1.7,
            technique="sect",
            wealth=40,
            foundation=0.72,
            traits={"caution": 0.82, "ambition": 0.78, "loyalty": 0.55, "insight": 0.74},
            goals=[_goal("goal_breakthrough", "breakthrough", 1.0, target_realm=2)],
            inventory=[ITEM_TALISMAN],
        ),
        dict(
            key="lu_xuanji",
            name="陆玄机",
            role="sect_leader",
            faction=FACTION_XUANYUE,
            location=LOC_XUANYUE_SECT,
            realm=3,
            stage=1,
            age_years=210,
            aptitude=0.8,
            luck=1.2,
            technique="rare",
            wealth=800,
            foundation=0.8,
            traits={"caution": 0.7, "ambition": 0.6, "loyalty": 0.8, "insight": 0.7},
            goals=[_goal("goal_guard_sect", "guard", 0.9)],
            inventory=[ITEM_JADE_SLIP],
        ),
        dict(
            key="huo_ran",
            name="霍燃",
            role="enemy_leader",
            faction=FACTION_CHIXIAO,
            location=LOC_CHIXIAO_OUTPOST,
            realm=3,
            stage=1,
            age_years=190,
            aptitude=0.78,
            luck=1.15,
            technique="rare",
            wealth=700,
            foundation=0.76,
            traits={"caution": 0.4, "ambition": 1.0, "loyalty": 0.5, "insight": 0.6},
            goals=[_goal("goal_expand", "expand", 1.0)],
            inventory=[],
        ),
        dict(
            key="su_zhi",
            name="苏芷",
            role="alchemist_elder",
            faction=FACTION_XUANYUE,
            location=LOC_XUANYUE_SECT,
            realm=2,
            stage=2,
            age_years=96,
            aptitude=0.75,
            luck=1.05,
            technique="sect",
            wealth=600,
            foundation=0.7,
            traits={"caution": 0.6, "ambition": 0.4, "loyalty": 0.8, "insight": 0.65},
            goals=[_goal("goal_accumulate_wealth", "accumulate_wealth", 0.7)],
            inventory=[ITEM_QI_PILL],
        ),
        dict(
            key="pei_lie",
            name="裴烈",
            role="rival",
            faction=FACTION_CHIXIAO,
            location=LOC_CHIXIAO_OUTPOST,
            realm=2,
            stage=1,
            age_years=74,
            aptitude=0.72,
            luck=1.0,
            technique="sect",
            wealth=150,
            foundation=0.62,
            traits={"caution": 0.3, "ambition": 0.9, "loyalty": 0.5, "insight": 0.45},
            goals=[_goal("goal_defeat_rival", "defeat_rival", 0.9, target=PROTAGONIST_ID)],
            inventory=[ITEM_SPIRIT_SWORD],
        ),
    ]

    minor = [
        (
            "lin_wan",
            "林晚",
            "inner_disciple",
            FACTION_XUANYUE,
            LOC_XUANYUE_SECT,
            1,
            6,
            26,
            0.68,
            1.02,
            "sect",
            80,
        ),
        (
            "zhou_mu",
            "周牧",
            "deacon",
            FACTION_XUANYUE,
            LOC_XUANYUE_SECT,
            1,
            5,
            44,
            0.55,
            0.98,
            "sect",
            150,
        ),
        (
            "qiao_yun",
            "乔芸",
            "herb_gatherer",
            FACTION_XUANYUE,
            LOC_BLACKWOOD_FOREST,
            1,
            4,
            31,
            0.6,
            1.1,
            "basic",
            35,
        ),
        ("du_heng", "杜衡", "merchant", None, LOC_STONE_TOWN, 0, 1, 52, 0.4, 1.25, "basic", 900),
        (
            "shi_san",
            "石三",
            "black_marketeer",
            None,
            LOC_BLACK_MARKET,
            0,
            1,
            47,
            0.45,
            1.3,
            "basic",
            1200,
        ),
        ("yan_qing", "燕青", "explorer", None, LOC_STONE_TOWN, 1, 7, 38, 0.65, 1.15, "sect", 120),
        (
            "luo_chuan",
            "罗川",
            "chixiao_deacon",
            FACTION_CHIXIAO,
            LOC_CHIXIAO_OUTPOST,
            1,
            6,
            40,
            0.6,
            1.0,
            "sect",
            100,
        ),
        (
            "bai_lin",
            "白琳",
            "chixiao_disciple",
            FACTION_CHIXIAO,
            LOC_CHIXIAO_OUTPOST,
            1,
            4,
            23,
            0.7,
            1.05,
            "sect",
            50,
        ),
        (
            "chen_jiu",
            "陈九",
            "guard",
            FACTION_XUANYUE,
            LOC_XUANYUE_SECT,
            1,
            3,
            35,
            0.5,
            0.95,
            "basic",
            40,
        ),
        (
            "mu_yu",
            "木雨",
            "wanderer",
            None,
            LOC_BLACKWOOD_FOREST,
            1,
            2,
            29,
            0.58,
            1.08,
            "basic",
            25,
        ),
    ]
    for key, name, role, faction_key, loc, realm, stage, age, apt, luck, tech, wealth in minor:
        rows.append(
            dict(
                key=key,
                name=name,
                role=role,
                faction=faction_key,
                location=loc,
                realm=realm,
                stage=stage,
                age_years=age,
                aptitude=apt,
                luck=luck,
                technique=tech,
                wealth=wealth,
                traits=dict(cautious),
                goals=[_goal(f"goal_cultivate_{key}", "cultivate", 0.6)],
                inventory=[],
            )
        )

    background = [
        ("a_he", "阿禾", "servant", FACTION_XUANYUE, LOC_XUANYUE_SECT, 0, 1, 19, 0.35, 1.0, 5),
        ("shi_tou", "石头", "laborer", None, LOC_STONE_TOWN, 0, 1, 24, 0.3, 0.9, 8),
        (
            "qing_luo",
            "青萝",
            "herb_gatherer",
            FACTION_XUANYUE,
            LOC_BLACKWOOD_FOREST,
            1,
            1,
            22,
            0.5,
            1.0,
            12,
        ),
        ("lao_huai", "老槐", "gardener", FACTION_XUANYUE, LOC_XUANYUE_SECT, 0, 1, 61, 0.3, 0.95, 6),
        ("cai_wei", "采薇", "servant", FACTION_XUANYUE, LOC_XUANYUE_SECT, 0, 1, 18, 0.42, 1.02, 4),
        ("xiao_man", "小满", "cook", None, LOC_STONE_TOWN, 0, 1, 33, 0.32, 1.0, 20),
        (
            "tie_niu",
            "铁牛",
            "guard",
            FACTION_CHIXIAO,
            LOC_CHIXIAO_OUTPOST,
            1,
            2,
            28,
            0.48,
            0.98,
            30,
        ),
        ("liu_sheng", "柳生", "wanderer", None, LOC_BLACKWOOD_FOREST, 1, 1, 34, 0.45, 1.05, 15),
        ("a_xiu", "阿绣", "seamstress", None, LOC_STONE_TOWN, 0, 1, 27, 0.34, 1.0, 26),
        ("gu_san", "顾三", "hunter", None, LOC_BLACKWOOD_FOREST, 0, 1, 39, 0.4, 0.95, 22),
        ("huang_si", "黄四", "laborer", None, LOC_STONE_TOWN, 0, 1, 45, 0.28, 0.9, 10),
        ("qiu_niang", "秋娘", "innkeeper", None, LOC_STONE_TOWN, 0, 1, 48, 0.44, 1.05, 200),
        (
            "shan_que",
            "山雀",
            "messenger",
            FACTION_XUANYUE,
            LOC_XUANYUE_SECT,
            0,
            1,
            16,
            0.38,
            1.08,
            3,
        ),
        ("zhao_wu", "赵五", "guard", None, LOC_STONE_TOWN, 0, 1, 30, 0.42, 0.95, 18),
    ]
    for key, name, role, faction_key, loc, realm, stage, age, apt, luck, wealth in background:
        rows.append(
            dict(
                key=key,
                name=name,
                role=role,
                faction=faction_key,
                location=loc,
                realm=realm,
                stage=stage,
                age_years=age,
                aptitude=apt,
                luck=luck,
                technique="basic",
                wealth=wealth,
                traits=dict(cautious),
                goals=[_goal(f"goal_live_{key}", "live", 0.4)],
                inventory=[],
            )
        )

    npcs: dict[str, Npc] = {}
    for row in rows:
        npc = _make_npc(**row)
        npcs[npc.npc_id] = npc
    return npcs


def _relationships() -> dict[str, Relationship]:
    pairs = [
        ("shen_yan", "su_zhi", 20, 30, 0, 40, 0),
        ("su_zhi", "shen_yan", 15, 20, 0, 30, 0),
        ("shen_yan", "pei_lie", -25, -10, 5, 10, 0),
        ("pei_lie", "shen_yan", -30, -15, 0, 5, 0),
        ("lu_xuanji", "shen_yan", 5, 10, 0, 20, 0),
        ("shen_yan", "lu_xuanji", 0, 10, 6, 30, 0),
        ("huo_ran", "pei_lie", 10, 20, 20, 30, 0),
        ("pei_lie", "huo_ran", 5, 15, 30, 20, 0),
        ("du_heng", "shi_san", 10, 40, 0, 10, 0),
        ("shi_san", "du_heng", 5, 30, 0, 5, 0),
        ("xie_wujiu", "shen_yan", 0, 0, 0, 0, 0),
        ("shen_yan", "xie_wujiu", 0, 0, 0, 0, 0),
    ]
    result: dict[str, Relationship] = {}
    for source, target, affinity, trust, fear, respect, debt in pairs:
        rel = Relationship(
            source_npc_id=npc_id(source),
            target_npc_id=npc_id(target),
            affinity=affinity,
            trust=trust,
            fear=fear,
            respect=respect,
            debt=debt,
        )
        result[relationship_key(rel.source_npc_id, rel.target_npc_id)] = rel
    return result


def _beliefs() -> dict[str, Belief]:
    rows = [
        ("shen_yan", LOC_RUINED_TEMPLE, "holds_ancient_relic", True, 0.78),
        ("shen_yan", LOC_MISTY_VALLEY, "linked_to_relics", True, 0.4),
        ("xie_wujiu", LOC_MISTY_VALLEY, "rumored_realm", True, 0.3),
        ("su_zhi", "shen_yan", "promising_disciple", True, 0.7),
        ("huo_ran", LOC_XUANYUE_SECT, "weakening", True, 0.55),
        ("pei_lie", "shen_yan", "rival", True, 0.9),
        ("du_heng", LOC_RUINED_TEMPLE, "old_rumors", True, 0.5),
    ]
    result: dict[str, Belief] = {}
    for key, subject, predicate, value, confidence in rows:
        belief = Belief(
            npc_id=npc_id(key),
            subject_key=subject,
            predicate=predicate,
            object_value=value,
            confidence=confidence,
            acquired_tick=0,
        )
        result[belief_key(belief.npc_id, belief.subject_key, belief.predicate)] = belief
    return result


def create_world(seed: int = 42) -> WorldState:
    state = WorldState(
        world_id=world_id(seed),
        world_seed=seed,
        tick=0,
        state_version=0,
        last_event_id=0,
        sim_version=SIM_VERSION,
        ruleset_version=RULESET.version,
        player_id=PLAYER_ID,
        npcs=_npcs(),
        locations=_locations(),
        factions=_factions(),
        items=_items(),
        opportunities={
            OPP_FOUNDATION_PILL: Opportunity(
                opportunity_id=OPP_FOUNDATION_PILL,
                name="洞府丹藏",
                kind="pill",
                location_id=LOC_ANCIENT_CAVE,
                reward_item_ids=[ITEM_FOUNDATION_PILL],
                active_from_tick=0,
                active_until_tick=REALM_CLOSE_TICK,
                base_weight=0.35,
                min_realm=1,
                canonical_candidate_id=PROTAGONIST_ID,
                canonical_luck_bias=1.7,
                requires_map_item_id=ITEM_MAP_FRAGMENT,
            )
        },
        secret_realms={
            REALM_ANCIENT_CAVE: SecretRealm(
                realm_id=REALM_ANCIENT_CAVE,
                name="无名古修洞府",
                entrance_location_id=LOC_MISTY_VALLEY,
                interior_location_id=LOC_ANCIENT_CAVE,
                required_item_id=ITEM_MAP_FRAGMENT,
                open_tick=0,
                close_tick=REALM_CLOSE_TICK,
                opened=True,
                discovered_by=[],
            )
        },
        relationships=_relationships(),
        beliefs=_beliefs(),
    )
    return state
