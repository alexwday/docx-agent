# CLAUDE.md - docx-agent

## Project Overview
Python project for intelligent Word document (.docx) processing with MCP server, LLM orchestration, and web UI.

## Structure
- `src/word_engine/` - Core DOCX manipulation (service.py is the main API)
- `src/word_mcp_server/` - FastMCP server exposing engine as MCP tools
- `src/word_agent/` - LLM orchestration via OpenAI for template fills
- `src/word_store/` - Postgres-backed session/message/artifact storage (V2)
- `src/word_ui/` - Web UI workspace, HTTP server, preview renderer
- `docs/` - Architecture docs, API contracts, upgrade plans
- `tests/unit/` - 20 unit test modules; `tests/e2e/` - 2 E2E test modules

## Commands
- `pip install -e ".[dev,mcp]"` - Install with all extras
- `pytest` - Run full test suite
- `pytest -q` - Quiet mode (used in CI)
- `word-mcp-server` - Start MCP server
- `word-ui-server --host 127.0.0.1 --port 8030 --allowed-root <path>` - Start web UI
- `word-store-migrate` - Run Postgres migrations

## Code Conventions
- All service methods return dicts with `status`, `contract_version`, and operation-specific fields
- Use `ok()` / `error()` helpers from `word_engine.responses`
- Error codes from `word_engine.errors.ErrorCode` (StrEnum)
- `from __future__ import annotations` in all files
- Dataclasses with `slots=True`; dependency injection via optional constructor params
- Private methods prefixed with `_`; exports defined via `__all__` in `__init__.py`
- Logging: one event per operation with `event`, `file_path`, `status`, `duration_ms`
- See `docs/CODING_STANDARDS.md` for full standards

## Testing
- pytest with `pythonpath = ["src"]` and `testpaths = ["tests"]`
- `make_service` fixture creates isolated `WordDocumentService` with `tmp_path`
- `build_sample_document()` / `build_styled_section_document()` helpers in `tests/unit/helpers.py`
- CI runs on Python 3.11, 3.12, 3.13

## Environment Variables
- `DOCX_AGENT_DATABASE_DSN` or `DATABASE_URL` - Postgres connection (required for V2/store features)
- `OPENAI_API_KEY` - Required for LLM agent features

## Key Patterns
- Path authorization: `EngineConfig.allowed_roots` prevents path traversal
- File locking: `FileLockManager` uses fcntl for thread + process-level locks
- V1 contract (basic ops) and V2 contract (session-centric with Postgres)
- Python >=3.11 required
