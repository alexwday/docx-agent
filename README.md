# docx-agent

`docx-agent` is a Python project for:

1. A custom Word-focused MCP server (`src/word_mcp_server`)
2. A document operations engine (`src/word_engine`)
3. An orchestration layer for multi-step template fill workflows (`src/word_agent`)
4. A UI workspace session layer and preview renderer for chat/files/preview state (`src/word_ui`)

Current version implements the V1 API contract for reliable template-aware read/edit/create operations on `.docx` files, including atomic section replacement with style preservation.
It also includes an additive experimental tool: `convert_to_pdf` (backend availability is environment-dependent).
The V2 session-centric workspace API is also implemented for login/session hydrate/respond flows with persisted events/artifacts.
Report workflow now includes an interactive report plan card (`content_json.report_plan_card`) with manual edit controls and `report_plan_action: "start_now"` support.
Current UI renders selected `.docx` files to HTML preview artifacts and includes inline report plan card rendering in chat.

## Quick Start

1. Install:
   - `pip install -e ".[dev,mcp]"`
2. Run tests:
   - `pytest`
3. Start MCP server:
   - `word-mcp-server`
4. Start UI workspace server:
   - `word-ui-server --host 127.0.0.1 --port 8030 --allowed-root /path/to/docs --session-store .docx-agent-ui-sessions.json`
   - optional hardening flags: `--read-only`, `--api-key YOUR_KEY`
   - legacy compatibility flag (only if needed): `--enable-legacy-v1-routes`

## Project Docs

1. [Big Upgrade Plan Index](docs/BIG_UPGRADE_PLAN/README.md)
2. [V2 API Contract Plan](docs/BIG_UPGRADE_PLAN/API_CONTRACT_V2.md)
3. [Postgres Schema Plan](docs/BIG_UPGRADE_PLAN/schemas/POSTGRES_SCHEMA_V1.md)
4. [Implementation Plan](docs/BIG_UPGRADE_PLAN/implementation/IMPLEMENTATION_PLAN_V1.md)
5. [Readiness Check](docs/BIG_UPGRADE_PLAN/READINESS_CHECK_V1.md)
6. Legacy V1 docs archive: `docs/archive/legacy_v1_2026-03-02/`
