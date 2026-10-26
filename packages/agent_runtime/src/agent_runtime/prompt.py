"""Structured planning prompts built only from an NPC observation.

The prompt separates authoritative facts from beliefs and never includes
hidden world truth (the observation layer already enforces that boundary).
"""

from __future__ import annotations

from agent_runtime.models import NpcObservation

SYSTEM_PROMPT = """\
你是一个持久运行的模拟世界中的自主角色。
你可以提出行为，但不能创造世界事实。
只有 WORLD_FACTS 是权威事实；BELIEFS 可能是错误的；未知信息必须保持未知。
你只能使用 AVAILABLE_ACTIONS 中的动作，且只能引用观察中存在的角色、地点与物品。
只输出一个符合 action-proposal.v1 的 JSON 对象，不要输出 Markdown 或解释。
"""

_INTENT_GUIDE = {
    "wait": '{"ticks": 1..365}',
    "move": '{"to_location_id": "<known location id>"}',
    "start_cultivation": '{"days": 1..365}',
    "attempt_breakthrough": '{"pill_item_id": "<owned pill id, optional>"}',
    "transfer_item": (
        '{"item_id": "<id>", "from": {"kind": "npc|location", "id": "<id>"}, '
        '"to": {"kind": "npc|location", "id": "<id>"}}'
    ),
    "investigate": (
        '{"target_location_id": "<current location id>", '
        '"focus": "secret_realm|person|item|rumor"}'
    ),
    "enter_secret_realm": '{"realm_id": "<discovered realm id>"}',
    "claim_opportunity": '{"opportunity_id": "<visible opportunity id>"}',
    "attack": '{"target_id": "<visible npc id>", "intent": "kill|subdue|rob"}',
}


def build_planning_prompt(observation: NpcObservation) -> tuple[str, str]:
    """Return ``(system, user)`` for one planning decision."""
    return SYSTEM_PROMPT, _user_prompt(observation)


def repair_prompt(original_user: str, error: str) -> str:
    """Append one bounded repair instruction to a failed attempt."""
    return (
        f"{original_user}\n\nPREVIOUS_OUTPUT_INVALID\n"
        f"error: {error}\n"
        "Return exactly one valid action-proposal.v1 JSON object. "
        "Do not invent ids or facts.\n"
    )


def _user_prompt(obs: NpcObservation) -> str:
    lines: list[str] = []
    view = obs.self
    lines.append("CHARACTER")
    lines.append(f"名字：{view.name}")
    lines.append(f"境界：{view.realm} 层 {view.stage}")
    lines.append(f"灵力：{view.qi}；根基：{view.foundation:.2f}；气血：{view.health:.2f}")
    lines.append(f"灵石：{view.wealth}；预计余寿：{view.estimated_remaining_life_ticks} 天")
    if view.traits:
        traits = "，".join(f"{key}={value:.2f}" for key, value in sorted(view.traits.items()))
        lines.append(f"性格：{traits}")
    lines.append(f"位置：{obs.location_id}")

    lines.append("\nGOALS")
    active = [goal for goal in obs.goals if goal.status == "active"]
    if active:
        for goal in sorted(active, key=lambda g: (-g.priority, g.goal_id)):
            params = f" {goal.params}" if goal.params else ""
            lines.append(f"- [{goal.goal_id}] {goal.kind} (priority {goal.priority:.2f}){params}")
    else:
        lines.append("- none")

    lines.append("\nINVENTORY")
    if obs.inventory:
        lines.extend(f"- {item.item_id} ({item.name}, {item.kind})" for item in obs.inventory)
    else:
        lines.append("- empty")

    lines.append("\nCURRENT_LOCATION")
    lines.append(f"- {obs.location_id}")
    if obs.visible_items:
        lines.append("可见物品：")
        lines.extend(
            f"- {item.item_id} ({item.name}, {item.kind})" for item in obs.visible_items
        )
    if obs.visible_opportunities:
        lines.append("可见机缘：")
        lines.extend(
            f"- {opp.opportunity_id} ({opp.name}, {opp.kind})" for opp in obs.visible_opportunities
        )
    if obs.visible_npcs:
        lines.append("在场人物：")
        lines.extend(
            f"- {npc.npc_id} ({npc.name}, 境界 {npc.realm} 层 {npc.stage})"
            for npc in obs.visible_npcs
        )

    lines.append("\nKNOWN_LOCATIONS")
    for location in obs.known_locations:
        adjacency = ", ".join(location.adjacent_ids) if location.adjacent_ids else "none"
        lines.append(f"- {location.location_id} ({location.name}, {location.kind}) -> {adjacency}")

    if obs.relationships:
        lines.append("\nRELATIONSHIPS")
        lines.extend(
            f"- {rel.npc_id}: 好感 {rel.affinity}, 信任 {rel.trust}, 敬畏 {rel.fear}, "
            f"敬重 {rel.respect}, 债务 {rel.debt}"
            for rel in obs.relationships
        )

    lines.append("\nWORLD_FACTS")
    lines.append("- 上述自身状态、在场人物、可见物品、可见机缘与已知地点是权威事实。")
    if obs.recent_events:
        lines.extend(
            f"- [E{event.event_id}] {event.summary}" for event in obs.recent_events
        )

    lines.append("\nBELIEFS（可能错误，不能当作事实）")
    if obs.beliefs:
        lines.extend(
            f"- [{belief.subject_key}] {belief.predicate}: {belief.object_value} "
            f"(置信度 {belief.confidence:.2f})"
            for belief in obs.beliefs
        )
    else:
        lines.append("- none")

    lines.append("\nRELEVANT_MEMORIES")
    if obs.memories:
        lines.extend(
            f"- [E{memory.event_id}] {memory.summary} (importance {memory.importance:.2f})"
            for memory in obs.memories
        )
    else:
        lines.append("- none")

    lines.append("\nAVAILABLE_ACTIONS")
    for intent in obs.available_actions:
        lines.append(f"- {intent}: {_INTENT_GUIDE[intent]}")

    goal_id = active[0].goal_id if active else None
    lines.append("\nOUTPUT")
    lines.append(
        "返回 JSON：schema_version, proposal_id, decision_id, npc_id, "
        "observed_world_version, goal_id, intent, arguments, valid_for_ticks, "
        "memory_refs, rationale_short, confidence。"
    )
    lines.append(f"npc_id 必须是 {obs.npc_id}；observed_world_version 必须是 {obs.world_version}。")
    if goal_id:
        lines.append(f"goal_id 建议为 {goal_id}。")
    lines.append("rationale_short 用一句中文说明理由；不得凭空创造资源、人物、地点或事实。")
    return "\n".join(lines)


__all__ = ["SYSTEM_PROMPT", "build_planning_prompt", "repair_prompt"]