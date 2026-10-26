# MVP scene plan (pre-editor)

**Status: design data only.** No Unreal Engine or Blender is installed in the authoring
environment. Nothing in this file has been imported, compiled, opened in the editor, or
validated on the GPU workstation. Treat every editor step as pending.

## Source of truth

The scene is derived from the authoritative seed world, not authored by hand:

```bash
uv run python clients/unreal/tools/export_scene_layout.py
uv run pytest clients/unreal/tools/test_scene_layout.py -q
```

- Layout file: `clients/unreal/Content/Layout/mvp_scene.json` (schema
  `unreal-scene-layout.v1`).
- Seed: `world_core.create_world(42)`; `source.source_checksum` is the
  `world_core.state_checksum` of that initial state.
- Contents: 8 locations, 30 NPC spawn records, 1 player spawn, and a
  `location_id -> actor tag / streaming level` map.
- Do not hand-edit the JSON. Change the export table in
  `clients/unreal/tools/export_scene_layout.py`, regenerate, and rerun the test.

The layout is developer tooling. It is not a world snapshot and must never be used as
authoritative state at runtime; snapshots from `/v1/world/snapshot` remain the only truth.

## Coordinates

- Units: Unreal centimeters.
- Plane: XY; `+X` east, `+Y` north, `+Z` up. Blockout geometry should sit on `Z = 0`.
- Location coordinates are stable literals in the exporter, not derived from runtime data.
- NPC local offsets are BLAKE2b-derived from the stable `npc_id`, so repeated exports are
  byte-identical across platforms.

## Minimal 3D scene (four areas)

| Scene area | Location | Interaction anchor | Purpose |
|---|---|---|---|
| Courtyard | `location_stone_town` | `town_courtyard` | Player start, town services, first dialogue; default-loaded persistent level. |
| Sect gate | `location_xuanyue_sect` | `sect_gate` | 玄岳宗 facade and gate; faction NPCs (陆玄机, 苏芷, 沈砚). |
| Forest edge | `location_blackwood_forest` | `forest_edge` | 落鸦林 edge; travel toward temple/valley/outpost. |
| Secret-realm entrance | `location_ancient_cave` | `cave_mouth` | Gated cave mouth; marker hidden until discovery. |

The black market, Chixiao outpost, ruined temple, and misty valley are **supporting
locations**: markers and small proxy sets, not full art passes in the MVP. Their JSON
records still exist so commands, NPC locations, and future streaming work use stable IDs.

## Locations

| Location ID | Display name | Kind | Faction ID | Aura | XY (cm) | Anchor | Scene area |
|---|---|---|---|---|---|---|---|
| `location_stone_town` | 青石镇 | town | — | 0.8 | 0, 0 | `town_courtyard` | courtyard |
| `location_xuanyue_sect` | 玄岳宗 | sect | `5119fed7-14e1-5851-afbc-29caacbd9c5a` | 1.1 | 7000, 1200 | `sect_gate` | sect_gate |
| `location_blackwood_forest` | 落鸦林 | wilderness | — | 0.7 | 14500, -800 | `forest_edge` | forest_edge |
| `location_ruined_temple` | 山间破庙 | ruin | — | 0.5 | 20500, 3500 | `temple_courtyard` | supporting |
| `location_misty_valley` | 迷雾谷 | wilderness | — | 0.9 | 26500, 5800 | `valley_trail` | supporting |
| `location_ancient_cave` | 无名古修洞府 | secret_realm | — | 2.0 | 30800, 8600 | `cave_mouth` | secret_realm_entrance |
| `location_chixiao_outpost` | 赤霄门外据点 | outpost | `fc86d6b0-bf16-5c9c-9dd6-486dd7e9a33b` | 0.9 | 17000, -6500 | `outpost_gate` | supporting |
| `location_black_market` | 黑石集市 | shop | — | 0.5 | -3500, -4200 | `market_alley` | supporting |

Adjacency is symmetric and comes from the seed world; the exporter fails if it is not.

## NPC ID -> Actor mapping

`npc_id` (UUID) is the only authoritative key. The Unreal actor tag is derived from it as
`NPC_` + the first 12 uppercase hex characters of the UUID; the actor's `NpcId` property
must be set to the full UUID. The suffix is stable but not a substitute for the UUID.

Spawn 29 `ANpcViewActor` instances for the non-player records at `coordinates_xy_cm`
(courtyard Z = 0), apply `location_actor_map`, and hide actors outside the player's area.
Use the remaining record (`is_player: true`) for the `PlayerStart` and the possessed player
pawn; do not duplicate it as a remote NPC actor. The table is generated from `npc_spawns`;
regenerate it if the exporter output changes.

| Actor tag | NPC ID | Name | Role | Spawn location |
|---|---|---|---|---|
| `NPC_20EFF347148A` | `20eff347-148a-540b-ac58-9fbeece8656c` | 秋娘 | innkeeper | `location_stone_town` |
| `NPC_3FE1B4429E6F` | `3fe1b442-9e6f-5c9a-b5da-7fe61de72059` | 赵五 | guard | `location_stone_town` |
| `NPC_406F2708F41F` | `406f2708-f41f-5fb5-9957-a8f13776b72a` | 谢无咎 | player | `location_stone_town` |
| `NPC_47C9DDC7CDBF` | `47c9ddc7-cdbf-5bbb-8a1c-196cb980e6e9` | 杜衡 | merchant | `location_stone_town` |
| `NPC_5E6D1083EEF3` | `5e6d1083-eef3-5132-aeeb-e73dc46698d2` | 小满 | cook | `location_stone_town` |
| `NPC_78F96568F06C` | `78f96568-f06c-5a0c-b95c-acc98bd7d146` | 燕青 | explorer | `location_stone_town` |
| `NPC_B08828F0A732` | `b08828f0-a732-55a0-b86f-a3a31395d381` | 石头 | laborer | `location_stone_town` |
| `NPC_CD2B74CD090B` | `cd2b74cd-090b-5ea6-b532-00adf37a80da` | 阿绣 | seamstress | `location_stone_town` |
| `NPC_D368C9B0ED4F` | `d368c9b0-ed4f-5aef-b847-959de04ee28d` | 黄四 | laborer | `location_stone_town` |
| `NPC_19B45CF5E81A` | `19b45cf5-e81a-5045-8717-2fc6176b3177` | 苏芷 | alchemist_elder | `location_xuanyue_sect` |
| `NPC_20CE4377A62C` | `20ce4377-a62c-57a2-bbae-44709ea0324f` | 采薇 | servant | `location_xuanyue_sect` |
| `NPC_45367FE3B4EC` | `45367fe3-b4ec-5952-b8a9-56750550143e` | 林晚 | inner_disciple | `location_xuanyue_sect` |
| `NPC_8DBEE2D5C947` | `8dbee2d5-c947-5e64-a134-76ea8f723f70` | 山雀 | messenger | `location_xuanyue_sect` |
| `NPC_C989DE8EB56F` | `c989de8e-b56f-5cb7-995d-5bccfe66307e` | 沈砚 | protagonist | `location_xuanyue_sect` |
| `NPC_D292258A077D` | `d292258a-077d-52b1-b8e0-fb610ea7f8e4` | 阿禾 | servant | `location_xuanyue_sect` |
| `NPC_D6EE6269D432` | `d6ee6269-d432-56ba-9c8d-b9a1c2960646` | 陆玄机 | sect_leader | `location_xuanyue_sect` |
| `NPC_EA18A2B628B6` | `ea18a2b6-28b6-51dd-b2e2-3a702a64bc8e` | 陈九 | guard | `location_xuanyue_sect` |
| `NPC_F268F92C790B` | `f268f92c-790b-5a6b-b805-3fc29140d16e` | 周牧 | deacon | `location_xuanyue_sect` |
| `NPC_F3FBF0600D77` | `f3fbf060-0d77-53d7-8a3a-2462ff965d03` | 老槐 | gardener | `location_xuanyue_sect` |
| `NPC_403266381037` | `40326638-1037-5021-8c3e-4226f5034299` | 乔芸 | herb_gatherer | `location_blackwood_forest` |
| `NPC_996ED1724204` | `996ed172-4204-577b-8d57-08227faaf23a` | 柳生 | wanderer | `location_blackwood_forest` |
| `NPC_9DA18CA2E984` | `9da18ca2-e984-5632-b77c-bbf0d0a106a7` | 木雨 | wanderer | `location_blackwood_forest` |
| `NPC_C57263808D83` | `c5726380-8d83-59ee-a88d-06327140f834` | 青萝 | herb_gatherer | `location_blackwood_forest` |
| `NPC_FA0E315A2440` | `fa0e315a-2440-59f0-8e57-8e799503666b` | 顾三 | hunter | `location_blackwood_forest` |
| `NPC_0423E919E5F8` | `0423e919-e5f8-5a43-8924-f960e5b88a7d` | 罗川 | chixiao_deacon | `location_chixiao_outpost` |
| `NPC_4F7AC7C6F8DE` | `4f7ac7c6-f8de-55d9-a16a-4bcef2c2f9c5` | 白琳 | chixiao_disciple | `location_chixiao_outpost` |
| `NPC_A3EF437B4D62` | `a3ef437b-4d62-5f15-aec8-22909f1fe7f7` | 霍燃 | enemy_leader | `location_chixiao_outpost` |
| `NPC_AAED2AB610D5` | `aaed2ab6-10d5-50c5-9cef-e844ef3dac3f` | 裴烈 | rival | `location_chixiao_outpost` |
| `NPC_F60DAB51AF6C` | `f60dab51-af6c-50e7-9939-7e950049609a` | 铁牛 | guard | `location_chixiao_outpost` |
| `NPC_4B5841F81139` | `4b5841f8-1139-561c-8611-6a9a7be9e0c5` | 石三 | black_marketeer | `location_black_market` |

Player spawn (`player_spawn`): `谢无咎`, NPC ID
`406f2708-f41f-5fb5-9957-a8f13776b72a`, location `location_stone_town`, XY
`44.8, 290.8`, actor tag `NPC_406F2708F41F`. Place the `PlayerStart` and the possessed pawn
at these coordinates; do not spawn a second world NPC for the player.

## Animation state mapping

All animation is presentation only and is derived from snapshot/event data. No state
machine in the client may infer rules, combat outcomes, or movement authority.

| Animation state | Authoritative signal | Presentation |
|---|---|---|
| `idle` | `alive == true`, no `active_action`, no confirmed movement target. | Loop idle; face camera/nearest player. |
| `walk` | Player/NPC `move` command accepted and `NPC_MOVED` or new snapshot confirms the destination. | Locomotion montage while `ANpcViewActor` interpolates to the confirmed target; snap on resync. |
| `cultivate` | `npc.active_action.type == "cultivate"`. | Seated/cultivation loop at the location marker; still cancellable by a new snapshot. |
| `combat` | `COMBAT_RESOLVED` event for this actor; play a short one-shot montage. | One-shot attack/hit reaction from event payload (`attacker_won`, `damage`); no local combat simulation or health math. |
| `dead` | `alive == false` (or `NPC_DIED`). | Dead pose/ragdoll placeholder, clear movement, disable interaction and collision; remove from active NPC list after the death notification. |

`combat` is a presentation event, not a persistent state. Revert to the snapshot-derived
state after the montage.

## Interaction triggers

Each trigger only submits a command or dialogue request and waits for authoritative
confirmation. Never apply the result locally.

| Trigger | Where | Request | Preconditions / notes |
|---|---|---|---|
| Investigate | `temple_courtyard`, `valley_trail`, `sect_gate` anchors | `POST /v1/commands`, type `investigate`, `{ "target_location_id": "<current location>" }` | Actor must be at the location; may discover the realm and emit `SECRET_REALM_DISCOVERED`. |
| Take | item/opportunity markers (ruined temple stash, cave opportunity) | `transfer_item` with `{ item_id, from: {kind:"location", id}, to: {kind:"npc", id:player} }`, or `claim_opportunity` with `{ opportunity_id }` | Item must be visible and present; opportunity has realm/map/expiry checks. |
| Enter realm | `cave_mouth` | `enter_secret_realm`, `{ "realm_id": "realm_ancient_cave" }` | Actor must be at `location_misty_valley`, be in `discovered_by`, hold the map, and the realm must be open (tick 0–5475). |
| Dialogue | Any alive NPC | `POST /v1/dialogue` with `npc_id`, `player_id`, `message` | Bounded text; show `reply_text`; never auto-apply the optional proposal. |

Interaction volumes should be small trigger spheres at the anchor coordinates. The prompt
appears only when the player is inside the volume and the server state permits it.

## Secrecy

`location_ancient_cave` is exported because the seed world contains it, not because the
player knows it. Its marker, streaming level, and cave-mouth prompt stay hidden until the
client receives `SECRET_REALM_DISCOVERED` for the player (or the snapshot shows the interior
location). Do not add map labels, rumors, or ambient hints for it. The other locations are
public seed-world areas; their records may be shown on the map.

## Placeholder-only

Until a licensed art pass is approved, these are placeholders and must be swappable without
C++/Blueprint changes: blockout walls/floors/gate, forest tree cards, cave rock shell,
temple props, NPC mannequin bodies, all locomotion/combat/cultivation animations, UMG
layouts and fonts, ambient audio, lighting, sky, and VFX. See `docs/asset-list.md` and
`docs/asset-licenses.md`.

## Still requires UE5

Layout import, actor placement, C++ compile/binding, NavMesh, streaming, UMG, Play-in-Editor,
packaging, and captures are unverified here. Follow `docs/editor-checklist.md` on the GPU
workstation.