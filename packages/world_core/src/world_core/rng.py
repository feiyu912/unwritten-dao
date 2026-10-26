from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world_core.models import WorldState


def seed_for(state: WorldState, purpose: str, *parts: object) -> int:
    """Stable RNG seed derived from world, tick, purpose, and entity parts."""
    tokens = [str(state.world_seed), str(state.tick), purpose]
    tokens.extend(str(part) for part in parts)
    digest = hashlib.blake2b("|".join(tokens).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1
