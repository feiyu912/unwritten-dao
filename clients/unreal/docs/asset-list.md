# Asset list (MVP)

Use original or properly licensed assets only. Prefer modular, low-poly placeholders that can be
replaced without touching C++ or Blueprint logic.

| Asset | Purpose | Format | Budget |
|---|---|---|---|
| Courtyard floor/walls/roof | Town starting area | FBX/OBJ + 2K PBR textures | ≤ 20k tris per module |
| Sect gate + hall facade | 玄岳宗山门 | FBX + trim sheet | ≤ 50k tris |
| Forest cluster (5–8 variants) | 落鸦林 edge | FBX + foliage cards | ≤ 8k tris each |
| Cave entrance + interior shell | Secret realm entrance | FBX + modular rock kit | ≤ 30k tris |
| Ruined temple props | Map fragment site | FBX kit | ≤ 15k tris |
| Two humanoid silhouettes | Placeholder NPC bodies | UE mannequin / compatible rig | — |
| Text UI font | Dialogue and notifications | TTF/OTF with CJK coverage | — |
| Ambient audio loop | Optional MVP polish | WAV/OGG | ≤ 10 MB |

## Constraints

- No scanned photogrammetry or unlicensed marketplace assets.
- Total first-load package target: keep under ~1 GB for the MVP map.
- Record the license and source for every external asset in this file before committing binaries.
- Character animation: reuse UE mannequin locomotion; no custom motion capture in the MVP.
- Follow `docs/asset-licenses.md` for source categories, redistribution limits, and the
  pre-commit provenance checklist; keep the license text under `Licenses/` when required.
