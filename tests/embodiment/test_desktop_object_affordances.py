"""P12.6 generic desktop-object affordance and privacy acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.contracts.desktop_objects import (
    DesktopObjectAffordance,
    DesktopObjectAffordanceRequest,
)
from sora.contracts.embodiment import EmbodimentSemanticAction, EmbodimentVerb, ScreenRect
from sora.contracts.models import (
    CapabilityOperation,
    CapabilityScope,
    DesktopObjectRecord,
    DesktopObjectVisibility,
    GrantStatus,
)
from sora.desktop_objects import (
    DesktopObjectAffordanceError,
    DesktopObjectDefinition,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def definition(
    object_id: str,
    *,
    visibility: DesktopObjectVisibility = DesktopObjectVisibility.LOCAL_ONLY,
    hidden: bool = False,
    content: str = "fixture contents",
) -> DesktopObjectDefinition:
    return DesktopObjectDefinition(
        record=DesktopObjectRecord(
            object_id=object_id,
            object_type="fixture_card",
            owner_id="owner-local",
            anchor="fixture_anchor",
            visibility=visibility,
            affordances=("look", "point", "touch"),
            canonical_ref="task:fixture",
            version=7,
        ),
        label="Fixture card",
        rect=ScreenRect(x=200, y=180, width=240, height=160),
        topology_revision=1,
        content={"summary": content, "state": "unchanged"},
        hidden=hidden,
    )


async def runtime(tmp_path: Path) -> SoraRuntime:
    instance = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            owner_id="owner-local",
        ),
        provider=DeterministicProvider(),
    )
    await instance.start()
    return instance


@pytest.mark.asyncio
async def test_projection_hides_private_hidden_contents_and_affordances(tmp_path: Path) -> None:
    instance = await runtime(tmp_path)
    try:
        instance.register_desktop_object(
            definition(
                "object-private",
                visibility=DesktopObjectVisibility.PRIVATE,
                content="P12_PRIVATE_SENTINEL",
            )
        )
        instance.register_desktop_object(
            definition(
                "object-hidden",
                visibility=DesktopObjectVisibility.PUBLIC,
                hidden=True,
                content="P12_HIDDEN_SENTINEL",
            )
        )
        instance.register_desktop_object(
            definition(
                "object-public",
                visibility=DesktopObjectVisibility.PUBLIC,
                content="public fixture",
            )
        )

        owner_projection = instance.project_desktop_objects(
            scope=CapabilityScope.LOCAL_OWNER,
            actor_id="owner-local",
        )
        owner_ids = {item.object_id for item in owner_projection}
        assert owner_ids == {"object-private", "object-public"}
        assert next(
            item for item in owner_projection if item.object_id == "object-private"
        ).affordances == (
            DesktopObjectAffordance.LOOK,
            DesktopObjectAffordance.POINT,
            DesktopObjectAffordance.TOUCH,
        )

        public_projection = instance.project_desktop_objects(
            scope=CapabilityScope.NETWORK_PUBLIC,
            actor_id="visitor",
        )
        encoded = json.dumps(
            [item.model_dump(mode="json") for item in public_projection], sort_keys=True
        )
        assert [item.object_id for item in public_projection] == ["object-public"]
        assert public_projection[0].affordances == ()
        assert "P12_PRIVATE_SENTINEL" not in encoded
        assert "P12_HIDDEN_SENTINEL" not in encoded
        assert "object-private" not in encoded
        assert "object-hidden" not in encoded

        for object_id in ("object-private", "object-hidden", "object-missing"):
            with pytest.raises(DesktopObjectAffordanceError) as denied:
                instance.desktop_object_affordances.resolve(
                    DesktopObjectAffordanceRequest(
                        request_id=f"request-{object_id}",
                        object_id=object_id,
                        affordance=DesktopObjectAffordance.TOUCH,
                        expected_version=7,
                    ),
                    scope=CapabilityScope.NETWORK_PUBLIC,
                    actor_id="visitor",
                )
            assert denied.value.code == "not_available"
            assert str(denied.value) == "desktop object is not available"
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_generic_bridge_maps_look_point_touch_under_exact_policy(tmp_path: Path) -> None:
    instance = await runtime(tmp_path)
    try:
        instance.register_desktop_object(definition("object-fixture"))
        queue = instance.register_embodiment_queue()
        cases = (
            (
                DesktopObjectAffordance.LOOK,
                CapabilityOperation.DESKTOP_PRESENT,
                EmbodimentVerb.LOOK_AT,
            ),
            (
                DesktopObjectAffordance.POINT,
                CapabilityOperation.DESKTOP_PRESENT,
                EmbodimentVerb.SHOW_MARKER,
            ),
            (
                DesktopObjectAffordance.TOUCH,
                CapabilityOperation.DESKTOP_INTERACT,
                EmbodimentVerb.INTERACTION_START,
            ),
        )
        for index, (affordance, operation, expected_verb) in enumerate(cases):
            grant_id = f"grant-object-{affordance.value}"
            await persist_operation_grant(
                instance,
                f"desktop.object:object-fixture:{affordance.value}",
                grant_id=grant_id,
                operation=operation,
            )
            request = DesktopObjectAffordanceRequest(
                request_id=f"object-request-{index}",
                object_id="object-fixture",
                affordance=affordance,
                expected_version=7,
            )
            command = await instance.present_desktop_object_affordance(
                request,
                grant_id=grant_id,
                device_id="device-local",
            )
            assert queue.get_nowait() == command
            assert command.verb is expected_verb
            assert command.target_id == "object-fixture"
            assert command.target_point is not None
            assert (command.target_point.x, command.target_point.y) == (320, 260)
            assert await instance.validate_embodiment_delivery(command)
            if affordance is DesktopObjectAffordance.POINT:
                assert command.target_rect == ScreenRect(x=200, y=180, width=240, height=160)
            if affordance is DesktopObjectAffordance.TOUCH:
                assert command.semantic_action is EmbodimentSemanticAction.TOUCH
                assert command.semantic_action_id == request.request_id

        await persist_operation_grant(
            instance,
            "desktop.object:object-fixture:look",
            grant_id="grant-wrong-operation",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        with pytest.raises(OperationAuthorizationError):
            await instance.present_desktop_object_affordance(
                DesktopObjectAffordanceRequest(
                    request_id="request-wrong-policy",
                    object_id="object-fixture",
                    affordance=DesktopObjectAffordance.LOOK,
                    expected_version=7,
                ),
                grant_id="grant-wrong-operation",
                device_id="device-local",
            )
        assert queue.empty()
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_revocation_and_presentation_failure_leave_canonical_object_unchanged(
    tmp_path: Path,
) -> None:
    instance = await runtime(tmp_path)
    try:
        original = definition("object-stable", content="canonical payload")
        instance.register_desktop_object(original)
        queue = instance.register_embodiment_queue()
        authorization = await persist_operation_grant(
            instance,
            "desktop.object:object-stable:touch",
            grant_id="grant-object-stable-touch",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        request = DesktopObjectAffordanceRequest(
            request_id="request-object-stable-touch",
            object_id="object-stable",
            affordance=DesktopObjectAffordance.TOUCH,
            expected_version=7,
        )
        command = await instance.present_desktop_object_affordance(
            request,
            grant_id="grant-object-stable-touch",
            device_id="device-local",
        )
        assert queue.get_nowait() == command
        await instance.repository.save_grant(
            authorization.grant.model_copy(update={"status": GrantStatus.REVOKED})
        )
        assert not await instance.validate_embodiment_delivery(command)
        assert instance.desktop_object_affordances.snapshot("object-stable") == original

        instance.unregister_embodiment_queue(queue)
        await persist_operation_grant(
            instance,
            "desktop.object:object-stable:point",
            grant_id="grant-object-stable-point",
            operation=CapabilityOperation.DESKTOP_PRESENT,
        )
        with pytest.raises(DesktopObjectAffordanceError) as unavailable:
            await instance.present_desktop_object_affordance(
                request.model_copy(
                    update={
                        "request_id": "request-object-stable-point",
                        "affordance": DesktopObjectAffordance.POINT,
                    }
                ),
                grant_id="grant-object-stable-point",
                device_id="device-local",
            )
        assert unavailable.value.code == "presentation_unavailable"
        assert instance.desktop_object_affordances.snapshot("object-stable") == original
        assert original.record.version == 7
        assert original.content == {"summary": "canonical payload", "state": "unchanged"}
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_authenticated_api_projects_and_queues_generic_affordance(tmp_path: Path) -> None:
    instance = await runtime(tmp_path)
    instance.register_desktop_object(definition("object-api-fixture"))
    queue = instance.register_embodiment_queue()
    await persist_operation_grant(
        instance,
        "desktop.object:object-api-fixture:point",
        grant_id="grant-object-api-point",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    server = SoraApiServer(
        instance,
        ApiServerConfig(host="127.0.0.1", port=0, auth_token="p12-api-token-123456"),
    )
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token="p12-api-token-123456",
    )
    try:
        projection = await client.get_objects_projection()
        assert [item["object_id"] for item in projection["objects"]] == [
            "object-api-fixture"
        ]
        response = await client.present_desktop_object_affordance(
            "object-api-fixture",
            DesktopObjectAffordanceRequest(
                request_id="request-object-api-point",
                object_id="object-api-fixture",
                affordance=DesktopObjectAffordance.POINT,
                expected_version=7,
            ).model_dump(mode="json"),
            grant_id="grant-object-api-point",
        )
        assert response["status"] == "queued"
        assert response["command"]["verb"] == "show_marker"
        assert queue.get_nowait().command_id == response["command"]["command_id"]
    finally:
        await server.close()
        await instance.close()
