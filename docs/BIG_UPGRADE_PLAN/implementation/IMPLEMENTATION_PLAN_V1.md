# Implementation Plan V1

## Goal

Implement the Postgres-backed session/orchestration architecture while preserving existing functionality during migration from JSON session storage.

## Guardrails

1. Keep API contract backward-compatible where feasible while introducing V2 routes.
2. No hidden in-memory conversational memory for model continuity.
3. Persist full per-turn orchestration trace in `message_events`.
4. Use `assistant_message_id` as `operation_id` to avoid introducing separate run tables.

## Current Code Touchpoints

1. `src/word_ui/workspace.py`: in-process session store + orchestration bridge.
2. `src/word_ui/models.py`: in-memory dataclasses for session state.
3. `src/word_ui/web_server.py`: HTTP routing and session/chat endpoints.
4. `src/word_agent/orchestrator.py`: system prompt construction + tool/workflow calls.

## Current Snapshot (2026-03-03)

1. Overall implementation status: Phases 1-8a are implemented at baseline functional level; Phase 8 cutover is in compatibility-window mode (legacy V1 routes are optional and opt-in).
2. Latest local test status: `100 passed, 5 skipped` (`pytest -q`).
3. Implemented core journey:
   - employee login (`9-digit user id`) -> session list -> hydrate -> chat/respond
   - artifact panes (uploads, research outputs, report documents) + artifact preview endpoint
   - per-turn orchestration trace with persisted tool/model events
   - internal database research + uploaded-doc research with persisted `research_markdown` + `research_output_doc`
   - report scaffolding -> instruction capture -> generation tool call -> export tool call
   - interactive report plan card flow: plan card render -> manual plan edits -> `start_now` generation trigger
4. Current known functional gaps vs target end-state:
   - no blocking gaps for the current Phase 8 + 8a target scope
   - remaining work is focused on production-grade integrations (retrievers, optional async execution, storage backend hardening) and final V1 runtime retirement.

## Phase 1: Persistence Foundation

Deliverables:

1. Add Postgres dependencies (`psycopg[binary]` or SQLAlchemy + psycopg).
2. Add migration execution path for `docs/BIG_UPGRADE_PLAN/sql/0001_schema_v1.sql`.
3. Introduce repository layer under new package `src/word_store/`.

Suggested modules:

1. `src/word_store/db.py` (connection pool/session helpers)
2. `src/word_store/sessions_repo.py`
3. `src/word_store/messages_repo.py`
4. `src/word_store/events_repo.py`
5. `src/word_store/artifacts_repo.py`
6. `src/word_store/data_sources_repo.py`

Success criteria:

1. Can create/load sessions/messages/artifacts from Postgres.
2. JSON session store no longer required for V2 flows.

Status update:

1. Implemented `word_store` repository package and Postgres DSN/config helper layer.
2. Added migration runner path and SQL migration script integration (`word-store-migrate` + `0001_schema_v1.sql`).
3. Implemented repositories for sessions/messages/events/artifacts/knowledge/data-source catalog.
4. V2 flow is Postgres-backed in `WordUIWorkspaceV2`; V1 JSON workspace remains present for coexistence during migration.

## Phase 2: API V2 Endpoints

Deliverables:

1. Add/route endpoints from `API_CONTRACT_V2.md`.
2. Preserve existing V1 endpoints for transition.

Primary new routes:

1. `POST /api/v2/auth/login`
2. `GET /api/v2/users/{user_id}/sessions`
3. `GET /api/v2/sessions/{session_id}/hydrate`
4. `POST /api/v2/sessions/{session_id}/respond`
5. `GET /api/v2/sessions/{session_id}/operations/{operation_id}`
6. `POST /api/v2/sessions/{session_id}/artifacts/upload`
7. `GET /api/v2/sessions/{session_id}/artifacts`
8. `GET /api/v2/sessions/{session_id}/artifacts/{artifact_id}/preview`
9. `GET /api/v2/sessions/{session_id}/messages/{message_id}/events`

Implementation note:

1. `operation_id` is `assistant_message_id`.
2. `operation.state` maps to `session_messages.processing_state`.
3. `operation.started_at/ended_at` map to `processing_started_at/processing_ended_at`.

Success criteria:

1. UI can login, load sessions, hydrate selected session, and send/respond in one flow.

Status update:

1. Implemented initial `/api/v2/*` routing in `src/word_ui/web_server.py`.
2. Added Postgres-backed `WordUIWorkspaceV2` service in `src/word_ui/workspace_v2.py`.
3. Added route-level tests for V2 dispatch + HTTP coverage with fake V2 workspace.
4. Migrated `src/word_ui/static/index.html` to V2 flow:
   - employee login (`/api/v2/auth/login`)
   - user session listing/creation (`/api/v2/users/{user_id}/sessions`, `/api/v2/sessions`)
   - session hydration (`/api/v2/sessions/{session_id}/hydrate`)
   - turn processing (`/api/v2/sessions/{session_id}/respond`)
   - optional data-source filtering UI passed via `data_source_filters`
   - artifact upload/list/preview behavior aligned with V2 artifact panes.

## Phase 3: Orchestrator Context Assembly

Deliverables:

1. Add context builder that assembles:
   - conversation history
   - effective data source catalog
   - uploaded-document knowledge units
   - relevant prior message events
2. Replace ad hoc `system_context` concatenation with explicit prompt sections.
3. Persist prompt assembly and decisions to `message_events`.

Required events per turn:

1. `orchestrator_system_prompt`
2. `conversation_context_injected`
3. `available_data_sources_injected`
4. `uploaded_documents_context_injected`
5. `tool_definitions_injected`
6. `model_request`
7. `model_response`

Success criteria:

1. Every assistant turn can be replayed from DB records.

Status update:

1. Added deterministic tool execution hooks in `WordUIWorkspaceV2.respond` for:
   - `research_internal_data_sources`
   - `research_uploaded_documents`
2. Each call now emits `tool_call_request` and `tool_call_response` events with structured arguments/results.
3. Tool outputs are injected into orchestrator system context sections for the model turn.
4. Internal research tool now dispatches by `source_type` with extractor payloads:
   - `postgres_table` / `warehouse_view`: `postgres_relation_probe` (live probe when DB access is available, metadata fallback otherwise)
   - `search_index`: `search_index_probe` metadata execution
   - unknown types: generic metadata probe
5. Added unified `database_research` tool contract for per-source calls:
   - request args: `source_id`, `source_type`, `research_statement`
   - routes to source-specific retriever handler
   - always persists tool research outputs as `research_markdown` + `research_output_doc` artifacts
   - returns artifact references in tool response payload.
6. Current retriever handlers are baseline/mock-oriented (metadata and optional lightweight DB probing) to validate the contract before integrating production retrievers.
7. Internal-source research now invokes `database_research` once per selected source and aggregates those per-source results.
8. Added a dedicated retriever plugin layer (`src/word_ui/retrievers.py`) with:
   - retriever registry resolution by `source_id`, `location.retriever_id`, then `source_type` fallback
   - pluggable retriever interface + function adapter
   - default mock retrievers and fallback metadata retrievers.
9. Orchestrator prompt assembly now injects prior agent interaction context:
   - pulls recent persisted event summaries from previous assistant turns
   - emits `prior_agent_interactions_injected` event per turn
   - includes prior interaction summaries in explicit `PREVIOUS_AGENT_INTERACTIONS` system prompt section.
10. Internal-source research now runs a model-native iterative decision loop:
   - each iteration asks the model to return either `call_more` with source/query calls or `finish`
   - planned `source_id` + `research_statement` pairs are executed via `database_research`
   - execution state (results + executed signatures) is injected each iteration to guide next calls.
11. Heuristic fallback remains active only for invalid/unusable planner output so the turn still executes deterministic research when needed.
12. Final selection metadata is persisted (`selection_mode`, planned/executed call counts).

## Phase 4: Data Source Filter Enforcement

Deliverables:

1. Support `data_source_filters` in `/respond`.
2. Resolve effective source scope from `data_source_catalog`.
3. Enforce tool-call scope so agent cannot query outside effective set.
4. Persist filter and selected-source events.

Required events:

1. `ui_data_source_filter_applied`
2. `agent_data_source_selected`

Success criteria:

1. Filtered requests only expose allowed source ids in prompt and tool execution.

Status update:

1. Implemented `data_source_filters` handling in `/respond` and UI payload wiring.
2. Effective sources are resolved from enabled `data_source_catalog` rows, with filter mismatch handling.
3. Filter scope is enforced for source selection + internal research execution.
4. Required events are emitted:
   - `ui_data_source_filter_applied`
   - `agent_data_source_selected`.

## Phase 5: Artifact Ingestion and Knowledge Units

Deliverables:

1. Build upload ingestion pipeline:
   - artifact record creation (`artifact_type='upload'`)
   - summary/chunk extraction into `artifact_knowledge_units`
2. Add preview conversion support for artifact viewer.

Success criteria:

1. Uploaded docs appear in session panes and are retrievable by the agent.

Status update:

1. Initial synchronous ingestion implemented for uploads:
   - text extraction (`txt/md/json/html/xml/docx`)
   - summary + chunk writes to `artifact_knowledge_units`
   - artifact metadata updated with ingestion state and unit counts.

## Phase 6: Research Output Pipeline

Deliverables:

1. Standardize research output creation for each research pass:
   - markdown artifact for agent reuse (`research_markdown`)
   - user-facing output doc (`research_output_doc`)
2. Persist creation/update events and message linkage.

Success criteria:

1. Research-only sessions produce reusable context and user-readable outputs.

Status update:

1. Added baseline research output persistence in `WordUIWorkspaceV2.respond` for non-report turns.
2. Each completed research turn now generates:
   - `research_markdown` artifact (persisted markdown summary for agent reuse)
   - `research_output_doc` artifact (DOCX user-facing output)
3. Research artifact creation emits `artifact_created` events tied to the assistant message operation.
4. Per-source research output format presets are now enforced for `database_research`:
   - source/retriever metadata can set `research_output_format` (`docx`, `pdf`, `xlsx`)
   - tool always returns `research_markdown` + `research_output_doc`, with doc format determined by source preset.

## Phase 7: Report Workflow Pipeline

Deliverables:

1. Implement interactive report scaffolding in conversational flow:
   - create blank `report_working_doc`
   - iterate sections/subsections
   - capture per-section instructions
2. Implement generation tool call that replaces instruction placeholders with final content.
3. Persist final report artifacts and optional exports.

Required events:

1. `report_structure_proposed`
2. `report_structure_confirmed`
3. `report_section_instructions_captured`
4. `report_generation_started`
5. `report_generation_completed`
6. `artifact_updated`

Success criteria:

1. User can complete end-to-end report generation within one session, with fully persisted trace.

Status update:

1. Conversational report scaffolding is implemented in `WordUIWorkspaceV2.respond`:
   - report request detection
   - working DOCX artifact creation
   - primary section proposal/confirmation
   - subsection confirmation and recursive nested subsection expansion (`add deeper` / `final structure`)
   - instruction capture/defaulting
   - generation completion that updates working report + creates final report artifact.
2. Required report workflow events are now emitted in the initial path:
   - `report_structure_proposed`
   - `report_structure_confirmed`
   - `report_section_instructions_captured`
   - `report_generation_started`
   - `report_generation_completed`
   - `artifact_updated`
3. Structured instruction mapping is supported in report turns:
   - `Primary Section -> instruction`
   - `Primary Section: Subsection -> instruction`
   - `Primary Section > Subsection > Nested -> instruction`
   - `all -> instruction` fallback for unmapped sections.
4. Report generation now executes through explicit `generate_report_document` tool events:
   - emits `tool_call_request`/`tool_call_response` for generation step
   - assigns available `research_markdown` artifacts to report sections
   - injects assignment references into generated section content.
5. Added explicit `export_report_document` tool execution in report completion:
   - emits `tool_call_request`/`tool_call_response` for export step
   - creates `export_file` artifacts for requested formats (`docx`, `pdf`, `xlsx`)
   - supports native export handlers:
     - `docx`: file copy export
     - `xlsx`: structured workbook export using `openpyxl`
     - `pdf`: Word-engine conversion when available, minimal valid PDF fallback otherwise
   - links exports to the final report artifact via `source_artifact_id`.
6. Added LLM-driven adaptive report gap-fill research loop within `generate_report_document`:
   - planner prompt gives the model report requirements, current section coverage, and current research summaries
   - model returns targeted `database_research` calls (`section_key`, `source_id`, `research_statement`) or `finish`
   - iterative stopping criteria are enforced (`max calls` and `no improvement` cutoff), with heuristic fallback on invalid planner output
   - resulting research references and quality scores are written back into section assignments.
7. Added richer artifact preview rendering for non-HTML formats:
   - `pdf`: inline embedded preview for normal-size files with graceful large-file fallback
   - `xlsx`: inline worksheet table preview (openpyxl path + OOXML fallback parser).

## Phase 8a: Report Plan Card

Deliverables:

1. Implement interactive report plan card widget in the frontend chat interface.
2. Extend `/respond` request payload to accept `report_plan_state` and `report_plan_action`.
3. Extend orchestrator to emit `report_plan_card` in `content_json` of assistant messages during report workflow.
4. Wire "Start Now" action to trigger finalization and generation.
5. Support manual edit controls (add section, add subsection, edit instructions, remove, edit title).

See `REPORT_PLAN_CARD_V1.md` for full design specification.

Implementation layers:

1. **Frontend** (`src/word_ui/static/index.html`):
   - Render `report_plan_card` from `content_json` inline in assistant chat bubbles.
   - Build card HTML: section tree with collapsible nesting, status indicators, action buttons.
   - Handle "Start Now" click: send `/respond` with `report_plan_action: "start_now"` and current `report_plan_state`.
   - Handle manual edit controls: update local plan state, include in next `/respond` as `report_plan_state`.
   - Only the most recent plan card has interactive controls; older cards render as read-only snapshots.

2. **API layer** (`src/word_ui/web_server.py`):
   - Parse `report_plan_state` and `report_plan_action` from `/respond` request body.
   - Pass through to workspace V2 orchestrator.
   - No new endpoints required; all plan card behavior flows through existing `/respond`.

3. **Orchestrator** (`src/word_ui/workspace_v2.py`):
   - On report intent detection: create initial plan state, include `report_plan_card` in response `content_json`.
   - On receiving `report_plan_state` from request: inject context note into system prompt ("plan was recently updated by the user"), use incoming state as authoritative.
   - On receiving `report_plan_action: "start_now"`: fill defaults for pending sections, transition to generation pipeline.
   - Emit new event types: `report_plan_card_created`, `report_plan_state_updated`, `report_plan_start_now_triggered`.
   - Each assistant response during scaffolding includes updated plan card in `content_json`.

Success criteria:

1. User can see and interact with a visual report plan card in the chat.
2. User can click "Start Now" at any point to trigger generation with agent defaults.
3. User can add/edit/remove sections and instructions via card controls.
4. Manual edits from card controls are received and acknowledged by the orchestrator.
5. Plan card state is persisted in message events for replay.

Status update:

1. Frontend implementation completed in `src/word_ui/static/index.html`:
   - inline `report_plan_card` rendering in assistant bubbles
   - local plan state tracking (`currentReportPlanState`)
   - manual edit controls (title/section/subsection/instructions/remove)
   - "Start Now" action wiring to `/respond` with `report_plan_action: "start_now"`.
2. API passthrough implemented in `src/word_ui/web_server.py` for `report_plan_state` and `report_plan_action`.
3. Orchestrator implementation completed in `src/word_ui/workspace_v2.py`:
   - report plan card emitted in `assistant_message.content_json`
   - `report_plan_state` updates applied to workflow state
   - `report_plan_action: "start_now"` finalization/generation path
   - plan card events emitted (`report_plan_card_created`, `report_plan_state_updated`, `report_plan_start_now_triggered`).
4. Unit tests added/updated for API forwarding and report plan card behavior in:
   - `tests/unit/test_ui_web_server_v2_routes.py`
   - `tests/unit/test_ui_web_server_v2_http.py`
   - `tests/unit/test_workspace_v2_core.py`.

## Phase 8: Migration and Cleanup

Deliverables:

1. Add one-time migration utility from legacy JSON session store to Postgres (optional but recommended).
2. Deprecate JSON persistence path in workspace service.
3. Update docs/tests to V2 defaults.

Success criteria:

1. All primary session/orchestration state is Postgres-native.

Status update:

1. Migration utility is implemented and available via `word-store-migrate`.
2. V2 docs/tests are in place and actively updated as implementation progresses.
3. JSON persistence path has not yet been removed; V1/V2 coexistence remains intentionally active until cutover.

## Testing Plan

1. Repository unit tests for all CRUD/query behavior.
2. API contract tests for new endpoints and error codes.
3. End-to-end tests:
   - login -> load sessions -> hydrate -> respond
   - filtered vs unfiltered data-source turns
   - upload -> ingest -> retrieval-aware response
   - report scaffolding -> generation -> artifact updates
   - report plan card: create -> manual edit -> start now -> generation
4. Regression tests to keep current document tool operations stable.
5. Report plan card tests:
   - `report_plan_state` round-trip through `/respond` request/response.
   - `report_plan_action: "start_now"` triggers finalization and generation.
   - Manual edits in `report_plan_state` are reflected in next response card.
   - Plan card event persistence (`report_plan_card_created`, `report_plan_state_updated`, `report_plan_start_now_triggered`).
   - Frontend rendering of plan card in chat bubbles (manual/visual testing).
6. Smoke validation:
   - local HTTP flow validated for `create report -> manual plan edit -> start_now` transitions and event emission.

## Resolved Technical Decisions (2026-03-03)

1. Orchestrator execution mode: **synchronous** for now; long-run async orchestration remains a future enhancement.
2. Artifact byte storage: **filesystem-backed `storage_uri`** under allowed workspace roots in the current baseline.
3. Retrieval strategy: **keyword/metadata retrieval** with pluggable retriever adapters; vector index integration deferred.
4. Prompt windowing: **bounded recency window** (last completed messages within a character budget) plus structured system-context sections.
5. Report plan card edits: **batched local edits** sent on next `/respond` or explicit Start Now (no auto-send per edit).
6. Report plan card interactivity: **most-recent card interactive**, historical cards read-only.

## Next Implementation Focus

1. Integrate production retriever backends and relevance scoring refinements for non-mock data sources.
2. Evaluate optional async orchestration/job execution mode for very long report-generation runs.
3. Evaluate optional object-storage artifact backend and signed preview/download URL support.
4. Perform final V1 codepath retirement after compatibility window closes.
