"""Ordered SQLite schema migrations."""

# ruff: noqa: E501 -- keeping each migration statement atomic aids exact review/replay.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
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
    Migration(
        5,
        (
            "CREATE TABLE desktop_action_attempts (attempt_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, target_id TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE INDEX desktop_action_attempts_status_idx ON desktop_action_attempts(status, updated_at)",
        ),
    ),
    Migration(
        6,
        (
            "CREATE TABLE voice_utterances (utterance_key TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), device_id TEXT NOT NULL, project_id TEXT REFERENCES projects(project_id), conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id), session_id TEXT NOT NULL, utterance_id TEXT NOT NULL, transcript_sha256 TEXT NOT NULL, user_message_id TEXT NOT NULL REFERENCES messages(message_id), assistant_message_id TEXT NOT NULL REFERENCES messages(message_id), created_at TEXT NOT NULL, UNIQUE(owner_id, device_id, session_id, utterance_id))",
            "CREATE INDEX voice_utterances_conversation_idx ON voice_utterances(conversation_id, created_at)",
        ),
    ),
    Migration(
        7,
        (
            "CREATE TABLE pairing_invitations (invitation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), code_hash TEXT NOT NULL UNIQUE, label TEXT NOT NULL, scopes_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, claimed_at TEXT, claimed_device_id TEXT)",
            "CREATE INDEX pairing_invitations_expiry_idx ON pairing_invitations(owner_id, expires_at)",
            "CREATE TABLE paired_devices (device_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), label TEXT NOT NULL, credential_hash TEXT NOT NULL, scopes_json TEXT NOT NULL, paired_at TEXT NOT NULL, last_seen_at TEXT, revoked_at TEXT)",
            "CREATE INDEX paired_devices_owner_idx ON paired_devices(owner_id, revoked_at)",
            "CREATE TABLE remote_sessions (session_id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES paired_devices(device_id), token_hash TEXT NOT NULL, scopes_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen_at TEXT, revoked_at TEXT)",
            "CREATE INDEX remote_sessions_device_idx ON remote_sessions(device_id, expires_at, revoked_at)",
            "CREATE TABLE remote_access_audit (audit_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), device_id TEXT, session_id TEXT, source_ip TEXT NOT NULL, method TEXT NOT NULL, path TEXT NOT NULL, action TEXT NOT NULL, outcome TEXT NOT NULL, created_at TEXT NOT NULL, details_json TEXT NOT NULL)",
            "CREATE INDEX remote_access_audit_owner_idx ON remote_access_audit(owner_id, created_at)",
        ),
    ),
    Migration(
        8,
        (
            "CREATE TABLE board_plan_requests (idempotency_key TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), intent TEXT NOT NULL, created_at TEXT NOT NULL)",
        ),
    ),
    Migration(
        9,
        (
            "CREATE TABLE board_cards (task_id TEXT PRIMARY KEY REFERENCES tasks(task_id), column_name TEXT, assigned_agent TEXT, archived_at TEXT, version INTEGER NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE board_card_events (event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id), action TEXT NOT NULL, actor TEXT NOT NULL, column_name TEXT, assigned_agent TEXT, occurred_at TEXT NOT NULL)",
            "CREATE INDEX board_card_events_task_idx ON board_card_events(task_id, occurred_at)",
        ),
    ),
)

MIGRATIONS += (
    Migration(
        10,
        (
            "CREATE TABLE path_leases (run_id TEXT PRIMARY KEY REFERENCES agent_runs(run_id), task_id TEXT NOT NULL REFERENCES tasks(task_id), canonical_root TEXT NOT NULL, display_root TEXT NOT NULL, job_name TEXT NOT NULL UNIQUE, status TEXT NOT NULL, acquired_at TEXT NOT NULL, owner_pid INTEGER NOT NULL)",
            "CREATE TABLE path_events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES agent_runs(run_id), path TEXT NOT NULL, operation TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL, occurred_at TEXT NOT NULL)",
            "CREATE INDEX path_events_run_idx ON path_events(run_id, occurred_at)",
        ),
    ),
)

MIGRATIONS += (
    Migration(
        11,
        (
            "CREATE TABLE memory_mutation_receipts (owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_scope TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner_id, project_scope, request_id))",
        ),
    ),
)

MIGRATIONS += (
    Migration(
        12,
        (
            "CREATE TABLE automation_definitions (automation_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_id TEXT REFERENCES projects(project_id), entity_version INTEGER NOT NULL CHECK(entity_version>=1), state TEXT NOT NULL CHECK(state IN ('active','paused','deleted')), payload TEXT NOT NULL, next_slot_json TEXT)",
            "CREATE INDEX automation_definitions_scope_idx ON automation_definitions(owner_id,project_id,state)",
            "CREATE TABLE automation_occurrences (occurrence_id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automation_definitions(automation_id), definition_version INTEGER NOT NULL CHECK(definition_version>=1), origin TEXT NOT NULL CHECK(origin IN ('scheduled','manual')), slot_key TEXT NOT NULL, status TEXT NOT NULL, submission_key TEXT NOT NULL UNIQUE, task_id TEXT REFERENCES tasks(task_id), run_id TEXT REFERENCES agent_runs(run_id), payload TEXT NOT NULL, UNIQUE(automation_id,definition_version,origin,slot_key))",
            "CREATE INDEX automation_occurrences_active_idx ON automation_occurrences(automation_id,status)",
            "CREATE TABLE automation_mutation_receipts (owner_id TEXT NOT NULL REFERENCES owners(owner_id), project_scope TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner_id,project_scope,request_id))",
        ),
    ),
)

CURRENT_SCHEMA_VERSION = MIGRATIONS[-1].version
