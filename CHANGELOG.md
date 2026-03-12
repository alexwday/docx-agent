# Changelog

## 0.1.0

1. Created initial project structure for `word_engine`, `word_mcp_server`, and `word_agent`.
2. Added v1 contract docs and architecture/phase roadmap docs.
3. Implemented v1 document APIs including atomic `replace_section_content`.
4. Added unit and e2e tests for read/edit/replace/orchestration workflows.

## 0.1.1

1. Added status-aware execution docs:
   - `docs/STATUS.md`
   - updated `docs/PHASES.md` with phase states and evidence.
2. Added Phase 5 hardening test suite in `tests/unit/test_phase5_hardening.py`:
   - idempotency coverage
   - deterministic read output checks
   - safety/failure-path coverage
   - structured log-field assertions.
3. Expanded hardening coverage with:
   - large fixture-backed file-size guard tests
   - multiprocessing contention tests (environment-aware)
   - MCP runtime dependency/guidance smoke test.
4. Expanded regression baseline from 15 tests to 29 tests (plus 1 environment-dependent skip in sandboxed runners).
5. Added CI workflow `.github/workflows/ci.yml`:
   - Python 3.11/3.12/3.13 matrix for full regression
   - no-`mcp` smoke job for missing-`fastmcp` runtime guidance path.
6. Added release operations checklist in `docs/RELEASE_CHECKLIST.md` and linked it across docs.

## 0.1.2

1. Added additive experimental PDF export API:
   - `WordDocumentService.convert_to_pdf`
   - `word_mcp_server` tool registration for `convert_to_pdf`.
2. Implemented backend selection/fallback logic:
   - `docx2pdf` when available
   - fallback to `soffice` / `libreoffice`.
3. Added deterministic unit tests in `tests/unit/test_phase6_pdf_export.py` for:
   - missing source and invalid output path errors
   - mocked success path
   - default output path behavior
   - backend failure path.
4. Updated docs (`API_CONTRACT.md`, `ARCHITECTURE.md`, `PHASES.md`, `STATUS.md`) to track the Phase 6 experimental slice.

## 0.1.3

1. Added Phase 7.1 UI workspace scaffold in new `word_ui` package:
   - session state contract models (`WorkspaceSession`, `SessionPlan`, `PreviewState`, `ChatMessage`)
   - event APIs for chat, context files, editable targets, and preview selection/refresh
   - execution bridge APIs for `run_plan`, `apply_plan`, and `validate_result`.
2. Added baseline UI workflow e2e coverage in `tests/e2e/test_ui_workspace_flow.py`.
3. Updated planning docs to track active UI execution:
   - `docs/PHASES.md` (`Phase 7` now `IN_PROGRESS`)
   - `docs/STATUS.md` (new backlog and risk updates)
   - `docs/ARCHITECTURE.md` (implemented scaffold noted)
   - `docs/UI_WORKSPACE_PLAN.md` (Phase 7.1 marked done).

## 0.1.4

1. Implemented Phase 7.2 preview pipeline:
   - new `DocxPreviewRenderer` in `src/word_ui/preview.py`
   - `.docx` to HTML preview artifact generation
   - default artifact location under `.docx-agent-preview/`.
2. Wired preview rendering into `WordUIWorkspace.refresh_preview` and post-apply workflow path.
3. Expanded tests:
   - new `tests/unit/test_ui_preview_renderer.py`
   - updated `tests/e2e/test_ui_workspace_flow.py` to assert preview artifacts exist after apply.
4. Updated roadmap tracking docs to mark Phase 7.2 complete and move next focus to Phase 7.3 browser UI integration.

## 0.1.5

1. Added browser UI shell runtime:
   - `src/word_ui/web_server.py` with HTTP endpoints for session, chat, file lists, preview, plan/apply/validate
   - `word-ui-server` script entrypoint in `pyproject.toml`.
2. Added full-page workspace UI:
   - `src/word_ui/static/index.html`
   - three-panel layout with conversation, context/target sidebars, and live preview iframe.
3. Added web-shell coverage:
   - `tests/unit/test_ui_web_server.py` for static template load and endpoint lifecycle.
4. Updated docs to mark Phase 7.3 complete and shift remaining work to Phase 7.4 hardening.

## 0.1.6

1. Added Phase 7.4 baseline hardening in `word_ui/workspace.py`:
   - path allowlist enforcement for context/target file registration
   - file existence validation before registration and operation use
   - session persistence/recovery via configurable JSON session store.
2. Added web-layer operation guards in `word_ui/web_server.py`:
   - `--read-only` mode to block document mutation route(s)
   - optional `--api-key` to protect sensitive workspace routes.
3. Updated browser shell to support API-key protected operations:
   - optional API key input that sends `X-API-Key` header.
4. Added hardening tests:
   - `tests/unit/test_ui_workspace_hardening.py`
   - expanded `tests/unit/test_ui_web_server.py` route guard coverage.
5. Updated docs (`PHASES.md`, `STATUS.md`, `UI_WORKSPACE_PLAN.md`, `ARCHITECTURE.md`, `README.md`) for Phase 7.4 baseline progress.

## 0.1.7

1. Added socket-independent web guard dispatcher in `src/word_ui/web_server.py`:
   - `dispatch_api_post(...)` for deterministic route handling without socket binding
   - reusable helpers for route classification (`is_document_mutation_route`, `requires_api_key`).
2. Added guarded-route integration tests in `tests/unit/test_ui_web_server_guards.py`:
   - API key enforcement checks
   - read-only mutation-route blocking checks.
3. Updated `tests/unit/test_ui_web_server.py` to use module-level route helper APIs.
4. Updated planning docs to reflect Phase 7.4 extended hardening slice completion for sandbox-independent guard coverage.

## 0.1.8

1. Added server mode/config endpoint in `src/word_ui/web_server.py`:
   - `GET /api/config` returns `read_only` and `api_key_required`
   - browser shell now surfaces server mode/auth state.
2. Added socket-bound guarded endpoint tests in `tests/unit/test_ui_web_server_http_guards.py`:
   - real HTTP validation for API-key and read-only route controls
   - environment-aware skip in restricted sandboxes.
3. Hardened API key header handling to be case-insensitive in dispatch path.
4. Updated UI shell API-key UX:
   - optional key persistence in `sessionStorage`
   - `X-API-Key` header automatically attached when provided.

## 0.1.9

1. Implemented interactive report plan card workflow across V2 stack:
   - frontend card rendering + controls in `src/word_ui/static/index.html`
   - API passthrough of `report_plan_state` / `report_plan_action` in `src/word_ui/web_server.py`
   - orchestrator plan-state handling, Start Now generation path, and `content_json.report_plan_card` in `src/word_ui/workspace_v2.py`.
2. Added report plan card event coverage in report workflow:
   - `report_plan_card_created`
   - `report_plan_state_updated`
   - `report_plan_start_now_triggered`.
3. Added and updated unit tests for request forwarding and report plan behavior:
   - `tests/unit/test_ui_web_server_v2_routes.py`
   - `tests/unit/test_ui_web_server_v2_http.py`
   - `tests/unit/test_workspace_v2_core.py`.
4. Refreshed upgrade/status documentation for the implemented Phase 8a slice:
   - `README.md`
   - `docs/BIG_UPGRADE_PLAN/README.md`
   - `docs/BIG_UPGRADE_PLAN/API_CONTRACT_V2.md`
   - `docs/BIG_UPGRADE_PLAN/implementation/IMPLEMENTATION_PLAN_V1.md`
   - `docs/BIG_UPGRADE_PLAN/READINESS_CHECK_V1.md`.

## 0.1.10

1. Completed planner-quality hardening across research/report loops in `src/word_ui/workspace_v2.py`:
   - stronger research-statement normalization for planner outputs
   - iterative stall/budget stop reasons and per-source/section call controls
   - richer gap-fill stop metadata (`gap_fill_stop_reason`) in generation results.
2. Added semantic cross-section dependency modeling in generated report content:
   - dependency map derived from parent/sibling/child structure and source assignments
   - generated sections now include explicit cross-section dependency guidance.
3. Improved preview UX for large artifacts:
   - large-file PDF preview mode with size metadata and inline-render guardrails
   - adaptive XLSX preview limits (`full`, `balanced`, `large-file` modes) with explicit mode messaging.
4. Completed V2 cutover hardening in web server routing:
   - V2-first behavior when V2 workspace is configured
   - legacy V1 `/api` routes moved behind explicit opt-in (`--enable-legacy-v1-routes`)
   - server config now reports `legacy_v1_routes_enabled` and `v2_enabled`.
5. Expanded test coverage for the new completion slice:
   - planner normalization and dependency-content assertions
   - large-file preview behavior checks
   - V2 HTTP behavior asserting legacy-route disablement under V2 mode.
6. Updated plan/readiness docs to lock technical decisions and mark the prior gap list complete for current target scope.
