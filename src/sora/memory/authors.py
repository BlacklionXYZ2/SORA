"""Who a memory came from. Her own thoughts are ordinary memories with this provenance."""

from __future__ import annotations

from sora.persistence.records import StoredMemory

OWN_THOUGHT = "SORA's own thought"


def is_own_thought(memory: StoredMemory) -> bool:
    return memory.provenance.startswith(OWN_THOUGHT)
