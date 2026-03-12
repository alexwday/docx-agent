# Roadmap

Related docs:
1. [Phase Plan](PHASES.md)
2. [Execution Status](STATUS.md)
3. [API Contract](API_CONTRACT.md)
4. [Release Checklist](RELEASE_CHECKLIST.md)
5. [UI Workspace Plan](UI_WORKSPACE_PLAN.md)

## Vision

Build one main Python Word agent, one custom Python MCP server, and one operator UI workspace for reliable document reading, targeted section replacement, template-safe style preservation, and orchestrated multi-document workflows.

## End-State Capabilities

1. Read structure and content from target and support documents.
2. Replace targeted sections atomically with style-preserving behavior.
3. Create new documents from scratch or templates.
4. Execute end-to-end template-fill workflows through an orchestration layer.
5. Expose a stable MCP API contract with backward compatibility.
6. Provide a UI workspace with chat orchestration, context file management, editable target selection, and live document preview.

## Milestones

1. V1 Core
   - Stable DOCX read/edit/create APIs.
   - `replace_section_content` with `heading_exact` and `anchors`.
   - File locking, allowlist path controls, structured error model.
2. V2 Hardening
   - Advanced style fidelity, comments/footnotes/protection.
   - Better table operations and optional PDF export.
3. V3 UI Workspace
   - Main conversational workspace for the agent.
   - Sidebar for uploaded context files.
   - Sidebar for editable target files.
   - Large preview pane for the selected DOCX file.
4. V4 Ecosystem
   - Companion conversion/ingestion adapters (Pandoc/MarkItDown).
   - Extended selectors and semantic section targeting.

## Non-Goals

1. Full Office COM automation.
2. Large Microsoft Graph tool parity.
3. One-to-one feature parity with every upstream repository.
