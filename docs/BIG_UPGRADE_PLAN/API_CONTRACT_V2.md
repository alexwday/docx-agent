# API Contract V2

## Purpose

Define the backend API contract for the Postgres-backed session architecture and orchestrator workflow.

This contract is designed to support:

1. Login by 9-digit employee id.
2. Session list/load by user.
3. Session resume with full chat + artifacts.
4. One-turn agent processing with optional data source filters.
5. Traceability of orchestration internals.

## Implementation Status (2026-03-03)

1. Core V2 endpoints are implemented and wired in UI:
   - auth/login, user session listing, session hydrate, respond, operations, artifacts upload/list/preview, message events.
2. `POST /respond` currently executes baseline orchestration with persisted tool/model traces and a model-native iterative internal-research loop (with heuristic fallback).
3. Implemented orchestration tool paths:
   - `research_internal_data_sources`
   - `database_research`
   - `research_uploaded_documents`
   - `generate_report_document`
   - `export_report_document`
4. `database_research` now returns:
   - `research_markdown` artifact
   - `research_output_doc` artifact with format preset per source (`docx`/`pdf`/`xlsx`).
5. Report generation includes an LLM-driven adaptive gap-fill loop that reviews report requirements and current research context, then triggers additional `database_research` calls when needed.
6. Report structure flow supports recursive subsection expansion through conversational turns before instruction capture/generation.
7. Report plan card contract fields are implemented in `POST /respond`:
   - request passthrough: `report_plan_state`, `report_plan_action`
   - response payload: `assistant_message.content_json.report_plan_card`
   - events: `report_plan_card_created`, `report_plan_state_updated`, `report_plan_start_now_triggered`.
8. Remaining contract-adjacent backlog:
   - optional additional UX improvements for extreme-size `pdf`/`xlsx` previews beyond current large-file/balanced preview modes.

Transition routing note:

1. V2 routes are exposed under `/api/v2/...` and are the default active API surface when V2 workspace is configured.
2. Legacy V1 `/api/...` routes are compatibility-only and require explicit server opt-in (`--enable-legacy-v1-routes`).

## Envelope

All responses return:

1. `status`: `ok` or `error`
2. `contract_version`: `v2`

Error responses also include:

1. `error_code`
2. `message`

## Shared Shapes

### Session Summary

```json
{
  "session_id": "uuid",
  "user_id": "123456789",
  "title": "Q2 Supply Chain Research",
  "status": "active",
  "created_at": "2026-03-02T14:00:00Z",
  "updated_at": "2026-03-02T14:30:00Z",
  "last_activity_at": "2026-03-02T14:30:00Z",
  "metadata": {}
}
```

### Message

```json
{
  "message_id": "uuid",
  "session_id": "uuid",
  "sequence_no": 17,
  "role": "assistant",
  "content_text": "Here is what I found...",
  "content_json": {},
  "parent_message_id": "uuid",
  "processing_state": "completed",
  "processing_started_at": "2026-03-02T14:29:58Z",
  "processing_ended_at": "2026-03-02T14:30:00Z",
  "error": null,
  "created_at": "2026-03-02T14:30:00Z"
}
```

### Artifact

```json
{
  "artifact_id": "uuid",
  "session_id": "uuid",
  "artifact_group_id": "uuid",
  "artifact_type": "research_output_doc",
  "lifecycle_state": "final",
  "format": "pdf",
  "filename": "supplier-risk-summary.pdf",
  "storage_uri": "s3://bucket/path/file.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 248291,
  "checksum": "sha256:...",
  "source_artifact_id": null,
  "created_from_message_id": "uuid",
  "metadata": {},
  "created_at": "2026-03-02T14:31:00Z"
}
```

### Artifact Panes

```json
{
  "uploaded_documents": [],
  "research_outputs": [],
  "report_documents": []
}
```

## Auth + User Session Discovery

### `POST /api/v2/auth/login`

Validates 9-digit employee id and initializes UI identity context.

Request:

```json
{
  "employee_id": "123456789"
}
```

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "user": {
    "user_id": "123456789"
  }
}
```

### `GET /api/v2/users/{user_id}/sessions`

Returns all sessions for the logged-in user.

Query params:

1. `status` optional (`active`, `archived`)
2. `limit` optional
3. `cursor` optional

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "sessions": [],
  "next_cursor": null
}
```

## Session Lifecycle

### `POST /api/v2/sessions`

Create a session for a user.

Request:

```json
{
  "user_id": "123456789",
  "title": "New Research Session",
  "metadata": {}
}
```

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "session": {}
}
```

### `GET /api/v2/sessions/{session_id}/hydrate`

Loads complete session context for UI resume.

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "session": {},
  "messages": [],
  "artifact_panes": {
    "uploaded_documents": [],
    "research_outputs": [],
    "report_documents": []
  },
  "active_preview_artifact_id": null
}
```

## Artifact Endpoints

### `POST /api/v2/sessions/{session_id}/artifacts/upload`

Uploads a user document and triggers ingestion.

Request:

1. `multipart/form-data` with file bytes, or backend-supported upload reference payload.

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "artifact": {},
  "ingestion_state": "completed",
  "ingestion_summary": {
    "ingestion_state": "completed",
    "summary_units": 1,
    "chunk_units": 8
  }
}
```

`ingestion_state` values:

1. `queued` (async mode)
2. `completed` (sync mode)
3. `failed`
4. `skipped`

### `GET /api/v2/sessions/{session_id}/artifacts`

Returns artifacts; UI groups by `artifact_type`.

Query params:

1. `artifact_type` optional
2. `limit` optional
3. `cursor` optional

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "artifacts": [],
  "next_cursor": null
}
```

### `GET /api/v2/sessions/{session_id}/artifacts/{artifact_id}/preview`

Returns preview content/URL for selected artifact.

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "artifact_id": "uuid",
  "preview_format": "html",
  "preview_content": "<html>...</html>",
  "preview_url": null
}
```

## Data Source Catalog

### `GET /api/v2/data-sources/catalog`

Returns enabled data source catalog entries for UI and orchestration.

Query params:

1. `enabled` optional (`true` default)
2. `source_type` optional

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "sources": [
    {
      "source_id": "sales_db.orders",
      "name": "Orders",
      "source_type": "postgres_table",
      "schema_json": {}
    }
  ]
}
```

## Orchestrator Turn Processing

### `POST /api/v2/sessions/{session_id}/respond`

Creates a user turn (if `message` provided), executes orchestration, and persists assistant output + events.

Request:

```json
{
  "message": "Create a supplier risk report for Q2.",
  "data_source_filters": [
    "sales_db.orders",
    "risk_db.suppliers"
  ],
  "response_mode": "auto",
  "report_plan_state": null,
  "report_plan_action": null
}
```

Request rules:

1. `message` is optional, but at least one actionable input must be present (a `message`, a `report_plan_state` update, or a `report_plan_action`).
2. `data_source_filters` is optional.
3. Missing/empty `data_source_filters` means unfiltered mode across all enabled catalog sources.
4. If provided, only effective filtered sources are visible to the orchestrator.
5. `report_plan_state` is optional. When provided, carries the current report plan state from the frontend, including any manual user edits via card controls. See `REPORT_PLAN_CARD_V1.md` for the plan state schema.
6. `report_plan_action` is optional. Values:
   - `"start_now"` — user clicked Start Now; agent finalizes missing details and begins generation.
   - `null` / absent — normal conversational turn during scaffolding.

Current behavior note:

1. Baseline implementation enforces data-source filters, then runs model-native iterative source/query planning for internal research calls.
2. Internal research runs iteratively: model receives current results and decides `call_more` vs `finish`.
3. Each internal research call is normalized to `database_research(source_id, research_statement)` and scoped to effective sources only.
4. If iterative planner output is invalid/unusable, heuristic selection is used as fallback.
5. Report generation applies LLM-planned iterative gap-fill before final section synthesis.

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "user_message": {},
  "assistant_message": {},
  "operation": {
    "operation_id": "uuid",
    "state": "completed"
  },
  "filter_result": {
    "mode": "filtered",
    "requested_source_ids": [
      "sales_db.orders",
      "risk_db.suppliers"
    ],
    "effective_source_ids": [
      "sales_db.orders",
      "risk_db.suppliers"
    ],
    "ignored_source_ids": []
  },
  "selected_source_ids": [
    "risk_db.suppliers"
  ],
  "artifacts_created": [],
  "artifacts_updated": []
}
```

Operation identity rule:

1. `operation_id` equals the `assistant_message.message_id` created for this turn.
2. This avoids separate run tables while preserving operation polling/state semantics.

`operation.state` values:

1. `queued`
2. `in_progress`
3. `completed`
4. `failed`

### `GET /api/v2/sessions/{session_id}/operations/{operation_id}`

Returns operation status for long-running turns.

Resolution rule:

1. Lookup `session_messages.message_id = operation_id` where role is `assistant`.
2. Derive operation state from `session_messages.processing_state`.
3. Map `started_at` to `session_messages.processing_started_at`.
4. Map `ended_at` to `session_messages.processing_ended_at`.

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "operation": {
    "operation_id": "uuid",
    "state": "in_progress",
    "started_at": "2026-03-02T14:30:00Z",
    "ended_at": null,
    "error": null
  }
}
```

## Event Trace Endpoint

### `GET /api/v2/sessions/{session_id}/messages/{message_id}/events`

Returns ordered orchestration events for one assistant turn.

Response:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "events": [
    {
      "event_id": "uuid",
      "event_index": 1,
      "event_type": "orchestrator_system_prompt",
      "payload": {},
      "created_at": "2026-03-02T14:30:00Z"
    }
  ]
}
```

Common implemented event types include:

1. `orchestrator_system_prompt`
2. `conversation_context_injected`
3. `available_data_sources_injected`
4. `uploaded_documents_context_injected`
5. `prior_agent_interactions_injected`
6. `tool_definitions_injected`
7. `tool_call_request`
8. `tool_call_response`
9. `model_request`
10. `model_response`
11. `report_plan_card_created`
12. `report_plan_state_updated`
13. `report_plan_start_now_triggered`

## Report Workflow Semantics

Report creation is powered via `POST /respond` and uses an interactive **report plan card** — an HTML widget embedded in assistant messages that gives users a visual, editable view of the report structure.

See [`REPORT_PLAN_CARD_V1.md`](./REPORT_PLAN_CARD_V1.md) for full design specification.

### Plan Card in Responses

When the session is in report workflow mode, the assistant message `content_json` includes a `report_plan_card` object:

```json
{
  "content_json": {
    "report_plan_card": {
      "plan_id": "uuid",
      "title": "Q2 Supplier Risk Assessment",
      "summary": "Comprehensive report analyzing supplier risk",
      "status": "scaffolding",
      "sections": [
        {
          "section_id": "uuid",
          "title": "Executive Summary",
          "depth": 0,
          "instructions": "Provide a high-level overview",
          "instruction_source": "user",
          "status": "has_instructions",
          "subsections": []
        }
      ],
      "updated_by": "agent",
      "updated_at": "2026-03-03T10:00:00Z"
    }
  }
}
```

### Expected Workflow

1. Agent detects report intent, creates initial plan card with suggested sections. Status: `scaffolding`.
2. User interacts via chat messages and/or card controls (add section, add subsection, edit instructions, remove).
3. Manual edits from card controls are sent back in `report_plan_state` of the next `/respond` request.
4. When `report_plan_state` is present in the request, the orchestrator injects a context note: "The report plan was recently updated by the user. Review the updated plan before proceeding."
5. Each assistant response during scaffolding includes an updated plan card.
6. User clicks "Start Now" at any point (sends `report_plan_action: "start_now"`). Agent fills in defaults for missing instructions and begins generation.
7. Final content replaces instruction placeholders in report working doc.
8. Final report and exports are persisted as artifacts.

### Two Entry Paths

1. **Simple**: user says "create a report about X" and immediately clicks "Start Now". Agent suggests all sections, generates default instructions, and runs the full pipeline.
2. **Detailed**: user iterates on sections, subsections, and instructions through conversation and/or card controls before clicking "Start Now".

### Instruction Input

Instructions can be provided via:

1. Card controls (inline textarea per section).
2. Conversational text using structured formats:
   - `Primary Section -> instruction text`
   - `Primary Section: Subsection -> instruction text`
   - `Primary Section > Subsection > Nested -> instruction text`
   - `all -> global instruction text` (fallback for unspecified sections)

### Primary Events

1. `report_plan_card_created` — initial plan card generated.
2. `report_plan_state_updated` — plan state changed (user edit or agent update).
3. `report_plan_start_now_triggered` — user clicked Start Now.
4. `report_structure_proposed`
5. `report_structure_confirmed`
6. `report_section_instructions_captured`
7. `report_generation_started`
8. `report_generation_completed`
9. `artifact_updated`

`report_section_instructions_captured` payload includes:

1. `instruction_count`
2. `mode` (`defaults`, `structured`, `global`, `start_now_defaults`, or `start_now_existing`)
3. `provided_keys` (explicitly mapped section keys)
4. `defaulted_keys` (auto-filled keys)

## Error Codes (V2)

1. `INVALID_ARGUMENT`
2. `AUTH_REQUIRED`
3. `NOT_FOUND`
4. `PERMISSION_DENIED`
5. `CONFLICT`
6. `PROCESSING_FAILED`
7. `TOOL_EXECUTION_FAILED`
8. `PREVIEW_NOT_AVAILABLE`
9. `INTERNAL_ERROR`
