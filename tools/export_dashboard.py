#!/usr/bin/env python3
"""Export a self-contained HTML history dashboard (debug visualization).

    uv run python -m tools.export_dashboard --years 20 --out reports/dashboard.html

This is a development viewer, not the UE5 client.
"""

from __future__ import annotations

import argparse
import html
import math
import pathlib
import sys

from world_server.db import get_engine, get_session_factory
from world_server.repository import NotFound, list_events, load_state
from world_server.summaries import summarize_event

from agent_runtime import find_story_threads
from tools.character_history import character_timeline, find_npc, simulate
from world_core import evaluate_endings, state_checksum, validate_state

POSITIONS = {
    "location_stone_town": (110, 320),
    "location_xuanyue_sect": (260, 200),
    "location_blackwood_forest": (430, 260),
    "location_chixiao_outpost": (430, 420),
    "location_ruined_temple": (560, 180),
    "location_misty_valley": (680, 260),
    "location_ancient_cave": (790, 170),
    "location_black_market": (110, 450),
}

IMPORTANCE = {
    "NPC_DIED": 1.0,
    "BREAKTHROUGH_ATTEMPT": 0.9,
    "SECRET_REALM_DISCOVERED": 0.9,
    "OPPORTUNITY_CLAIMED": 0.8,
    "COMBAT_RESOLVED": 0.8,
    "SECRET_REALM_ENTERED": 0.7,
    "ITEM_TRANSFERRED": 0.5,
}

FACTION_COLORS_BY_NAME = {"玄岳宗": "#5b8def", "赤霄门": "#e05a5a"}
KIND_COLORS = {
    "town": "#3fb27f",
    "sect": "#5b8def",
    "outpost": "#e05a5a",
    "wilderness": "#7a9f5a",
    "ruin": "#b08a4a",
    "shop": "#9a7abf",
    "secret_realm": "#4fd1c5",
}


def _faction_color(state, faction_id: str | None) -> str:
    if faction_id is None:
        return "#8b98a5"
    faction = state.factions.get(faction_id)
    return FACTION_COLORS_BY_NAME.get(faction.name if faction else "", "#3fb27f")


def _esc(text: object) -> str:
    return html.escape(str(text))


def _svg(state) -> str:
    parts = [
        '<svg viewBox="0 0 900 540" role="img" aria-label="region map">',
        '<rect width="900" height="540" fill="#0f1720"/>',
    ]
    drawn = set()
    for location in state.locations.values():
        x1, y1 = POSITIONS[location.location_id]
        for adjacent in location.adjacency:
            pair = tuple(sorted((location.location_id, adjacent)))
            if pair in drawn or adjacent not in POSITIONS:
                continue
            drawn.add(pair)
            x2, y2 = POSITIONS[adjacent]
            parts.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#33465a" stroke-width="2"/>'
            )
    by_location: dict[str, list] = {}
    for npc in state.npcs.values():
        by_location.setdefault(npc.location_id, []).append(npc)
    for location in state.locations.values():
        x, y = POSITIONS[location.location_id]
        color = (
            _faction_color(state, location.faction_id)
            if location.faction_id
            else KIND_COLORS.get(location.kind, "#3fb27f")
        )
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="22" fill="{color}" opacity="0.18" stroke="{color}"/>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 44}" fill="#9fb3c8" font-size="13" '
            f'text-anchor="middle">{_esc(location.name)}</text>'
        )
        members_here = sorted(by_location.get(location.location_id, []), key=lambda n: n.npc_id)
        for index, npc in enumerate(members_here):
            angle = (index / max(1, len(members_here))) * 6.283
            nx = x + 13 * math.cos(angle)
            ny = y + 13 * math.sin(angle)
            dot = _faction_color(state, npc.faction_id)
            opacity = "1" if npc.alive else "0.25"
            parts.append(
                f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="4.5" fill="{dot}" '
                f'opacity="{opacity}"><title>{_esc(npc.name)} · 境界 {npc.realm}'
                f"{' · 已故' if not npc.alive else ''}</title></circle>"
            )
    parts.append("</svg>")
    return "".join(parts)


def _factions(state) -> str:
    rows = []
    for faction in sorted(state.factions.values(), key=lambda item: item.faction_id):
        members = [npc for npc in state.npcs.values() if npc.faction_id == faction.faction_id]
        alive = sum(1 for npc in members if npc.alive)
        rows.append(
            f"<li><strong>{_esc(faction.name)}</strong> —  treasury {faction.treasury} · "
            f"alive {alive}/{len(members)}</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def _characters(state) -> str:
    rows = []
    for npc in sorted(state.npcs.values(), key=lambda item: (-item.realm, item.name)):
        if npc.realm < 2 and npc.canonical_role not in {"protagonist", "player"}:
            continue
        faction = state.factions[npc.faction_id].name if npc.faction_id else "散修"
        status = "在世" if npc.alive else f"已故（{npc.death_cause}）"
        goals = "、".join(f"{goal.kind}:{goal.status}" for goal in npc.goals)
        location = state.locations[npc.location_id].name
        rows.append(
            f"<tr><td>{_esc(npc.name)}</td><td>{_esc(npc.canonical_role)}</td>"
            f"<td>{npc.realm} 层 {npc.stage}</td><td>{_esc(faction)}</td>"
            f"<td>{_esc(location)}</td><td>{_esc(status)}</td>"
            f"<td>{_esc(goals)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>人物</th><th>身份</th><th>境界</th><th>势力</th>"
        "<th>位置</th><th>状态</th><th>目标</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _timeline(state, events) -> str:
    important = sorted(
        (event for event in events if event.type in IMPORTANCE),
        key=lambda event: (-IMPORTANCE[event.type], event.event_id),
    )[:30]
    rows = []
    for event in sorted(important, key=lambda item: item.event_id):
        actor = state.npcs.get(event.actor_ids[0]) if event.actor_ids else None
        who = actor.name if actor else "世界"
        parents = ", ".join(f"E{parent}" for parent in event.causal_parent_ids) or "—"
        rows.append(
            f"<li><span class='tick'>tick {event.tick}</span> "
            f"<span class='ev'>E{event.event_id}</span> <strong>{_esc(who)}</strong> "
            f"{_esc(summarize_event(event.type, event.payload, state))} "
            f"<span class='meta'>← {_esc(parents)}</span></li>"
        )
    return "<ol>" + "".join(rows) + "</ol>" if rows else "<p>无重要事件</p>"


def _threads(state, events) -> str:
    index = {event.event_id: event for event in events}
    rows = []
    for thread in find_story_threads(events):
        steps = "".join(
            f"<li>{_esc(_thread_summary(state, index[event_id]))}</li>"
            for event_id in thread.event_ids
        )
        rows.append(
            f"<li><strong>{_esc(thread.headline)}</strong> "
            f"<span class='meta'>score={thread.score:.2f}</span><ol>{steps}</ol></li>"
        )
    return "<ol>" + "".join(rows) + "</ol>" if rows else "<p>无故事线</p>"


def _thread_summary(state, event) -> str:
    return summarize_event(event.type, event.payload, state)


def _endings(state, events) -> str:
    report = evaluate_endings(state, events)
    item = report["key_item"]
    rows = []
    for ending in report["endings"]:
        evidence = ", ".join(str(event_id) for event_id in ending["evidence_event_ids"]) or "—"
        rows.append(
            f'<li><strong class="ev">{_esc(ending["ending_id"])}</strong> · '
            f'{_esc(ending["summary"])} '
            f'<span class="meta">evidence: {_esc(evidence)}</span></li>'
        )
    holder = _esc(item["holder_name"] or "无主")
    consumed = _esc(item["consumed_by"] or "—")
    return (
        f'<p class="sub">关键物：{_esc(item["name"] or item["item_id"])} · '
        f"持有：{holder} · 服用：{consumed}</p>"
        f'<ol>{"".join(rows)}</ol>'
    )


def build_dashboard(state, events, *, years: int, seed: int) -> str:
    protagonist = find_npc(state, "protagonist")
    life = character_timeline(state, events, protagonist.npc_id)[:12] if protagonist else []
    violations = validate_state(state)
    goal_text = (
        "、".join(f"{goal.kind}:{goal.status}" for goal in protagonist.goals)
        if protagonist
        else "—"
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Unwritten Dao — {years} 年历史</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; background: #0b1118; color: #d7e2ee;
  font: 14px/1.55 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 28px 22px 64px; }}
h1 {{ font-size: 26px; margin: 0 0 4px; }}
h2 {{ font-size: 17px; margin: 30px 0 10px; color: #8fd3ff; }}
.sub {{ color: #7d92a8; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
.card {{ background: #111b26; border: 1px solid #223244; border-radius: 10px; padding: 14px 16px; }}
svg {{ width: 100%; height: auto; border-radius: 10px; border: 1px solid #223244; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #1d2a39; }}
th {{ color: #8fd3ff; font-weight: 600; }}
ol {{ padding-left: 22px; }} li {{ margin: 5px 0; }}
.tick {{ color: #7d92a8; font-variant-numeric: tabular-nums; }}
.ev {{ color: #8fd3ff; }}
.meta {{ color: #667a8f; font-size: 12px; }}
.warn {{ color: #ffb4b4; }}
</style></head><body><main>
<h1>Unwritten Dao · {years} 年历史</h1>
<div class="sub">seed={seed} · tick={state.tick} · checksum={state_checksum(state)[:23]}… ·
调试可视化，非 UE5 客户端</div>
<h2>区域</h2>{_svg(state)}
<div class="grid">
<div class="card"><h2 style="margin-top:0">势力</h2>{_factions(state)}</div>
<div class="card"><h2 style="margin-top:0">主角结局</h2>
<p><strong>{_esc(protagonist.name) if protagonist else "—"}</strong> ·
境界 {protagonist.realm if protagonist else "—"} ·
{"在世" if protagonist and protagonist.alive else "已故"} ·
位置 {_esc(state.locations[protagonist.location_id].name) if protagonist else "—"}</p>
<p class="sub">目标：{_esc(goal_text)}</p>
</div></div>
<h2>主要人物</h2><div class="card">{_characters(state)}</div>
<h2>世界结局（真实事件）</h2><div class="card">{_endings(state, events)}</div>
<h2>重要事件与因果父事件</h2><div class="card">{_timeline(state, events)}</div>
<h2>故事线（真实因果链）</h2><div class="card">{_threads(state, events)}</div>
<h2>主角人生节点</h2><div class="card"><ol>
{"".join(f"<li>{_esc(line)}</li>" for line in life) or "<li>无</li>"}
</ol></div>
<h2>校验</h2><p class="{"warn" if violations else "sub"}">
violations: {_esc(violations) if violations else "none"}</p>
</main></body></html>"""


def dashboard_from_db(session) -> tuple[str, int, bool]:
    state = load_state(session)
    events = []
    after = 0
    while True:
        page = list_events(session, after=after, limit=1000)
        if not page:
            break
        events.extend(page)
        after = page[-1].event_id
    years = max(1, state.tick // 365)
    html_text = build_dashboard(state, events, years=years, seed=state.world_seed)
    return html_text, len(events), not validate_state(state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a history dashboard.")
    parser.add_argument("--years", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("reports/dashboard.html"))
    parser.add_argument("--from-db", action="store_true", help="read the persisted server world")
    args = parser.parse_args(argv)

    if args.from_db:
        session = get_session_factory(get_engine())()
        try:
            page, event_count, valid = dashboard_from_db(session)
        except NotFound:
            print("no world in the database; run tools.seed_history or start the server first")
            return 2
        finally:
            session.close()
    else:
        state, events = simulate(years=args.years, seed=args.seed)
        page = build_dashboard(state, events, years=args.years, seed=args.seed)
        event_count = len(events)
        valid = not validate_state(state)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes, events={event_count})")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
