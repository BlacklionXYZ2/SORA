from __future__ import annotations

import pytest

from sora.workspaces.synthesis import (
    SynthesisCandidate,
    SynthesisConsensus,
    SynthesisEngine,
)


def test_synthesis_full_agreement() -> None:
    engine = SynthesisEngine()
    candidate_1 = SynthesisCandidate(
        run_id="run-1",
        provider="codex",
        outcome="completed",
        summary="Fixed bug in auth",
        conclusion="Auth patch verified",
        diff="--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed=("auth.py",),
        verification_commands=("pytest tests/test_auth.py",),
    )
    candidate_2 = SynthesisCandidate(
        run_id="run-2",
        provider="hermes",
        outcome="completed",
        summary="Fixed bug in auth",
        conclusion="Auth patch verified",
        diff="--- a/auth.py\n+++ b/auth.py\n@@ -1 +1 @@\n-old\n+new\n",
        files_changed=("auth.py",),
        verification_commands=("pytest tests/test_auth.py",),
    )

    result = engine.synthesize("task-1", [candidate_1, candidate_2])
    assert result.consensus is SynthesisConsensus.FULL_AGREEMENT
    assert result.agreed_files == ("auth.py",)
    assert not result.conflicting_files
    assert not result.disagreements
    assert not result.failures
    assert "Consensus: full_agreement." in result.summary


def test_synthesis_disagreement_on_conflicting_diff() -> None:
    engine = SynthesisEngine()
    candidate_1 = SynthesisCandidate(
        run_id="run-1",
        provider="codex",
        outcome="completed",
        summary="Approach A",
        conclusion="Use method A",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-val\n+optA\n",
        files_changed=("main.py",),
    )
    candidate_2 = SynthesisCandidate(
        run_id="run-2",
        provider="antigravity",
        outcome="completed",
        summary="Approach B",
        conclusion="Use method B",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-val\n+optB\n",
        files_changed=("main.py",),
    )

    result = engine.synthesize("task-2", [candidate_1, candidate_2])
    assert result.consensus is SynthesisConsensus.DISAGREEMENT
    assert "main.py" in result.conflicting_files
    assert len(result.disagreements) > 0
    assert not result.failures


def test_synthesis_partial_agreement_on_disjoint_files() -> None:
    engine = SynthesisEngine()
    candidate_1 = SynthesisCandidate(
        run_id="run-1",
        provider="codex",
        outcome="completed",
        summary="Added tests",
        conclusion="Tests added",
        diff="--- a/test_feature.py\n+++ b/test_feature.py\n@@ -0,0 +1 @@\n+test\n",
        files_changed=("test_feature.py",),
    )
    candidate_2 = SynthesisCandidate(
        run_id="run-2",
        provider="hermes",
        outcome="completed",
        summary="Added docs",
        conclusion="Docs added",
        diff="--- a/docs.md\n+++ b/docs.md\n@@ -0,0 +1 @@\n+doc\n",
        files_changed=("docs.md",),
    )

    result = engine.synthesize("task-3", [candidate_1, candidate_2])
    assert result.consensus is SynthesisConsensus.PARTIAL_AGREEMENT
    assert not result.conflicting_files


def test_synthesis_partial_failure_retains_visibility() -> None:
    engine = SynthesisEngine()
    candidate_1 = SynthesisCandidate(
        run_id="run-1",
        provider="codex",
        outcome="completed",
        summary="Succeeded",
        conclusion="Fixed",
        diff="--- a/fix.py\n+++ b/fix.py\n@@ -1 +1 @@\n-bad\n+good\n",
        files_changed=("fix.py",),
    )
    candidate_2 = SynthesisCandidate(
        run_id="run-2",
        provider="hermes",
        outcome="failed",
        summary="Timed out",
        error="Process deadline exceeded after 30s",
    )

    result = engine.synthesize("task-4", [candidate_1, candidate_2])
    assert result.consensus is SynthesisConsensus.PARTIAL_FAILURE
    assert len(result.failures) == 1
    assert "hermes" in result.failures[0]
    assert "deadline exceeded" in result.failures[0]


def test_synthesis_all_failed() -> None:
    engine = SynthesisEngine()
    candidate_1 = SynthesisCandidate(
        run_id="run-1",
        provider="codex",
        outcome="failed",
        error="Connection refused",
    )
    candidate_2 = SynthesisCandidate(
        run_id="run-2",
        provider="antigravity",
        outcome="failed",
        error="Model quota exhausted",
    )

    result = engine.synthesize("task-5", [candidate_1, candidate_2])
    assert result.consensus is SynthesisConsensus.ALL_FAILED
    assert len(result.failures) == 2
    assert "Connection refused" in result.failures[0]
    assert "quota exhausted" in result.failures[1]


def test_synthesis_rejects_empty_candidates() -> None:
    engine = SynthesisEngine()
    with pytest.raises(ValueError, match="at least one candidate"):
        engine.synthesize("task-empty", [])


def test_synthesis_compares_each_file_not_the_candidate_wide_diff() -> None:
    engine = SynthesisEngine()
    shared = "diff --git a/shared.py b/shared.py\n-old\n+same\n"
    candidate_1 = SynthesisCandidate(
        run_id="run-1",
        provider="codex",
        outcome="completed",
        conclusion="same conclusion",
        diff=shared + "diff --git a/a.py b/a.py\n-old\n+a\n",
        files_changed=("shared.py", "a.py"),
        file_diffs={"shared.py": shared, "a.py": "a-change"},
    )
    candidate_2 = SynthesisCandidate(
        run_id="run-2",
        provider="hermes",
        outcome="completed",
        conclusion="same conclusion",
        diff=shared + "diff --git a/b.py b/b.py\n-old\n+b\n",
        files_changed=("shared.py", "b.py"),
        file_diffs={"shared.py": shared, "b.py": "b-change"},
    )

    result = engine.synthesize("task-file-specific", [candidate_1, candidate_2])
    assert result.agreed_files == ("shared.py",)
    assert result.conflicting_files == ()
