# Readiness Check V1 (Current Status)

Date: 2026-03-03

## Verdict

Current Phase 8 + 8a target scope is implemented at a baseline functional level. Core V2 flow (including report plan card) is functional and test-covered; remaining work is post-plan enhancement and final cutover cleanup.

## Status Snapshot (2026-03-03)

1. Current test status: `100 passed, 5 skipped` (`pytest -q`).
2. Implemented in baseline form:
   - 9-digit employee login -> user session list -> session hydrate -> respond flow
   - persisted message/event/artifact/knowledge/data-source repositories on Postgres
   - data-source filter enforcement + per-turn event trace
   - `database_research` tool contract with retriever routing and source-specific output format presets
   - uploaded document ingestion (summary/chunk knowledge units)
   - conversational report scaffold/generate/export workflow with persisted artifacts/events
   - interactive report plan card workflow with manual plan edits and `report_plan_action: "start_now"`.
3. Remaining high-priority implementation gaps (current scope):
   - none for the current Phase 8 + Phase 8a target scope; core planned slices are implemented at baseline.
4. Post-plan enhancement backlog:
   - production-grade retriever integrations beyond mock/baseline handlers
   - optional async orchestration mode for very long-running generations
   - optional object-storage artifact backend and signed preview/download URLs.

## Ready

1. Target architecture and data model are defined.
2. API contract for session/login/hydrate/respond flow is defined.
3. Data source filtering behavior is defined.
4. Workflow alignment doc maps user journey to schema and events.
5. Tooling-agnostic Postgres migration SQL is drafted.
6. Implementation phases are defined with module-level touchpoints.

## Technical Decisions (Locked 2026-03-03)

1. DB access stack: `psycopg` SQL-first repositories.
2. Artifact byte storage: local filesystem-backed `storage_uri` in current baseline.
3. Orchestrator execution mode: synchronous for current report/research workflows.
4. Retrieval strategy for `artifact_knowledge_units`: keyword/metadata filtering with pluggable retrievers (vector integration deferred).
5. Prompt windowing strategy: bounded recency window + structured system-context injection.

## Migration Risk Notes (Current)

1. Runtime now defaults to V2-first routing when V2 workspace is configured; legacy V1 routes require explicit opt-in.
2. Existing V1 docs were archived to avoid planning ambiguity.
3. Legacy V1 route path remains available behind the `--enable-legacy-v1-routes` compatibility flag.
4. Full V1 runtime retirement is still outstanding until the compatibility window closes.
