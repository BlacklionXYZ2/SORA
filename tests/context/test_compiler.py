from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from sora.context.compiler import ContextBudgetError, ContextItem, ContextSource, compile_context
from sora.identity.loader import load_identity

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"
GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "context"
NOW = datetime(2026, 9, 7, 17, 0, tzinfo=UTC)


def test_context_preserves_constraints_scope_and_epistemic_labels() -> None:
    exact_constraint = "Never modify the source checkout."
    items = (
        ContextItem(
            source_id="fact-001",
            source=ContextSource.FACT,
            owner_id="owner-local",
            project_id="project-sora",
            content="The active project is SORA.",
        ),
        ContextItem(
            source_id="inference-001",
            source=ContextSource.INFERENCE,
            owner_id="owner-local",
            project_id="project-sora",
            content="The user may prefer a dark interface.",
        ),
        ContextItem(
            source_id="private-other-project",
            source=ContextSource.MEMORY,
            owner_id="owner-local",
            project_id="project-private",
            content="PRIVATE OTHER PROJECT CONTENT",
        ),
    )

    compiled = compile_context(
        identity=load_identity(IDENTITY_ROOT),
        owner_id="owner-local",
        project_id="project-sora",
        constraints=(exact_constraint,),
        items=items,
        observed_at=NOW,
        max_chars=2_000,
    )

    assert exact_constraint in compiled.text
    assert "[FACT:fact-001]" in compiled.text
    assert "[INFERENCE:inference-001]" in compiled.text
    assert "PRIVATE OTHER PROJECT CONTENT" not in compiled.text
    excluded = {entry.source_id: entry.reason for entry in compiled.manifest.entries}
    assert excluded["private-other-project"] == "project_scope_mismatch"


def test_scoped_context_matches_golden_fixture() -> None:
    fixture = cast(
        dict[str, object],
        json.loads((GOLDEN_ROOT / "scoped_context.json").read_text(encoding="utf-8")),
    )
    raw_items = cast(list[dict[str, object]], fixture["items"])
    items = tuple(ContextItem.model_validate(item) for item in raw_items)
    compiled = compile_context(
        identity=load_identity(IDENTITY_ROOT),
        owner_id=cast(str, fixture["owner_id"]),
        project_id=cast(str, fixture["project_id"]),
        constraints=tuple(cast(list[str], fixture["constraints"])),
        items=items,
        observed_at=NOW,
        max_chars=2_000,
    )

    for expected in cast(list[str], fixture["expected_included"]):
        assert expected in compiled.text
    for excluded in cast(list[str], fixture["expected_excluded"]):
        assert excluded not in compiled.text
    reasons = {entry.source_id: entry.reason for entry in compiled.manifest.entries}
    assert reasons | cast(dict[str, str], fixture["expected_manifest_reason"]) == reasons


def test_budget_never_silently_truncates_exact_constraints() -> None:
    with pytest.raises(ContextBudgetError):
        compile_context(
            identity=load_identity(IDENTITY_ROOT),
            owner_id="owner-local",
            project_id="project-sora",
            constraints=("X" * 2_000,),
            items=(),
            observed_at=NOW,
            max_chars=500,
        )


def test_budget_excludes_low_priority_content_with_manifest_reason() -> None:
    large_inference = ContextItem(
        source_id="inference-large",
        source=ContextSource.INFERENCE,
        owner_id="owner-local",
        project_id="project-sora",
        content="speculation " * 200,
    )
    compiled = compile_context(
        identity=load_identity(IDENTITY_ROOT),
        owner_id="owner-local",
        project_id="project-sora",
        constraints=("Keep this exact.",),
        items=(large_inference,),
        observed_at=NOW,
        max_chars=1_600,
    )

    assert "Keep this exact." in compiled.text
    assert "speculation" not in compiled.text
    assert compiled.manifest.entries[0].reason == "budget_excluded"
