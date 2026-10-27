#!/usr/bin/env python3
"""Playable headless MVP: manual player commands + autonomous NPCs.

    uv run python -m tools.play
    uv run python -m tools.play --script "look; go 落鸦林; next 7; look; quit"

The simulator remains authoritative. Every command goes through
``world_core.apply_command``; NPCs use the deterministic UtilityPolicy.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from world_server.summaries import summarize_event

from agent_runtime import RivalryPolicy, decide_command
from world_core import (
    PLAYER_ID,
    CommandRejected,
    WorldState,
    advance_time,
    apply_command,
    create_world,
    evaluate_endings,
    make_command,
    restore_snapshot,
    snapshot,
    state_checksum,
    validate_state,
)

_KEY_EVENTS = {
    "ITEM_TRANSFERRED",
    "SECRET_REALM_DISCOVERED",
    "SECRET_REALM_ENTERED",
    "OPPORTUNITY_CLAIMED",
    "BREAKTHROUGH_ATTEMPT",
    "NPC_DIED",
    "COMBAT_RESOLVED",
}

_HELP = """\
命令：
  look                         查看自身、地点、物品、机缘与在场人物
  go <地点 id/名称>             移动一格
  take <物品 id/名称>           从当前地点拾取物品
  investigate                  调查当前地点
  enter <realm_id>             进入已发现的秘境
  claim <opportunity id/名称>  领取可见机缘
  cultivate <天数>             开始修炼
  breakthrough [丹药 id]       尝试突破
  attack <npc id/名称> [kill|subdue|rob]
  next [天数]                  推进时间，NPC 自主行动（默认 1 天）
  save [路径] / load [路径]    存档 / 读档
  help / quit
"""


class Game:
    def __init__(self, state: WorldState) -> None:
        self.state = state
        self.policy = RivalryPolicy()
        self.events: list[Any] = []

    def player(self):
        return self.state.npcs[PLAYER_ID]

    def resolve_location(self, text: str) -> str | None:
        for location in self.state.locations.values():
            if text in {location.location_id, location.name} or location.location_id.endswith(text):
                return location.location_id
        return None

    def resolve_npc(self, text: str) -> str | None:
        for npc in self.state.npcs.values():
            if text in {npc.npc_id, npc.name} or npc.npc_id.startswith(text):
                return npc.npc_id
        return None

    def resolve_item(self, text: str) -> str | None:
        for item in self.state.items.values():
            if text in {item.item_id, item.name} or item.item_id.endswith(text):
                return item.item_id
        return None

    def resolve_opportunity(self, text: str) -> str | None:
        for opportunity in self.state.opportunities.values():
            if text in {opportunity.opportunity_id, opportunity.name}:
                return opportunity.opportunity_id
        return None

    def look(self) -> None:
        player = self.player()
        location = self.state.locations[player.location_id]
        print(
            f"\n{player.name} | 境界 {player.realm} 层 {player.stage} | "
            f"气血 {player.health:.2f} | 灵石 {player.wealth}"
        )
        print(f"地点：{location.name} ({location.location_id})")
        if location.stash:
            names = [self.state.items[i].name for i in location.stash if i in self.state.items]
            print(f"地面物品：{', '.join(names) or '无'}")
        opportunities = [
            opportunity.name
            for opportunity in self.state.opportunities.values()
            if opportunity.location_id == player.location_id and opportunity.claimed_by is None
        ]
        if opportunities:
            print(f"机缘：{', '.join(opportunities)}")
        present = [
            npc.name
            for npc in self.state.npcs.values()
            if npc.alive and npc.npc_id != player.npc_id and npc.location_id == player.location_id
        ]
        if present:
            print(f"在场：{', '.join(present)}")
        exits = [
            self.state.locations[adj].name
            for adj in location.adjacency
            if adj in self.state.locations
        ]
        print(f"出口：{', '.join(exits)}")
        if player.inventory:
            names = [self.state.items[i].name for i in player.inventory if i in self.state.items]
            print(f"背包：{', '.join(names)}")

    def path_to(self, target: str) -> list[str] | None:
        from collections import deque

        start = self.player().location_id
        if target == start:
            return []
        previous: dict[str, str | None] = {start: None}
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            for adjacent in sorted(self.state.locations[node].adjacency):
                if adjacent in previous or adjacent not in self.state.locations:
                    continue
                previous[adjacent] = node
                if adjacent == target:
                    queue.clear()
                    break
                queue.append(adjacent)
        if target not in previous:
            return None
        steps: list[str] = []
        node = target
        while previous[node] is not None:
            steps.append(node)
            node = previous[node]  # type: ignore[assignment]
        return list(reversed(steps))

    def send(self, intent: str, arguments: dict[str, Any]) -> None:
        command = make_command(self.state, PLAYER_ID, intent, arguments, source="player")  # type: ignore[arg-type]
        result = apply_command(self.state, command)
        self.report(result.events)

    def report(self, events: list[Any]) -> None:
        self.events.extend(events)
        for event in events:
            if event.type in _KEY_EVENTS:
                summary = summarize_event(event.type, event.payload, self.state)
                print(f"  [tick {event.tick}] {summary}")

    def advance(self, days: int) -> None:
        for _ in range(days):
            for npc in sorted(self.state.npcs.values(), key=lambda item: item.npc_id):
                if npc.npc_id == PLAYER_ID or not npc.alive:
                    continue
                command = decide_command(self.state, npc.npc_id, self.policy)
                if command is not None:
                    try:
                        result = apply_command(self.state, command)
                    except CommandRejected:
                        continue
                    self.report(result.events)
            result = advance_time(self.state, 1)
            self.report(result.events)
        player = self.player()
        print(f"  现在第 {self.state.tick} 天；气血 {player.health:.2f}；位置 {player.location_id}")

    def save(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot(self.state), ensure_ascii=False, indent=2))
        print(f"已存档：{path}；checksum {state_checksum(self.state)}")

    def load(self, path: pathlib.Path) -> None:
        self.state = restore_snapshot(json.loads(path.read_text()))
        self.events.clear()
        print(f"已读档：{path}；tick {self.state.tick}（结局从当前会话事件重算）")

    def handle(self, line: str) -> bool:
        parts = line.strip().split()
        if not parts:
            return True
        verb, args = parts[0].lower(), parts[1:]
        try:
            if verb in {"quit", "exit"}:
                return False
            if verb == "help":
                print(_HELP)
            elif verb == "look":
                self.look()
            elif verb == "go":
                target = self.resolve_location(" ".join(args))
                if target is None:
                    print("找不到该地点。")
                else:
                    path = self.path_to(target)
                    if path is None:
                        print("没有可行路径。")
                    else:
                        for step in path:
                            self.send("move", {"to_location_id": step})
                        print(f"到达 {self.state.locations[target].name}。")
            elif verb == "take":
                item_id = self.resolve_item(" ".join(args))
                if item_id is None:
                    print("找不到该物品。")
                else:
                    self.send(
                        "transfer_item",
                        {
                            "item_id": item_id,
                            "from": {"kind": "location", "id": self.player().location_id},
                            "to": {"kind": "npc", "id": PLAYER_ID},
                        },
                    )
            elif verb == "investigate":
                self.send(
                    "investigate",
                    {"target_location_id": self.player().location_id, "focus": "secret_realm"},
                )
            elif verb == "enter":
                self.send("enter_secret_realm", {"realm_id": args[0] if args else ""})
            elif verb == "claim":
                opportunity_id = self.resolve_opportunity(" ".join(args))
                if opportunity_id is None:
                    print("找不到该机缘。")
                else:
                    self.send("claim_opportunity", {"opportunity_id": opportunity_id})
            elif verb == "cultivate":
                days = int(args[0]) if args else 30
                self.send("start_cultivation", {"days": days})
            elif verb == "breakthrough":
                pill = self.resolve_item(args[0]) if args else None
                self.send("attempt_breakthrough", {"pill_item_id": pill} if pill else {})
            elif verb == "attack":
                target = self.resolve_npc(args[0]) if args else None
                if target is None:
                    print("找不到目标。")
                else:
                    self.send(
                        "attack",
                        {"target_id": target, "intent": args[1] if len(args) > 1 else "kill"},
                    )
            elif verb == "next":
                self.advance(int(args[0]) if args else 1)
            elif verb == "save":
                self.save(pathlib.Path(args[0] if args else "data/play_save.json"))
            elif verb == "load":
                self.load(pathlib.Path(args[0] if args else "data/play_save.json"))
            else:
                print("未知命令。输入 help 查看帮助。")
        except CommandRejected as exc:
            print(f"被拒绝：{exc.code} — {exc.message}")
        except (ValueError, IndexError) as exc:
            print(f"参数错误：{exc}")
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Playable headless xianxia MVP.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--script", type=str, default=None, help="semicolon-separated commands")
    args = parser.parse_args(argv)

    state = create_world(args.seed)
    game = Game(state)
    print("Unwritten Dao — 无头可玩 MVP（输入 help 查看命令）")
    game.look()

    if args.script:
        for line in args.script.split(";"):
            if line.strip() and not game.handle(line):
                break
    else:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not game.handle(line):
                break

    violations = validate_state(game.state)
    assert not violations, violations
    print(f"\n结束。tick={game.state.tick} checksum={state_checksum(game.state)}")
    report = evaluate_endings(game.state, game.events)
    print("结局：")
    for ending in report["endings"]:
        evidence = ", ".join(str(event_id) for event_id in ending["evidence_event_ids"]) or "—"
        print(f"  {ending['ending_id']} — {ending['summary']}（证据 {evidence}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
