# Phases

Related docs:
1. [Roadmap](ROADMAP.md)
2. [Execution Status](STATUS.md)
3. [API Contract](API_CONTRACT.md)
4. [Release Checklist](RELEASE_CHECKLIST.md)
5. [UI Workspace Plan](UI_WORKSPACE_PLAN.md)

## Phase 0: Foundation

Status: `DONE`

Scope:
1. Publish canonical planning and architecture docs.
2. Freeze v1 response and error model.
3. Define coding/logging/testing conventions.

Exit Criteria:
1. Canonical docs exist and are internally consistent.
2. Error codes and contract version are documented.

Evidence:
1. `docs/ROADMAP.md`
2. `docs/PHASES.md`
3. `docs/API_CONTRACT.md`
4. `docs/ARCHITECTURE.md`
5. `docs/CODING_STANDARDS.md`

## Phase 1: Server Skeleton + Read APIs

Status: `DONE`

Scope:
1. Build service layer and tool registration skeleton.
2. Implement read lifecycle APIs.

Exit Criteria:
1. API methods are available with v1 response shape.
2. Unit tests cover base read path behavior.

Evidence:
1. `src/word_engine/service.py`
2. `src/word_mcp_server/server.py`
3. `tests/unit/test_contract_and_read.py`

## Phase 2: Editing Primitives

Status: `DONE`

Scope:
1. Implement deterministic primitive mutations.
2. Add validation and locking primitives.

Exit Criteria:
1. Insert/delete/search-replace operations behave deterministically.
2. Lock strategy prevents conflicting writes.

Evidence:
1. `src/word_engine/service.py`
2. `src/word_engine/locking.py`
3. `tests/unit/test_edit_primitives.py`

## Phase 3: Atomic Section Replacement

Status: `DONE`

Scope:
1. Implement `replace_section_content` for `heading_exact` and `anchors`.
2. Implement style capture/reapply and fallback.
3. Add atomic write behavior and `dry_run`.

Exit Criteria:
1. Section replacement is non-destructive and atomic.
2. Style-preserving behavior is validated by tests.

Evidence:
1. `src/word_engine/service.py`
2. `tests/unit/test_replace_section.py`

## Phase 4: Agent Workflows

Status: `DONE`

Scope:
1. Provide orchestration interfaces:
   - `plan_template_fill`
   - `generate_section_content`
   - `apply_section_plan`
   - `validate_document_result`
2. Validate end-to-end baseline workflow.

Exit Criteria:
1. E2E workflow executes successfully against generated fixtures.

Evidence:
1. `src/word_agent/orchestrator.py`
2. `tests/e2e/test_agent_workflow.py`

## Phase 5: Quality/Safety

Status: `IN_PROGRESS`

Scope:
1. Add deterministic output checks.
2. Add idempotency and expanded safety/failure-path tests.
3. Validate structured diagnostics fields across success/failure logs.

Exit Criteria:
1. Full regression suite is green.
2. New hardening tests are green.
3. Remaining risks are listed in `docs/STATUS.md`.

Evidence:
1. `tests/unit/test_phase5_hardening.py`
2. `tests/unit/test_edit_primitives.py`
3. `tests/unit/test_replace_section.py`
4. `docs/STATUS.md` (gaps, owners, next actions)
5. `.github/workflows/ci.yml` (unrestricted-run validation path)

## Phase 6: Advanced Expansion

Status: `IN_PROGRESS`

Scope:
1. Add advanced document features (comments/footnotes/protection).
2. Add optional conversion and ingestion adapters.
3. Keep API compatibility through additive changes.

Exit Criteria:
1. New features are gated and documented without breaking v1 API shape.

Evidence:
1. `src/word_engine/service.py` (`convert_to_pdf`)
2. `src/word_mcp_server/server.py` (`convert_to_pdf` tool)
3. `tests/unit/test_phase6_pdf_export.py`

Not Started / Deferred:
1. Comment extraction/insertion APIs.
2. Footnote/endnote APIs.
3. Document protection APIs.
4. Optional PDF conversion integration hardening beyond baseline slice.
5. Pandoc/MarkItDown companion adapters.

## Phase 7: UI Workspace

Status: `IN_PROGRESS`
Milestone mapping: `V3 UI Workspace`

Scope:
1. Build a primary conversation panel for the orchestration agent.
2. Add a context-files sidebar for uploaded/reference documents.
3. Add an editable-targets sidebar for documents selected for mutation.
4. Add a large preview panel for the currently selected `.docx` target.
5. Add session wiring between UI actions and MCP tool invocations.

Exit Criteria:
1. User can run a complete template-fill flow from the UI without terminal interaction.
2. Selected target document preview updates after successful mutation operations.
3. Context and target file lists are independently managed and persisted per session.
4. Integration tests cover chat message flow, file-list updates, and preview refresh.
5. Phase 7.1 scaffold is complete with session contract and e2e smoke coverage.

Evidence:
1. `src/word_ui/models.py` (session state contract)
2. `src/word_ui/workspace.py` (chat/files/preview/execution events)
3. `src/word_ui/preview.py` (docx-to-html preview pipeline)
4. `src/word_ui/web_server.py` (browser shell + API routes)
5. `src/word_ui/static/index.html` (conversation/sidebar/preview layout)
6. `tests/e2e/test_ui_workspace_flow.py`
7. `tests/unit/test_ui_preview_renderer.py`
8. `tests/unit/test_ui_web_server.py`
9. `tests/unit/test_ui_workspace_hardening.py`
10. `tests/unit/test_ui_web_server_guards.py`
11. `tests/unit/test_ui_web_server_http_guards.py` (socket-bound, environment-aware)
12. `docs/UI_WORKSPACE_PLAN.md`

Progress:
1. [x] Phase 7.1 scaffold (session state + event contract + e2e smoke test)
2. [x] Phase 7.2 preview rendering pipeline
3. [x] Phase 7.3 chat-to-workflow UI integration
4. [x] Phase 7.4 baseline hardening (path allowlist, session persistence/recovery, read-only/API-key guards)
5. [x] Phase 7.4 extended hardening slice: sandbox-independent guarded-route integration coverage
6. [x] Phase 7.4 extended hardening slice: socket-bound guarded endpoint tests (environment-aware skip in restricted runners)
7. [ ] Phase 7.4 extended hardening remaining: stronger auth UX/session model and higher-fidelity preview path

Not Started / Deferred:
1. Real-time collaborative editing.
2. Multi-user auth/roles.
3. Browser-side direct DOCX editing without server round-trip.
