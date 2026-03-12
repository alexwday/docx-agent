# UI Workspace Plan

Related docs:
1. [Roadmap](ROADMAP.md)
2. [Phase Plan](PHASES.md)
3. [Execution Status](STATUS.md)
4. [Architecture](ARCHITECTURE.md)

## Objective

Provide a single operator workspace to run and monitor document workflows without terminal usage.

## Required Layout (V1 UI)

1. Main conversation panel:
   - User prompts and agent responses.
   - Execution status and operation summaries.
2. Context files sidebar:
   - Uploaded/supporting files available for reasoning context.
   - Add/remove actions and file metadata display.
3. Editable targets sidebar:
   - Files approved for write operations.
   - Active target selector used by plan/apply actions.
4. Large document preview:
   - Shows the selected target `.docx`.
   - Refreshes after successful mutations.

## Interaction Contract

1. Chat events:
   - `send_message(session_id, text)`
   - `agent_response(session_id, text, operation_refs[])`
2. File-list events:
   - `add_context_file(session_id, file_path)`
   - `remove_context_file(session_id, file_path)`
   - `add_editable_target(session_id, file_path)`
   - `remove_editable_target(session_id, file_path)`
3. Preview events:
   - `select_preview_file(session_id, file_path)`
   - `refresh_preview(session_id, file_path, revision_id)`
4. Execution events:
   - `run_plan(session_id, objective)`
   - `apply_plan(session_id, plan_id)`
   - `validate_result(session_id, target_doc)`

## Backend Integration

1. UI calls `word_agent` session endpoints.
2. `word_agent` uses MCP tools from `word_mcp_server`.
3. Document operations remain in `word_engine`.
4. Preview source is generated from selected target (`.docx` -> preview format) with read-only rendering.

## Proposed Phase Steps

1. Phase 7.1 Scaffold:
   - Create `src/word_ui/` app shell and session store.
   - Wire chat + file-list state only (no preview renderer yet).
2. Phase 7.2 Preview:
   - Implement selected-document preview pipeline.
   - Refresh preview on write-complete events.
3. Phase 7.3 Workflow integration:
   - Bind chat actions to `plan_template_fill`, `apply_section_plan`, and `validate_document_result`.
   - Add operation timeline in conversation stream.
4. Phase 7.4 Hardening:
   - Permission checks for editable targets.
   - Session persistence and recovery.
   - E2E reliability tests.

## Progress Status

1. Phase 7.1: `DONE`
   - Evidence:
     - `src/word_ui/models.py`
     - `src/word_ui/workspace.py`
     - `tests/e2e/test_ui_workspace_flow.py`
2. Phase 7.2: `DONE`
   - Evidence:
     - `src/word_ui/preview.py`
     - `src/word_ui/workspace.py` (`refresh_preview` integration)
     - `tests/unit/test_ui_preview_renderer.py`
     - `tests/e2e/test_ui_workspace_flow.py`
3. Phase 7.3: `DONE`
   - Evidence:
     - `src/word_ui/web_server.py`
     - `src/word_ui/static/index.html`
     - `tests/unit/test_ui_web_server.py`
4. Phase 7.4: `IN_PROGRESS`
   - Baseline completed:
     - `src/word_ui/workspace.py` (allowed-root enforcement + session persistence/recovery)
     - `src/word_ui/web_server.py` (`--read-only` and optional `--api-key` operation guards)
     - `tests/unit/test_ui_workspace_hardening.py`
   - Extended slice completed:
     - `src/word_ui/web_server.py` (`dispatch_api_post` pure route dispatcher)
     - `tests/unit/test_ui_web_server_guards.py` (guarded route coverage without socket bind)
     - `tests/unit/test_ui_web_server_http_guards.py` (socket-bound guarded endpoint coverage; skips in restricted sandboxes)
   - Remaining:
     - broader integration coverage on unrestricted runners
     - improved preview fidelity options beyond HTML artifact baseline

## Acceptance Criteria

1. Full template-fill flow can be started and completed from UI.
2. Context and target file lists remain distinct and session-persistent.
3. Preview reflects selected file and post-edit output.
4. E2E tests validate chat-to-edit-to-preview lifecycle.
5. No v1 API contract breakage in MCP layer.
