"""P13.3 contracts for bounded, non-authoritative vision evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, Identifier, StrictModel, require_aware
from .capture import DesktopCaptureFrame, DesktopCaptureProvenance
from .content import ReferenceCandidate
from .embodiment import ScreenRect
from .models import AttentionTarget


class VisionEvidenceKind(StrEnum):
    UI_ELEMENT = "ui_element"
    TEXT = "text"
    ICON = "icon"
    REGION = "region"
    INSTRUCTION = "instruction"


class VisionEvidenceDisposition(StrEnum):
    CANDIDATE = "candidate"
    LOW_CONFIDENCE = "low_confidence"
    CAPTURED_INSTRUCTION = "captured_instruction"


class FrameRect(StrictModel):
    """Pixel rectangle relative to the top-left of one captured frame."""

    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


class VisionDetection(ContractModel):
    """Untrusted detector output. It intentionally cannot request or authorize an action."""

    detection_id: Identifier
    kind: VisionEvidenceKind
    label: Annotated[str, Field(min_length=1, max_length=512)]
    frame_region: FrameRect
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class VisionEvidenceBatchRequest(ContractModel):
    capture_id: Identifier
    detector_id: Identifier
    detector_version: Annotated[str, Field(min_length=1, max_length=128)]
    inferred_at: datetime
    ttl_seconds: Annotated[float, Field(gt=0, le=30, allow_inf_nan=False)] = 10.0
    detections: Annotated[tuple[VisionDetection, ...], Field(min_length=1, max_length=64)]

    @field_validator("inferred_at")
    @classmethod
    def validate_inferred_at(cls, value: datetime) -> datetime:
        return require_aware(value, "inferred_at")

    @model_validator(mode="after")
    def validate_unique_detections(self) -> VisionEvidenceBatchRequest:
        ids = [detection.detection_id for detection in self.detections]
        if len(ids) != len(set(ids)):
            raise ValueError("vision detection IDs must be unique within a batch")
        return self

    @property
    def resource(self) -> str:
        return f"desktop.observe:vision:{self.capture_id}"


class VisionEvidenceProvenance(ContractModel):
    capture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_provenance: DesktopCaptureProvenance
    detector_id: Identifier
    detector_version: Annotated[str, Field(min_length=1, max_length=128)]
    normalizer_version: Literal["p13.3-v1"] = "p13.3-v1"


class VisionEvidence(ContractModel):
    """Short-lived observation with explicit non-authority and non-fact semantics."""

    evidence_id: Identifier
    capture_id: Identifier
    detection_id: Identifier
    kind: VisionEvidenceKind
    label: Annotated[str, Field(min_length=1, max_length=512)]
    captured_at: datetime
    inferred_at: datetime
    expires_at: datetime
    topology_revision: Annotated[int, Field(ge=1)]
    frame_region: FrameRect
    screen_region: ScreenRect
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    disposition: VisionEvidenceDisposition
    usable_for_context: bool
    provenance: VisionEvidenceProvenance
    action_authority: Literal[False] = False
    instruction_authority: Literal[False] = False
    canonical_fact: Literal[False] = False

    @field_validator("captured_at", "inferred_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        return require_aware(value, getattr(info, "field_name", "timestamp"))

    @model_validator(mode="after")
    def validate_semantics(self) -> VisionEvidence:
        if self.inferred_at < self.captured_at:
            raise ValueError("vision inference cannot predate its capture")
        if self.expires_at <= self.inferred_at:
            raise ValueError("vision evidence expiry must follow inference")
        if self.disposition is VisionEvidenceDisposition.CANDIDATE:
            if not self.usable_for_context:
                raise ValueError("candidate vision evidence must be usable for context")
        elif self.usable_for_context:
            raise ValueError("suppressed vision evidence cannot be usable for context")
        if self.kind is VisionEvidenceKind.INSTRUCTION and (
            self.disposition is not VisionEvidenceDisposition.CAPTURED_INSTRUCTION
        ):
            raise ValueError("captured instructions must remain explicitly suppressed")
        return self


class VisionEvidenceBatchResult(ContractModel):
    capture_id: Identifier
    evidence: Annotated[tuple[VisionEvidence, ...], Field(max_length=64)] = ()
    candidate_count: Annotated[int, Field(ge=0, le=64)] = 0
    suppressed_count: Annotated[int, Field(ge=0, le=64)] = 0

    @model_validator(mode="after")
    def validate_counts(self) -> VisionEvidenceBatchResult:
        if self.candidate_count + self.suppressed_count != len(self.evidence):
            raise ValueError("vision evidence counts do not match the normalized records")
        return self


class AttentionCropFallbackRequest(ContractModel):
    """Request an exact crop derived from one live circle target, never caller geometry."""

    request_id: Identifier
    attention_target_id: Identifier
    capture_id: Identifier
    fallback_reason: Literal["uia_insufficient"] = "uia_insufficient"
    ttl_seconds: Annotated[float, Field(gt=0, le=30, allow_inf_nan=False)] = 5.0


class AttentionCropFallbackResult(ContractModel):
    request_id: Identifier
    target: AttentionTarget
    reference: ReferenceCandidate
    frame: DesktopCaptureFrame

    @model_validator(mode="after")
    def validate_join(self) -> AttentionCropFallbackResult:
        if self.target.target_id != self.reference.attention_target_id:
            raise ValueError("attention crop target/reference identity mismatch")
        if self.target.crop_ref != self.frame.capture_id:
            raise ValueError("attention target does not identify its crop")
        if self.reference.crop_ref != self.frame.capture_id:
            raise ValueError("attention reference does not identify its crop")
        if self.target.source != "circle":
            raise ValueError("cropped fallback requires a circle target")
        rect = self.target.screen_rect
        if rect is None or rect != (
            self.frame.region.x,
            self.frame.region.y,
            self.frame.region.width,
            self.frame.region.height,
        ):
            raise ValueError("attention target and crop regions differ")
        if self.reference.screen_rect != self.frame.region:
            raise ValueError("attention reference and crop regions differ")
        if self.target.expires_at > self.frame.expires_at:
            raise ValueError("attention target cannot outlive its crop")
        return self
