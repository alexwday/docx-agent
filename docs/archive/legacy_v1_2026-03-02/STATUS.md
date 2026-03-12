# Status

Related docs:
1. [Roadmap](ROADMAP.md)
2. [Phase Plan](PHASES.md)
3. [API Contract](API_CONTRACT.md)
4. [Release Checklist](RELEASE_CHECKLIST.md)
5. [UI Workspace Plan](UI_WORKSPACE_PLAN.md)

## Snapshot

Date: 2026-02-28

1. Current milestone: `V1 Core + Phase 5 Hardening`
2. Current focus: Phase 5 closure + Phase 6 experimental features + Phase 7.4 UI hardening baseline.
3. Last verified test command + result:
   - Command: `pytest -q`
   - Result: `52 passed, 3 skipped in 1.08s`

## Completed Since Last Milestone

1. Implemented all v1 engine APIs (12 contract tools).
2. Implemented MCP server wrapper around engine service.
3. Implemented baseline agent orchestration interfaces.
4. Added unit and e2e coverage for read/edit/replace/workflow flows.
5. Published canonical planning and architecture docs.
6. Added Phase 5 gap-closure tests:
   - large fixture-backed file-size guard
   - multiprocessing contention safety (environment-aware)
   - MCP runtime dependency/guidance smoke coverage.
7. Started Phase 6 with additive experimental PDF export:
   - `convert_to_pdf` implemented in service and MCP layer
   - backend behavior covered with deterministic unit tests.
8. Added Phase 7 planning scope for operator UI workspace:
   - conversation panel
   - context-files sidebar
   - editable-targets sidebar
   - selected-docx preview pane
9. Implemented Phase 7.1 UI scaffold:
   - new `word_ui` module with session state contract
   - chat/context/target/preview event APIs
   - execution hooks for `run_plan`, `apply_plan`, `validate_result`
   - baseline e2e UI state-flow test coverage.
10. Implemented Phase 7.2 preview rendering:
   - `DocxPreviewRenderer` converts selected `.docx` to HTML preview artifacts
   - `refresh_preview` now performs real rendering and returns artifact metadata
   - `apply_plan` triggers preview refresh after successful section updates.
11. Implemented Phase 7.3 browser workspace shell:
   - `word-ui-server` HTTP runtime with session/event APIs
   - three-panel web UI: conversation, file sidebars, preview pane
   - browser actions wired to run/apply/validate/refresh workflows.
12. Implemented Phase 7.4 baseline hardening:
   - `word_ui` path allowlist checks for context and editable target files
   - session persistence/recovery through JSON session store
   - web-layer operation guards (`--read-only`, optional `--api-key`)
   - API key input support in browser shell.
13. Added socket-independent guarded-route integration coverage:
   - pure dispatch validation for `api_key` and `read_only` behavior
   - coverage runs in sandboxed environments without network bind.
14. Added socket-bound guarded endpoint tests for unrestricted runners:
   - API key and read-only behavior validated through real HTTP requests
   - tests are environment-aware and skip when bind permissions are restricted.

## In Progress

Checklist (Owner: `core-engine`, Target: `2026-03-01`):
1. [x] Add idempotency tests for repeated operations.
2. [x] Add deterministic ordering/index tests for read outputs.
3. [x] Add safety-path tests: allowlist, max file size, selector failures, range bounds.
4. [x] Add log-field assertions for success and failure events.
5. [x] Re-run full regression and publish updated test totals.

## Next Up (Prioritized Backlog)

Checklist (Owner: `core-engine`, Target window: `2026-03-02` to `2026-03-05`):
1. [x] Finalize Phase 5 hardening closure note in `PHASES.md`.
2. [x] Add deterministic/idempotent behavior notes to `ARCHITECTURE.md`.
3. [x] Expand concurrency safety tests for higher contention.
4. [x] Add release checklist for v1 stabilization (versioning and changelog policy).
5. [x] Add CI workflow for multi-version regression and MCP guidance smoke checks.
6. [ ] Close Phase 5 in `PHASES.md` after first unrestricted CI confirmation for multiprocessing coverage.
7. [x] Create `word_ui` module scaffold and session state contract for chat/files/preview.
8. [x] Define UI-to-agent interaction API for message, plan, apply, and refresh events.
9. [x] Add baseline e2e test for UI workspace state transitions (context files, targets, preview selection).
10. [x] Implement Phase 7.2 preview rendering pipeline for selected `.docx`.
11. [x] Add browser UI shell for conversation panel + dual sidebars + preview pane (Phase 7.3).
12. [x] Add UI session persistence/recovery behavior beyond in-memory state.
13. [x] Add UI hardening for path/permission controls at web layer and operation auth boundaries.
14. [x] Add integration validation for web-layer guarded endpoints via socket-independent dispatcher tests.
15. [x] Add unrestricted-run test suite for socket-bound HTTP endpoint behavior (environment-aware in sandbox).
16. [ ] Confirm socket-bound guard tests executed on unrestricted CI runner and capture job evidence.

## Known Gaps / Risks

Checklist (Owner: `core-engine`, Next action date: `2026-03-02`):
1. [x] Verify selector failure modes for both missing start and missing end anchors.
2. [x] Validate logging schema coverage for success and failure paths.
3. [x] Confirm guard behavior via low max-file-size tests.
4. [x] Add fixture-backed file-size guard tests for larger real-world documents.
5. [x] Add multiprocessing contention tests (with environment-aware skip where process pools are restricted).
6. [x] Confirm MCP runtime dependency installation guidance remains accurate after packaging changes.
7. [ ] Validate multiprocessing contention test on an unrestricted CI runner (current local sandbox enforces a skip).
8. [ ] Confirm first successful run of `.github/workflows/ci.yml` and capture job links in this document.
9. [ ] Validate real backend PDF conversion path on runner with `docx2pdf` or LibreOffice installed.
10. [x] UI implementation stack selected for baseline: built-in `ThreadingHTTPServer` + static browser shell + HTML preview artifacts.
11. [x] Browser shell integration is implemented (`word-ui-server` + static workspace client).
12. [x] Session persistence/recovery is implemented via JSON session store.
13. [ ] Preview is HTML artifact-based (good for speed) but not full Word-layout fidelity.
14. [ ] Browser-layer tests that require socket bind are environment-restricted and currently skip in sandbox.
15. [ ] API-key mode currently requires manual key entry in UI and lacks stronger auth/session management.
16. [ ] `/api/config` mode introspection is implemented, but UI auth flow still relies on manual key handling.

## Definition of Ready for Next Wave

A wave is considered ready when all conditions are met:
1. Test suite is fully green.
2. Hardening checklist items for the active phase are either completed or explicitly deferred with rationale.
3. Known gaps have owner + next action date.
4. No API contract-breaking changes were introduced (v1 response schema remains stable).
5. UI phase start criteria are documented:
   - framework and rendering approach selected
   - session state contract written
   - first scaffold and e2e smoke test merged
6. UI phase continuation criteria are documented:
   - preview rendering implemented
   - persistence model chosen
   - browser shell integrated with `word_ui` events
