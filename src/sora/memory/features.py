"""Features for the memory manager's three small layers (MEMORY_MANAGER_2026-10-08 §4).

One definition serves the manager (deciding and logging), the use-case probe and training, so a
trained layer always sees exactly the features it was trained on. Each layer's features are a
fixed, named tuple; a layer file records the names it was trained with.

- acceptance: should this remembered moment be kept?
- relevance: is this part of the moment (her reply, a read result, an image) worth keeping with
  the owner's words?
- same_subject: are two memories about the same fact (a repeat or an update)?
- update: given the same subject, does the newer one replace the older one?

Until a layer is trained, ``Thresholds`` gives the fixed policy, calibrated on the 2026-10-09
probes for EmbeddingGemma 2 at 512 dimensions.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from sora.memory.vectors import cosine, mean_vector

ACCEPTANCE = ("nearest_similarity", "similar_recent", "log_chars", "is_question",
              "first_person", "personal_prototype", "chatter_prototype", "nominated",
              "own_thought")
RELEVANCE = ("similarity_to_owner", "similarity_to_entry", "max_similarity_same_type",
             "type_reply", "type_read", "type_image", "type_audio", "type_caption", "log_size")
COMPARISON = ("similarity", "token_jaccard", "number_mismatch", "change_marker",
              "negation_mismatch", "length_ratio", "log_days_apart")
FEATURES = {"acceptance": ACCEPTANCE, "relevance": RELEVANCE, "same_subject": COMPARISON,
            "update": COMPARISON}
PART_TYPES = ("reply", "read", "image", "audio", "caption")

# Prototype sentences for "worth remembering" versus passing chatter (similarity role). They are
# features, not rules; the acceptance layer learns how much they matter.
PERSONAL = (
    "The owner told me a lasting fact about themselves.",
    "Something the owner likes, dislikes or prefers.",
    "A person in the owner's life: family, friends, a pet.",
    "The owner's plans, deadlines, exams or appointments.",
    "Where the owner keeps something, or what they own.",
    "How the owner wants me to behave from now on.",
)
CHATTER = (
    "A greeting or a passing remark with nothing to remember.",
    "A question about the screen or a window right now.",
    "A one-off command: open, move, point, wave or walk.",
    "Thanks, okay, yes, no, cool, never mind.",
)


@dataclass(frozen=True)
class Thresholds:
    """The fixed policy used until a layer is trained (and its baseline in training reports).

    Calibrated on the use-case probe, 2026-10-09 (fabricated data, EmbeddingGemma 2 Q4_K_XL,
    512 dimensions; docs/verification/MEMORY_USE_CASES_Opus-5.5_2026-10-09.md).
    """

    related: float = 0.77  # related pairs 0.766-0.841; unrelated topped out at 0.765
    same_subject: float = 0.85  # same 0.893+, updated 0.831-0.948; related below 0.85
    related_links: int = 5  # most related links kept per memory
    part_relevance: float = 0.79  # relevant text parts 0.80+, unrelated up to 0.784
    image_relevance: float = 0.63  # owner message (query) to image: 0.686+ vs 0.584 or less
    image_duplicate: float = 0.91  # same screen re-encoded or cropped: 0.858-1.0; others to 0.921
    audio_relevance: float = 0.68  # spoken clip to its text: 0.692+; to other texts 0.664 or less
    recall_floor: float = 0.74  # questions found their memory at 0.745+; off-topic median 0.707
    recall_limit: int = 10
    importance_weight: float = 0.05
    recency_weight: float = 0.05
    recency_days: float = 30.0


_WORD = re.compile(r"[a-z0-9']+")
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)?")
_STOP = frozenset(
    "a an the and or but to of in on at for with from by is are was were be been am i my me "
    "mine you your it its this that these those he she they we our his her their them do does "
    "did have has had so as just really very about into".split()
)
_CHANGE = re.compile(
    r"\b(now|nowadays|anymore|any more|no longer|not any ?more|changed?|switched|moved|"
    r"instead|these days|actually|new|from now on|stopped|started|used to)\b", re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(not|never|no|don't|doesn't|didn't|isn't|aren't|can't|won't|"
                       r"hate|dislike)\b|n't\b", re.IGNORECASE)
_QUESTION = re.compile(r"^\s*(what|where|when|who|why|how|which|is|are|do|does|did|can|could|"
                       r"would|should|will)\b", re.IGNORECASE)
_FIRST = re.compile(r"\b(i|i'm|i've|i'd|i'll|my|me|mine|myself)\b", re.IGNORECASE)


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if w not in _STOP}


def comparison(newer: str, older: str, similarity: float, days_apart: float) -> dict[str, float]:
    a, b = words(newer), words(older)
    numbers_a, numbers_b = set(_NUMBER.findall(newer)), set(_NUMBER.findall(older))
    length_a, length_b = len(newer.split()) or 1, len(older.split()) or 1
    return {
        "similarity": similarity,
        "token_jaccard": len(a & b) / len(a | b) if a | b else 0.0,
        "number_mismatch": float(bool(numbers_a and numbers_b and numbers_a != numbers_b)),
        "change_marker": float(bool(_CHANGE.search(newer))),
        "negation_mismatch": float(bool(_NEGATION.search(newer)) != bool(_NEGATION.search(older))),
        "length_ratio": min(length_a, length_b) / max(length_a, length_b),
        "log_days_apart": math.log1p(max(0.0, days_apart)),
    }


def acceptance(
    text: str, *, nearest_similarity: float, similar_recent: int, personal: float,
    chatter: float, nominated: bool = True, own_thought: bool = False,
) -> dict[str, float]:
    stripped = text.strip()
    return {
        "nearest_similarity": nearest_similarity,
        "similar_recent": float(min(similar_recent, 5)),
        "log_chars": math.log1p(len(stripped)),
        "is_question": float(stripped.endswith("?") or bool(_QUESTION.match(stripped))),
        "first_person": float(bool(_FIRST.search(stripped))),
        "personal_prototype": personal,
        "chatter_prototype": chatter,
        "nominated": float(nominated),
        "own_thought": float(own_thought),
    }


def relevance(
    part_type: str, *, similarity_to_owner: float, similarity_to_entry: float,
    max_similarity_same_type: float, size: float,
) -> dict[str, float]:
    features = {
        "similarity_to_owner": similarity_to_owner,
        "similarity_to_entry": similarity_to_entry,
        "max_similarity_same_type": max_similarity_same_type,
        "log_size": math.log1p(max(0.0, size)),
    }
    for kind in PART_TYPES:
        features[f"type_{kind}"] = float(part_type == kind)
    return features


def prototype_score(vector: Sequence[float], prototypes: Sequence[Sequence[float]]) -> float:
    """Closest prototype; prototypes are embedded once with the similarity role."""
    return max((cosine(vector, prototype) for prototype in prototypes), default=0.0)


def entry_vector(parts: Sequence[Sequence[float]]) -> list[float]:
    return mean_vector(parts) if parts else []
