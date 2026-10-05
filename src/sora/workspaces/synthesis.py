"""Bounded independent fan-out and result synthesis for multi-agent reasoning."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from sora.contracts.base import StrictModel


class SynthesisConsensus(StrEnum):
    """Consensus classification across parallel agent execution candidates."""

    FULL_AGREEMENT = "full_agreement"
    PARTIAL_AGREEMENT = "partial_agreement"
    DISAGREEMENT = "disagreement"
    PARTIAL_FAILURE = "partial_failure"
    ALL_FAILED = "all_failed"


class SynthesisCandidate(StrictModel):
    """Normalized evidence from one parallel candidate run."""

    run_id: str
    provider: str
    outcome: str | None = None
    summary: str = ""
    conclusion: str = ""
    diff: str = ""
    files_changed: tuple[str, ...] = ()
    file_diffs: dict[str, str] = Field(default_factory=dict)
    verification_commands: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    error: str | None = None


class SynthesisResult(StrictModel):
    """Attributable comparison and synthesis across multiple candidate runs.

    This synthesis is strictly analytical. It highlights disagreements and failures
    honestly and never executes result instructions or invents consensus.
    """

    task_id: str
    consensus: SynthesisConsensus
    candidates: tuple[SynthesisCandidate, ...]
    agreed_files: tuple[str, ...] = ()
    conflicting_files: tuple[str, ...] = ()
    summary: str
    disagreements: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    created_at: datetime


class SynthesisEngine:
    """Deterministic, non-authoritative synthesizer for parallel candidate outcomes."""

    def synthesize(
        self,
        task_id: str,
        candidates: Sequence[SynthesisCandidate],
    ) -> SynthesisResult:
        if not candidates:
            raise ValueError("Synthesis requires at least one candidate.")

        candidate_tuple = tuple(candidates)
        failed_candidates: list[SynthesisCandidate] = []
        successful_candidates: list[SynthesisCandidate] = []
        failures: list[str] = []

        for candidate in candidate_tuple:
            if candidate.error is not None or candidate.outcome != "completed":
                failed_candidates.append(candidate)
                reason = candidate.error or f"Outcome was {candidate.outcome}"
                failures.append(f"Provider '{candidate.provider}' ({candidate.run_id}): {reason}")
            else:
                successful_candidates.append(candidate)

        if not successful_candidates:
            consensus = SynthesisConsensus.ALL_FAILED
            summary = (
                f"All {len(candidate_tuple)} candidate branches failed. "
                f"No agreement or synthesis possible."
            )
            return SynthesisResult(
                task_id=task_id,
                consensus=consensus,
                candidates=candidate_tuple,
                agreed_files=(),
                conflicting_files=(),
                summary=summary,
                disagreements=(),
                failures=tuple(failures),
                created_at=datetime.now(UTC),
            )

        # Track diffs per file across successful candidates
        file_diffs: dict[str, dict[str, str]] = defaultdict(dict)
        conflicting_files: list[str] = []
        agreed_files: list[str] = []
        disagreements: list[str] = []
        for candidate in successful_candidates:
            for file in candidate.files_changed:
                file_diff = candidate.file_diffs.get(file)
                if file_diff is None and len(candidate.files_changed) == 1:
                    file_diff = candidate.diff
                if file_diff is None:
                    disagreements.append(
                        f"File '{file}' lacks an isolated per-file diff for "
                        f"candidate '{candidate.run_id}'."
                    )
                    file_diff = f"<missing:{candidate.run_id}:{file}>"
                file_diffs[file][candidate.run_id] = file_diff

        # Find files changed by all successful candidates
        num_success = len(successful_candidates)
        for file, run_map in file_diffs.items():
            if len(run_map) == num_success and num_success > 1:
                # Check if all runs produced identical diff for this file
                unique_diffs = set(run_map.values())
                if len(unique_diffs) == 1:
                    agreed_files.append(file)
                else:
                    conflicting_files.append(file)
                    disagreements.append(
                        f"File '{file}' was modified differently across successful candidates."
                    )
            elif len(run_map) > 1:
                unique_diffs = set(run_map.values())
                if len(unique_diffs) > 1:
                    conflicting_files.append(file)
                    disagreements.append(
                        f"File '{file}' has conflicting proposals among subsets of candidates."
                    )
            elif num_success == 1:
                agreed_files.append(file)

        # Check conclusions for contradictions
        conclusions = {c.conclusion for c in successful_candidates if c.conclusion}
        if len(conclusions) > 1 and len(successful_candidates) > 1:
            disagreements.append(f"Candidates reached divergent conclusions: {list(conclusions)}")

        if failed_candidates:
            consensus = SynthesisConsensus.PARTIAL_FAILURE
        elif conflicting_files:
            consensus = SynthesisConsensus.DISAGREEMENT
        elif num_success > 1 and len(agreed_files) == len(file_diffs) and len(conclusions) <= 1:
            consensus = SynthesisConsensus.FULL_AGREEMENT
        elif num_success > 1:
            consensus = SynthesisConsensus.PARTIAL_AGREEMENT
        else:
            consensus = SynthesisConsensus.FULL_AGREEMENT

        summary_parts = [
            f"Evaluated {len(candidate_tuple)} candidate runs "
            f"({len(successful_candidates)} succeeded, {len(failed_candidates)} failed).",
            f"Consensus: {consensus.value}.",
        ]
        if agreed_files:
            summary_parts.append(f"Agreed files: {', '.join(sorted(agreed_files))}.")
        if conflicting_files:
            summary_parts.append(f"Conflicting files: {', '.join(sorted(conflicting_files))}.")
        if disagreements:
            summary_parts.append(f"Disagreements noted: {len(disagreements)}.")
        if failures:
            summary_parts.append(f"Failures recorded: {len(failures)}.")

        return SynthesisResult(
            task_id=task_id,
            consensus=consensus,
            candidates=candidate_tuple,
            agreed_files=tuple(sorted(agreed_files)),
            conflicting_files=tuple(sorted(conflicting_files)),
            summary=" ".join(summary_parts),
            disagreements=tuple(disagreements),
            failures=tuple(failures),
            created_at=datetime.now(UTC),
        )
