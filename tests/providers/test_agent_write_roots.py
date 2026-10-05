"""Direct agent write authority: granted project roots instead of worktree-only isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from sora.providers.codex import CodexAppServerProvider


def test_workspace_write_still_requires_a_worktree_without_a_grant(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workspace-write requires an owned workspace"):
        CodexAppServerProvider(cwd=str(tmp_path), sandbox="workspace-write")


def test_granted_root_allows_workspace_write_in_place(tmp_path: Path) -> None:
    granted = tmp_path / "project"
    (granted / "src").mkdir(parents=True)
    provider = CodexAppServerProvider(
        cwd=str(granted / "src"), sandbox="workspace-write", direct_roots=(str(granted),),
    )
    assert provider.direct_roots == (str(granted),)
    assert provider.sandbox == "workspace-write"


def test_ungranted_directory_is_refused_even_next_to_a_grant(tmp_path: Path) -> None:
    granted = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    granted.mkdir()
    elsewhere.mkdir()
    with pytest.raises(ValueError, match="workspace-write requires an owned workspace"):
        CodexAppServerProvider(
            cwd=str(elsewhere), sandbox="workspace-write", direct_roots=(str(granted),),
        )


def test_prefix_sibling_is_not_inside_the_grant(tmp_path: Path) -> None:
    granted = tmp_path / "project"
    sibling = tmp_path / "project-other"
    granted.mkdir()
    sibling.mkdir()
    with pytest.raises(ValueError, match="workspace-write requires an owned workspace"):
        CodexAppServerProvider(
            cwd=str(sibling), sandbox="workspace-write", direct_roots=(str(granted),),
        )


@pytest.mark.parametrize("grant", ["C:/", "C:\\", ".", "relative/path"])
def test_drive_roots_and_relative_paths_are_never_grants(tmp_path: Path, grant: str) -> None:
    with pytest.raises(ValueError, match="workspace-write requires an owned workspace"):
        CodexAppServerProvider(
            cwd=str(tmp_path), sandbox="workspace-write", direct_roots=(grant,),
        )


def test_danger_full_access_stays_refused_even_with_a_grant(tmp_path: Path) -> None:
    granted = tmp_path / "project"
    granted.mkdir()
    with pytest.raises(ValueError, match="danger-full-access"):
        CodexAppServerProvider(
            cwd=str(granted), sandbox="danger-full-access", direct_roots=(str(granted),),
        )


def test_for_direct_root_binds_the_granted_directory(tmp_path: Path) -> None:
    granted = tmp_path / "project"
    granted.mkdir()
    base = CodexAppServerProvider(cwd=str(tmp_path), model="gpt-5.6-luna")
    bound = base.for_direct_root(str(granted))
    assert Path(bound.cwd) == granted.resolve()
    assert bound.sandbox == "workspace-write"
    assert bound.direct_roots == (str(granted),)
    assert base.sandbox == "read-only"  # the unbound adapter is unchanged
