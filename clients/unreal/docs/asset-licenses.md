# Asset licenses and provenance

**Status: policy draft, not legal advice.** Terms change; verify the current license on the
source page at download time and keep a copy of the terms with the asset. This repository is
public, so redistribution rules matter more than they would in a private project.

## Rule: record source and license before commit

No binary asset enters `clients/unreal/Content/` (or Git history) until its row is recorded
in `docs/asset-list.md` and, where the license is non-trivial, a copy of the license text is
stored next to the asset under a `Licenses/` folder. Record at least:

| Field | Example |
|---|---|
| Asset name / version | `Modular rock kit v2` |
| Author / publisher | studio or artist name |
| Source page | exact URL copied from the download page |
| License name and version | `CC0 1.0`, `CC BY 4.0`, `Epic Content License`, per-listing Fab license |
| Downloaded on | ISO date |
| Modifications | retopo, texture resize, material changes |
| UE content path | `/Game/Environment/Rocks/...` |
| Redistribution allowed in public repo? | yes / no / only as packaged build |
| License file stored at | `Licenses/<asset>/LICENSE.txt` |

If any field is unknown, the asset is not approved. A reviewer must confirm the row before
the binary is committed.

**Default for third-party binaries in this public repo: do not commit them.** Keep them in a
local/CI artifact store or Git LFS only after confirming the license permits public
redistribution. Importing a Fab/Megascans asset into a `.uasset` does not automatically grant
redistribution rights to that `.uasset`.

## Approved source categories

| Category | Examples (names only) | Typical license | Key constraints |
|---|---|---|---|
| Project-original / Blender-generated | blockout meshes, simple props, custom materials made for this project | Project copyright (optionally CC0-dedicated) | Preferred. Must not bake in third-party textures or scanned data. Record the author and date. |
| Epic Games / Fab / Quixel | Fab marketplace listings, Epic sample content, Quixel Megascans | Epic Content License / Fab EULA, or a per-listing license | Generally usable inside Unreal projects, including commercial builds, but not redistributable as standalone assets or asset packs. Some listings are CC BY or have extra restrictions; check each listing. Megascans terms have changed over time; re-verify at download. |
| CC0 / public-domain dedication | Kenney, Poly Haven, ambientCG, Quaternius | CC0 1.0 | No attribution required, but provenance is still recorded. Sites can mix licenses per item, so check the item page. |
| CC BY | OpenGameArt, Sketchfab CC-BY items, Wikimedia Commons | CC BY 3.0/4.0 | Attribution is mandatory in credits and packaged builds; keep the license text. Verify the exact author string. |
| Fonts | Noto Sans CJK, Source Han Sans | SIL Open Font License 1.1 | Include the OFL text; do not sell the font standalone; respect reserved font names. CJK coverage is required for this project. |
| Audio | freesound items, CC0 music packs | Per-file: CC0 or CC BY | Freesound licenses vary per sound; record each file. Avoid non-commercial and no-derivatives tracks. |
| Public domain (non-CC0) | old scans, government works | Jurisdiction-dependent | Verify that the work is actually public domain where the team and players are located; record the evidence. |
| AI-generated placeholders | generated textures/concept images | Provider terms + project policy | Check the provider's commercial terms and disclosure requirements; keep prompts and generation metadata. Not a substitute for a license record. |

## Licenses to avoid for the MVP

- No license, "free download", or a license that cannot be found.
- Ripped or extracted assets from commercial games, films, or other projects.
- CC BY-NC (non-commercial), CC BY-ND (no derivatives), or "personal use only" assets in a
  build that may be sold or publicly distributed.
- CC BY-SA / GPL assets whose share-alike terms would force the project's own assets or code
  to be relicensed; require explicit approval before use.
- Marketplace preview images, watermarked samples, or trial assets.
- Photogrammetry or scans with unclear provenance or model-release issues (people, private
  property, cultural sites).

## Category-specific notes

### Epic / Fab / Quixel

- The Epic Content License and Fab EULA govern most Unreal-native content. Read the license
  attached to the specific listing; Fab hosts multiple license types.
- Quixel Megascans are intended for use in Unreal Engine projects. Do not redistribute raw
  Megascans textures, meshes, or brush assets, and do not use them outside the engine in a
  way the current terms forbid.
- Epic sample projects (for example the mannequin and starter animations) are covered by the
  Epic Content License; keep the notice and do not repackage them as a standalone asset pack.

### CC0

- CC0 is a public-domain dedication, not a trademark grant. Do not imply the original author
  endorses the project.
- Record the item page and the exact CC0 version; some sites label "free" without CC0.

### CC BY

- Put the required attribution in an in-game credits screen and in `docs/asset-list.md`.
- Include the license text and a link to the license deed in the packaged build's notices.
- Do not add DRM or terms that contradict the license.

### Fonts

- Use an OFL-licensed CJK font; bundle the OFL text.
- Do not rename a reserved font name without permission.
- Avoid system fonts with unclear redistribution terms in a packaged Linux build.

### Audio

- Record the license per file, not per pack.
- Avoid "royalty-free" libraries whose terms forbid redistribution inside a game package;
  confirm the terms allow embedding in a build.

## Review checklist

1. Asset is listed in `docs/asset-list.md` with source, author, license, date, and modifications.
2. License text is stored under `Licenses/` when attribution or notice is required.
3. Attribution strings are added to the credits widget and packaged notices.
4. The license allows the intended distribution (public repo, free build, or commercial build).
5. No third-party asset is committed as a raw source file or a standalone `.uasset` pack
   unless redistribution is permitted.
6. A second reviewer confirms the row before the commit that adds the binary.

If a license is ambiguous, do not commit the asset; replace it with an original blockout or a
CC0 placeholder until the ambiguity is resolved.