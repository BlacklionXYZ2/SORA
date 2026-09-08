"""One strict codec shared by Core, providers, and clients."""

from __future__ import annotations

from pydantic import BaseModel


def decode_contract[ContractT: BaseModel](
    model: type[ContractT], payload: str | bytes | bytearray
) -> ContractT:
    """Decode JSON using the selected public contract and its strict validation."""

    return model.model_validate_json(payload)


def encode_contract(value: BaseModel) -> str:
    """Encode canonical JSON suitable for another contract consumer."""

    return value.model_dump_json(exclude_none=True)
