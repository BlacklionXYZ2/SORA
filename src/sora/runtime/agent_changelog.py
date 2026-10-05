"""Verification and storage of agent-authored changelog entries.

The agent authors; Core checks. Core never composes an entry and never presents its own summary as
the agent's account, so there are exactly three honest outcomes:

* the agent wrote the file itself - Core confirms it exists inside the working directory, under the
  changelog directory, hashes it and records it;
* the agent returned entry text because its sandbox could not create files - Core stores that text
  **verbatim** under a provenance line that says where it came from;
* neither arrived - Core records that the entry is missing. Nothing is invented, and a run without
  an entry says so on the record rather than quietly looking complete.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from sora.contracts.base import StrictModel
from sora.contracts.changelog import CHANGELOG_DIRECTORY

MAX_ENTRY_BYTES = 262_144
_SLUG_ALLOWED = re.compile(r"[^a-z0-9]+")


def _slug(value: str, *, limit: int = 48) -> str:
    slug = _SLUG_ALLOWED.sub("-", value.strip().lower()).strip("-")
    return (slug or "entry")[:limit].strip("-") or "entry"


class VerifiedChangelog(StrictModel):
    """An entry the agent wrote itself, confirmed to exist where the agent said it does."""

    relative_path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    bytes: int = Field(ge=1)
    truncated: bool = False


def verify_agent_changelog(root: Path, reported_path: str) -> VerifiedChangelog | None:
    """Confirm the agent's claimed entry really exists inside its working directory.

    A reported path is a claim, not evidence: absolute paths, traversal out of the root, anything
    outside the changelog directory, empty files and non-markdown files are all refused.
    """
    raw = reported_path.strip().replace("\\", "/")
    if not raw or Path(raw).is_absolute():
        return None
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / raw).resolve()
    except OSError:
        return None
    if candidate == root_resolved or root_resolved not in candidate.parents:
        return None
    try:
        candidate.relative_to(root_resolved / CHANGELOG_DIRECTORY)
    except ValueError:
        return None
    if candidate.suffix.lower() != ".md" or not candidate.is_file():
        return None
    try:
        data = candidate.read_bytes()[:MAX_ENTRY_BYTES]
        size = candidate.stat().st_size
    except OSError:
        return None
    if not data.strip():
        return None
    return VerifiedChangelog(
        relative_path=candidate.relative_to(root_resolved).as_posix(),
        sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        truncated=size > MAX_ENTRY_BYTES,
    )


def store_agent_entry(
    root: Path, *, agent: str, task_id: str, entry: str, now: datetime
) -> Path:
    """Persist, verbatim, entry text the agent returned because it could not write files.

    Only the provenance comment is Core's; the entry itself is the agent's own words, untouched.
    """
    root.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S")
    target = root / f"{stamp}_{_slug(task_id)}_{_slug(agent).upper()}.md"
    body = (
        "<!-- agent-authored entry: returned by the agent in its result contract because its "
        "sandbox could not create files, and stored here verbatim by Core. -->\n\n"
        f"{entry.strip()}\n"
    )
    handle_fd, temporary = tempfile.mkstemp(dir=root, prefix=".changelog-", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target
