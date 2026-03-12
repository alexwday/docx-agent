# Postgres Schema V1 (Big Upgrade)

## Purpose

This schema supports a session-centric, input/output orchestration model:

1. Users authenticate with a 9-digit employee id.
2. The UI loads sessions by user id and resumes any selected session.
3. The model remains stateless between turns; continuity is reconstructed from persisted data.
4. Orchestrator actions (prompt assembly, tool usage, research, report generation) are persisted as events.

## Coverage Checklist

| Product need | Schema support |
|---|---|
| Load all sessions for logged-in employee id | `sessions.user_id` + user indexes |
| Resume session chat history | `session_messages` |
| Show uploaded/research/report document lists | `session_artifacts.artifact_type` |
| Open selected document in preview | `session_artifacts.storage_uri` |
| Persist orchestrator internals per assistant turn | `message_events` |
| Allow agent to research internal sources and uploaded files | `data_source_catalog` + `artifact_knowledge_units` |
| Persist report working document + final document | `session_artifacts.lifecycle_state` + lineage fields |
| Track report plan card state across turns | `session_messages.content_json.report_plan_card` + `message_events` plan card events |

## Table: `sessions`

Stores one row per user session.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `session_id` | `uuid` | `primary key` | Unique session id used by UI + backend. |
| `user_id` | `char(9)` | `not null`, `check (user_id ~ '^[0-9]{9}$')` | 9-digit employee id from UI login. |
| `title` | `text` | nullable | Optional user-facing session name. |
| `status` | `text` | `not null default 'active'`, `check (status in ('active','archived'))` | Session lifecycle state. |
| `metadata` | `jsonb` | `not null default '{}'::jsonb` | Extra session-level metadata. |
| `created_at` | `timestamptz` | `not null default now()` | Creation timestamp. |
| `updated_at` | `timestamptz` | `not null default now()` | Last write timestamp. |
| `last_activity_at` | `timestamptz` | `not null default now()` | Last user/assistant activity. |

Indexes:

1. `idx_sessions_user_updated` on `(user_id, updated_at desc)`
2. `idx_sessions_user_last_activity` on `(user_id, last_activity_at desc)`

## Table: `session_messages`

Stores conversation messages shown in UI and used as orchestrator inputs.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `message_id` | `uuid` | `primary key` | Unique message id. |
| `session_id` | `uuid` | `not null`, `references sessions(session_id) on delete cascade` | Parent session. |
| `sequence_no` | `bigint` | `not null` | Strict in-session order. |
| `role` | `text` | `not null`, `check (role in ('user','assistant','system'))` | Message role. |
| `content_text` | `text` | nullable | Rendered display text for UI. |
| `content_json` | `jsonb` | `not null default '{}'::jsonb` | Structured payload form for richer message content. |
| `parent_message_id` | `uuid` | nullable, `references session_messages(message_id)` | Assistant response linkage to originating message. |
| `processing_state` | `text` | `not null default 'completed'`, `check (processing_state in ('pending','completed','failed'))` | Turn processing state. |
| `processing_started_at` | `timestamptz` | nullable | Turn processing start time (assistant turns). |
| `processing_ended_at` | `timestamptz` | nullable | Turn processing completion/failure time. |
| `error` | `jsonb` | nullable | Structured error details when failed. |
| `created_at` | `timestamptz` | `not null default now()` | Creation timestamp. |

Constraints and indexes:

1. `unique (session_id, sequence_no)`
2. `idx_session_messages_session_created` on `(session_id, created_at)`
3. `idx_session_messages_parent` on `(parent_message_id)`

## Table: `message_events`

Stores all per-turn orchestrator internals (system prompt, tool definitions, tool calls, report workflow state).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `event_id` | `uuid` | `primary key` | Unique event id. |
| `session_id` | `uuid` | `not null`, `references sessions(session_id) on delete cascade` | Parent session. |
| `message_id` | `uuid` | `not null`, `references session_messages(message_id) on delete cascade` | Parent assistant message. |
| `event_index` | `int` | `not null` | Ordered within one message turn. |
| `event_type` | `text` | `not null` | Event classification. |
| `payload` | `jsonb` | `not null` | Full event data payload. |
| `created_at` | `timestamptz` | `not null default now()` | Event timestamp. |

Constraints and indexes:

1. `unique (message_id, event_index)`
2. `idx_message_events_session_created` on `(session_id, created_at)`
3. `idx_message_events_type` on `(event_type)`

Recommended `event_type` values:

1. `orchestrator_system_prompt`
2. `conversation_context_injected`
3. `available_data_sources_injected`
4. `uploaded_documents_context_injected`
5. `tool_definitions_injected`
6. `ui_data_source_filter_applied`
7. `agent_data_source_selected`
8. `model_request`
9. `model_response`
10. `tool_call_request`
11. `tool_call_response`
12. `report_structure_proposed`
13. `report_structure_confirmed`
14. `report_section_instructions_captured`
15. `report_generation_started`
16. `report_generation_completed`
17. `artifact_created`
18. `artifact_updated`
19. `error`
20. `report_plan_card_created`
21. `report_plan_state_updated`
22. `report_plan_start_now_triggered`

## Table: `session_artifacts`

Stores uploaded inputs and generated outputs, including research and report documents.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `artifact_id` | `uuid` | `primary key` | Unique artifact id. |
| `session_id` | `uuid` | `not null`, `references sessions(session_id) on delete cascade` | Parent session. |
| `artifact_group_id` | `uuid` | nullable | Groups related outputs from one research/report generation pass. |
| `artifact_type` | `text` | `not null` | `upload`, `research_markdown`, `research_output_doc`, `report_working_doc`, `report_final_doc`, `export_file`. |
| `lifecycle_state` | `text` | `not null default 'final'`, `check (lifecycle_state in ('draft','in_progress','final','superseded'))` | Track working vs final assets. |
| `format` | `text` | `not null` | `docx`, `pdf`, `xlsx`, `json`, `md`, `txt`, etc. |
| `filename` | `text` | `not null` | Display file name. |
| `storage_uri` | `text` | `not null` | Path/object key for real file bytes. |
| `mime_type` | `text` | nullable | MIME type if known. |
| `size_bytes` | `bigint` | nullable | Size for UI and validation. |
| `checksum` | `text` | nullable | Optional integrity hash. |
| `created_from_message_id` | `uuid` | nullable, `references session_messages(message_id) on delete set null` | Producing message turn. |
| `source_artifact_id` | `uuid` | nullable, `references session_artifacts(artifact_id) on delete set null` | Lineage/version parent. |
| `metadata` | `jsonb` | `not null default '{}'::jsonb` | Structured metadata (preview hints, topic, section mapping). |
| `created_at` | `timestamptz` | `not null default now()` | Creation timestamp. |

Indexes:

1. `idx_session_artifacts_session_created` on `(session_id, created_at desc)`
2. `idx_session_artifacts_type` on `(artifact_type)`
3. `idx_session_artifacts_source` on `(source_artifact_id)`
4. `idx_session_artifacts_group` on `(artifact_group_id)`

UI document panes map directly from `artifact_type`:

1. Uploaded documents pane: `artifact_type = 'upload'`
2. Research outputs pane: `artifact_type in ('research_markdown','research_output_doc')`
3. Report documents pane: `artifact_type in ('report_working_doc','report_final_doc','export_file')`

## Table: `artifact_knowledge_units`

Stores parsed/summarized content derived from uploaded or generated documents for retrieval and prompt context injection.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `knowledge_id` | `uuid` | `primary key` | Unique derived-content id. |
| `session_id` | `uuid` | `not null`, `references sessions(session_id) on delete cascade` | Parent session for fast lookup. |
| `artifact_id` | `uuid` | `not null`, `references session_artifacts(artifact_id) on delete cascade` | Source document/artifact. |
| `unit_type` | `text` | `not null`, `check (unit_type in ('summary','chunk','table_extract'))` | Derived content class. |
| `sequence_no` | `int` | `not null default 0` | Order within the source artifact. |
| `content` | `text` | `not null` | Text body for retrieval/indexing. |
| `metadata` | `jsonb` | `not null default '{}'::jsonb` | Heading/page/table info, score hints, etc. |
| `created_at` | `timestamptz` | `not null default now()` | Creation timestamp. |

Constraints and indexes:

1. `unique (artifact_id, unit_type, sequence_no)`
2. `idx_artifact_knowledge_session` on `(session_id, created_at)`
3. `idx_artifact_knowledge_artifact` on `(artifact_id, sequence_no)`

## Table: `data_source_catalog`

Global catalog of available built-in data sources for agent research.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `source_id` | `text` | `primary key` | Stable identifier used by UI filters and agent selection. |
| `name` | `text` | `not null` | Human-readable source name. |
| `source_type` | `text` | `not null` | Example: `postgres_table`, `warehouse_view`, `search_index`. |
| `location` | `jsonb` | `not null default '{}'::jsonb` | Connection/schema/table/index location data. |
| `schema_json` | `jsonb` | `not null default '{}'::jsonb` | Fields and schema metadata for prompt context. |
| `enabled` | `boolean` | `not null default true` | Source availability flag. |
| `updated_at` | `timestamptz` | `not null default now()` | Last catalog update time. |

Indexes:

1. `idx_data_source_catalog_enabled` on `(enabled)`
2. `idx_data_source_catalog_type_enabled` on `(source_type, enabled)`

## Notes

1. This design intentionally avoids dedicated `orchestrator_runs`, `run_steps`, `tool_calls`, and `retrieval_events` tables in v1.
2. Those internals are persisted in `message_events.payload` to avoid duplication while preserving full traceability.
3. If analytics/reporting needs grow later, projection tables can be added without changing core write paths.
