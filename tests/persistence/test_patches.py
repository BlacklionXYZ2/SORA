from __future__ import annotations

from pathlib import Path

import pytest

from sora.contracts.models import (
    NormalizedResult,
    ProposedFact,
    ProposeFactOperation,
    UpdateTaskMetadataOperation,
)
from sora.contracts.patches import PatchDisposition
from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository
from tests.contracts.helpers import example_text

from .helpers import sample_patch, sample_run, sample_task


async def ready_repository(tmp_path: Path) -> SoraRepository:
    database = SQLiteDatabase(tmp_path / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    await repository.register_project("project-sora", "owner-local")
    await repository.create_task(sample_task())
    await repository.create_run(sample_run())
    return repository


@pytest.mark.asyncio
async def test_patch_replay_is_idempotent_and_stale_independent_append_succeeds(
    tmp_path: Path,
) -> None:
    repository = await ready_repository(tmp_path)
    sample = sample_patch()
    patch = sample.model_copy(
        update={
            "base_revision": 0,
            "preconditions": (sample.preconditions[0].model_copy(update={"expected_version": 1}),),
        }
    )

    first = await repository.apply_patch(patch, "owner-local")
    replay = await repository.apply_patch(patch, "owner-local")

    independent = patch.model_copy(
        update={
            "patch_id": "patch-002",
            "idempotency_key": "patch-once-002",
            "base_revision": 0,
            "preconditions": (),
            "operations": (
                ProposeFactOperation(
                    operation="propose_fact",
                    operation_id="operation-002",
                    fact=ProposedFact(
                        content="An independent append survives intervening conversation.",
                        epistemic_status="observation",
                        confidence=1,
                    ),
                ),
            ),
        }
    )
    appended = await repository.apply_patch(independent, "owner-local")

    assert first.disposition is PatchDisposition.APPLICABLE
    assert replay.disposition is PatchDisposition.DUPLICATE
    assert appended.disposition is PatchDisposition.APPLICABLE
    assert (await repository.counts())["facts"] == 2
    assert (await repository.counts())["events"] == 6
    project_ids = await repository.database.read(
        lambda db: {row[0] for row in db.execute("SELECT project_id FROM facts")}
    )
    assert project_ids == {"project-sora"}


@pytest.mark.asyncio
async def test_patch_cannot_cross_owner_or_project_scope(tmp_path: Path) -> None:
    repository = await ready_repository(tmp_path)
    patch = sample_patch().model_copy(
        update={
            "preconditions": (),
            "scope": "owner-local/project-private",
        }
    )

    with pytest.raises(PermissionError, match="scope"):
        await repository.apply_patch(patch, "owner-local")
    with pytest.raises(PermissionError, match="owner"):
        await repository.apply_patch(
            patch.model_copy(update={"scope": "owner-other/project-sora"}), "owner-other"
        )


@pytest.mark.asyncio
async def test_entity_version_conflict_is_recorded_without_applying_operations(
    tmp_path: Path,
) -> None:
    repository = await ready_repository(tmp_path)
    patch = sample_patch()
    result_artifact = NormalizedResult.model_validate_json(
        example_text("valid", "normalized-result.json")
    )

    await repository.record_result(result_artifact, "owner-local")

    result = await repository.apply_patch(patch, "owner-local")

    assert result.disposition is PatchDisposition.CONFLICT
    assert result.conflicts[0].actual_version == 1
    assert (await repository.counts())["facts"] == 0
    assert (await repository.counts())["normalized_results"] == 1
    assert (await repository.counts())["events"] == 6


@pytest.mark.asyncio
async def test_failed_transaction_leaves_no_partial_fact_or_phantom_event(tmp_path: Path) -> None:
    repository = await ready_repository(tmp_path)
    before = await repository.counts()
    before_revision = await repository.revision()
    valid = sample_patch()
    broken = valid.model_copy(
        update={
            "patch_id": "patch-broken",
            "idempotency_key": "patch-broken-once",
            "preconditions": (),
            "operations": (
                valid.operations[0],
                UpdateTaskMetadataOperation(
                    operation="update_task_metadata",
                    operation_id="operation-missing-task",
                    task_id="task-missing",
                    summary="This must roll back.",
                ),
            ),
        }
    )

    with pytest.raises(LookupError, match="task-missing"):
        await repository.apply_patch(broken, "owner-local")

    assert await repository.counts() == before
    assert await repository.revision() == before_revision
