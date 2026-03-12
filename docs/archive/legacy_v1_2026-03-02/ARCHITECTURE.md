# Architecture

Related docs:
1. [Roadmap](ROADMAP.md)
2. [Phase Plan](PHASES.md)
3. [Execution Status](STATUS.md)
4. [UI Workspace Plan](UI_WORKSPACE_PLAN.md)

## Components

1. `word_engine`
   - Core DOCX operations using `python-docx`.
   - Path security checks, file locking, atomic writes.
   - Style capture/reapply logic for section replacement.
   - Experimental PDF export backend resolution (`docx2pdf` or LibreOffice).
2. `word_mcp_server`
   - MCP tool registration layer.
   - Thin wrapper around `word_engine` service methods.
3. `word_agent`
   - Orchestration API for planning and applying multi-section workflows.
   - Uses `word_engine` APIs directly in-process for V1.
4. `word_ui` (Phase 7.1 scaffold implemented)
   - In-process session state service for conversation-driven document operations.
   - Event APIs for chat, context-file list, editable-target list, preview selection/refresh.
   - Execution bridge APIs for `run_plan`, `apply_plan`, and `validate_result`.
   - Preview renderer (`DocxPreviewRenderer`) that generates HTML artifacts from selected `.docx` files.
   - Browser UI shell (`web_server.py` + `static/index.html`) for operator interaction.
   - Session persistence/recovery via JSON session store.
   - UI-side path allowlist checks and web-layer operation guards (`read_only`, optional API key).
   - Socket-independent API dispatch path for deterministic guard testing.
   - Server config endpoint (`/api/config`) for UI mode/auth introspection.

## Data Flow

1. User action enters the planned browser shell or calls `word_ui` workspace APIs directly.
2. `word_ui` updates session state and calls `word_agent` orchestration handlers.
3. `word_agent` invokes `word_mcp_server` tools (or in-process `word_engine` calls where configured).
4. Service validates input, acquires lock, loads/modifies DOCX.
5. Mutations write to temp file and atomically replace target.
6. Structured response and operation events return to `word_ui`.
7. `word_ui` refreshes target list state and document preview for the selected file.
8. Preview artifacts are written under a per-document `.docx-agent-preview/` directory by default.
9. Browser client loads preview via `/api/sessions/{session_id}/preview/content`.
10. Workspace session state is persisted to configured session-store path and reloaded on startup.

## Concurrency

1. Per-file in-memory re-entrant lock.
2. Per-file `.lock` advisory file lock for process-level coordination.

## Atomicity

1. Mutating operations save to temp file in target directory.
2. `os.replace` performs atomic swap on success.
3. Any failure returns error response without partial save.

## Determinism and Idempotency

1. Read operations return stable ordering:
   - `get_document_outline` returns heading entries in paragraph index order.
   - `find_text` returns matches ordered by `(paragraph_index, start)`.
2. Repeated mutation operations with equivalent inputs should converge:
   - `replace_section_content` can be re-run with same payload without further structural drift.
   - `search_and_replace` with equivalent replacement text preserves stable output.
3. Hardening tests assert deterministic ordering and repeated-run stability.

## Logging Schema

1. `event`: operation key (for example `replace_section_content`)
2. `file_path`: normalized target path
3. `status`: `ok` or `error`
4. `error_code`: present on errors
5. `duration_ms`: execution time

## Testing Strategy

1. Unit tests for each API method and error path.
2. Contract tests for response shape and error codes.
3. Style-preservation tests for `replace_section_content`.
4. E2E workflow tests through `word_agent`.
5. Phase 5 hardening tests for idempotency, safety-path coverage, concurrency, and logging assertions.

## CI Enforcement

1. GitHub Actions workflow: `.github/workflows/ci.yml`
2. Matrix test job runs full `pytest -q` with Python 3.11/3.12/3.13 and `mcp` extras installed.
3. Dedicated no-`mcp` smoke job validates runtime guidance path for missing `fastmcp`.

## Experimental Features

1. `convert_to_pdf` is currently additive and experimental.
2. Conversion backend selection is runtime-dependent:
   - `docx2pdf` when installed and functional
   - fallback to `soffice` / `libreoffice` headless conversion
3. Backend unavailability/failure returns structured `DOCX_ERROR` without mutating source documents.

## Planned UI Surfaces

1. Conversation Surface
   - Threaded message history for task requests and execution reports.
   - Supports plan/build/apply/validate style workflow prompts.
2. Context File Surface
   - Lists uploaded supporting files available for agent context.
   - Shows file type, last update time, and add/remove actions.
3. Editable Target Surface
   - Lists files explicitly allowed for edits in active session.
   - Provides active-file selector and quick operation actions.
4. Preview Surface
   - Large preview of the selected target document.
   - Refreshes after successful write operations.
   - Read-only mode in initial phase; editing stays tool-driven.
