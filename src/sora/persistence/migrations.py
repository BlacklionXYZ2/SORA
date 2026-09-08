"""Ordered SQLite schema migrations."""

# ruff: noqa: E501 -- keeping each migration statement atomic aids exact review/replay.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        1,
        (
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
            "CREATE TABLE state_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL)",
            "INSERT INTO state_meta(singleton, revision) VALUES (1, 0)",
            "CREATE TABLE owners (owner_id TEXT PRIMARY KEY, created_at TEXT NOT NULL)",
            "CREATE TABLE projects (project_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), created_at TEXT NOT NULL)",
            "CREATE TABLE conversations (conversation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_id TEXT REFERENCES projects(project_id), created_at TEXT NOT NULL)",
            "CREATE TABLE messages (message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id), owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_id TEXT REFERENCES projects(project_id), role TEXT NOT NULL, content TEXT NOT NULL, provenance TEXT NOT NULL, sensitivity TEXT NOT NULL, created_at TEXT NOT NULL)",
            "CREATE INDEX messages_conversation_idx ON messages(conversation_id, created_at)",
            "CREATE TABLE tasks (task_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_id TEXT REFERENCES projects(project_id), status TEXT NOT NULL, entity_version INTEGER NOT NULL, payload TEXT NOT NULL)",
            "CREATE INDEX tasks_owner_status_idx ON tasks(owner_id, status)",
            "CREATE TABLE agent_runs (run_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), status TEXT NOT NULL, payload TEXT NOT NULL)",
            "CREATE INDEX runs_task_idx ON agent_runs(task_id)",
            "CREATE TABLE agent_sessions (session_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), provider TEXT NOT NULL, native_session_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(provider, native_session_id))",
            "CREATE TABLE identity_revisions (identity_revision_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), version INTEGER NOT NULL, content_hash TEXT NOT NULL, source TEXT NOT NULL, activated_at TEXT NOT NULL, files_json TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)), UNIQUE(owner_id, version))",
            "CREATE UNIQUE INDEX one_active_identity_idx ON identity_revisions(owner_id) WHERE active=1",
            "CREATE TABLE facts (fact_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_id TEXT REFERENCES projects(project_id), content TEXT NOT NULL, epistemic_status TEXT NOT NULL, confidence REAL NOT NULL, provenance TEXT NOT NULL, evidence_json TEXT NOT NULL, entity_version INTEGER NOT NULL, valid_until TEXT, superseded_by TEXT REFERENCES facts(fact_id), deleted_at TEXT)",
            "CREATE INDEX facts_scope_idx ON facts(owner_id, project_id)",
            "CREATE TABLE memories (memory_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_id TEXT REFERENCES projects(project_id), content TEXT NOT NULL, scope TEXT NOT NULL, sensitivity TEXT NOT NULL, retention TEXT NOT NULL, provenance TEXT NOT NULL, evidence_json TEXT NOT NULL, entity_version INTEGER NOT NULL, valid_until TEXT, superseded_by TEXT REFERENCES memories(memory_id), deleted_at TEXT)",
            "CREATE INDEX memories_scope_idx ON memories(owner_id, project_id)",
            "CREATE TABLE normalized_results (result_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), run_id TEXT NOT NULL REFERENCES agent_runs(run_id), payload TEXT NOT NULL, accepted_at TEXT NOT NULL)",
            "CREATE TABLE patches (patch_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(run_id), idempotency_key TEXT NOT NULL, disposition TEXT NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL)",
            "CREATE UNIQUE INDEX patches_idempotency_idx ON patches(idempotency_key)",
            "CREATE TABLE events (event_id TEXT PRIMARY KEY, stream_id TEXT NOT NULL, sequence INTEGER NOT NULL, revision INTEGER, payload TEXT NOT NULL, UNIQUE(stream_id, sequence))",
            "CREATE TABLE outbox (event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE, available_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE artifacts (artifact_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), relative_path TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, created_at TEXT NOT NULL, UNIQUE(owner_id, relative_path))",
            "CREATE TABLE approvals (approval_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), status TEXT NOT NULL, payload TEXT NOT NULL)",
            "CREATE TABLE grants (grant_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), status TEXT NOT NULL, payload TEXT NOT NULL)",
        ),
    ),
    Migration(
        2,
        (
            "ALTER TABLE outbox ADD COLUMN delivered_at TEXT",
            "CREATE INDEX outbox_pending_idx ON outbox(delivered_at, available_at)",
        ),
    ),
    Migration(
        3,
        (
            "CREATE TABLE submissions (idempotency_key TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), message_id TEXT NOT NULL REFERENCES messages(message_id), created_at TEXT NOT NULL)",
            "CREATE TABLE runtime_leases (run_id TEXT PRIMARY KEY REFERENCES agent_runs(run_id) ON DELETE CASCADE, lease_owner TEXT NOT NULL, acquired_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, expires_at TEXT NOT NULL, deadline TEXT NOT NULL)",
            "CREATE INDEX runtime_leases_expiry_idx ON runtime_leases(expires_at)",
            "CREATE TABLE traces (trace_id TEXT PRIMARY KEY, correlation_id TEXT NOT NULL, message_id TEXT, task_id TEXT, run_id TEXT, phase TEXT NOT NULL, timestamp TEXT NOT NULL, duration_ms REAL, fields_json TEXT NOT NULL)",
            "CREATE INDEX traces_correlation_idx ON traces(correlation_id, timestamp)",
        ),
    ),
    Migration(
        4,
        (
            "ALTER TABLE submissions ADD COLUMN acknowledgement_id TEXT REFERENCES messages(message_id)",
        ),
    ),
)

CURRENT_SCHEMA_VERSION = MIGRATIONS[-1].version
