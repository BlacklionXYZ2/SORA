"""The decision layer (System-1): which tool families SORA's brain is offered for each message.

See docs/plans/DECISION_LAYER_2026-10-08.md. The model is a swappable slot; the first one is
native (untrained) Laya, run by the ggmlc ``laya`` daemon on the GPU.
"""

from sora.decision.families import FAMILIES, Family, allowed_operations
from sora.decision.laya import Decision, LayaDecisionLayer

__all__ = ["FAMILIES", "Decision", "Family", "LayaDecisionLayer", "allowed_operations"]
