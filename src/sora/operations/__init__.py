"""Release packaging, state migration, and reversible Windows operations."""

from .install import install_bundle, rollback_install, uninstall_install, update_bundle
from .release import build_release_manifest, verify_release_manifest
from .state import backup_state, initialize_state, restore_state, verify_state

__all__ = [
    "backup_state",
    "build_release_manifest",
    "initialize_state",
    "install_bundle",
    "restore_state",
    "rollback_install",
    "uninstall_install",
    "update_bundle",
    "verify_release_manifest",
    "verify_state",
]
