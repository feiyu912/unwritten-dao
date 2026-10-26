"""Bounded NPC dialogue with an optional chat-completions provider.

Dialogue is presentation only: it never mutates state and never exposes facts
outside the NPC's observation.
"""

from __future__ import annotations

import os

from world_core.models import Npc, WorldState

from agent_runtime import OpenAICompatibleProvider, ProviderError

DIALOGUE_SYSTEM = """\
你在扮演一个持久运行的修仙模拟世界中的角色。
只输出角色说的话，一到三句，不要输出 JSON、旁白说明或世界事实清单。
你只能依据 WORLD_FACTS 与 BELIEFS 说话；BELIEFS 可能是错的。
不得凭空创造人物、地点、物品或已经发生的事件；不确定时保持含糊。
"""


def _fallback(npc: Npc) -> str:
    return f"（{npc.name}看了你一眼，没有多说。）"


def build_dialogue_prompt(state: WorldState, npc: Npc, player: Npc, message: str) -> str:
    location = state.locations.get(npc.location_id)
    faction = state.factions.get(npc.faction_id) if npc.faction_id else None
    beliefs = [belief for belief in state.beliefs.values() if belief.npc_id == npc.npc_id]
    fact_lines = [
        f"你是{npc.name}，身份是{npc.canonical_role}。",
        f"当前所在：{location.name if location else npc.location_id}。",
        f"境界：{npc.realm} 层 {npc.stage}；气血：{npc.health:.2f}。",
    ]
    if faction is not None:
        fact_lines.append(f"所属势力：{faction.name}。")
    belief_lines = [
        f"{belief.subject_key} {belief.predicate} (置信度 {belief.confidence:.2f})"
        for belief in beliefs
    ] or ["无"]
    return (
        "\n".join(fact_lines)
        + "\nWORLD_FACTS: 以上是权威事实。\nBELIEFS:\n- "
        + "\n- ".join(belief_lines)
        + f"\n\n玩家{player.name}对你说：{message}\n请以{npc.name}的身份回答。"
    )


def generate_dialogue_reply(state: WorldState, npc: Npc, player: Npc, message: str) -> str:
    mode = os.environ.get("AGENT_PROVIDER", "utility").strip().lower()
    if mode == "llm-mock":
        return os.environ.get("LLM_MOCK_DIALOGUE_REPLY") or _fallback(npc)
    if mode != "openai":
        return _fallback(npc)

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL")
    if not base_url or not model:
        raise RuntimeError("AGENT_PROVIDER=openai requires LLM_BASE_URL and LLM_MODEL")
    provider = OpenAICompatibleProvider(
        base_url=base_url,
        model=model,
        api_key=os.environ.get("LLM_API_KEY"),
        timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "20")),
        temperature=float(os.environ.get("LLM_DIALOGUE_TEMPERATURE", "0.7")),
    )
    try:
        reply = provider.complete_text(
            system=DIALOGUE_SYSTEM,
            user=build_dialogue_prompt(state, npc, player, message),
        )
    except ProviderError:
        return _fallback(npc)
    return reply.strip() or _fallback(npc)


__all__ = ["DIALOGUE_SYSTEM", "build_dialogue_prompt", "generate_dialogue_reply"]
