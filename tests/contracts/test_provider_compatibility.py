from __future__ import annotations

import pytest
from pydantic import ValidationError

from sora.contracts.codec import decode_contract, encode_contract
from sora.contracts.models import (
    NormalizedResult,
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderRequest,
)
from sora.contracts.provider_support import ProviderMethod, unsupported_method

from .helpers import example_text


class FakeProvider:
    def accept(self, payload: str) -> ProviderRequest:
        return decode_contract(ProviderRequest, payload)

    def emit(self, result: NormalizedResult) -> str:
        return encode_contract(result)


class FakeClient:
    def accept(self, payload: str) -> NormalizedResult:
        return decode_contract(NormalizedResult, payload)


def test_fake_provider_and_client_share_contract_without_native_types() -> None:
    provider = FakeProvider()
    client = FakeClient()
    request = provider.accept(example_text("valid", "provider-request.json"))
    result = NormalizedResult.model_validate_json(example_text("valid", "normalized-result.json"))

    received = client.accept(provider.emit(result))

    assert request.run_id == received.run_id
    assert received == result


def test_backend_specific_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="hermes_session_token"):
        NormalizedResult.model_validate_json(example_text("scenarios", "backend-field-leak.json"))


def test_unsupported_provider_method_returns_typed_error() -> None:
    capabilities = ProviderCapabilities.model_validate_json(
        example_text("valid", "provider-capabilities.json")
    )
    error = unsupported_method(capabilities, ProviderMethod.STEER)

    assert error is not None
    assert error.code is ProviderErrorCode.UNSUPPORTED
    assert unsupported_method(capabilities, ProviderMethod.CANCEL) is None


@pytest.mark.parametrize("fixture", ["uncertain-launch-result.json", "lost-session-result.json"])
def test_recovery_failures_remain_typed_and_inspectable(fixture: str) -> None:
    result = NormalizedResult.model_validate_json(example_text("scenarios", fixture))

    assert result.error is not None
    assert result.error.code in {
        ProviderErrorCode.UNCERTAIN_LAUNCH,
        ProviderErrorCode.LOST_SESSION,
    }
