# Agent Handoff: Report Plan Card Implementation

## What You're Building

An interactive **report plan card** — an HTML widget that renders inline in assistant chat messages during the report creation workflow. It gives users a visual, editable view of their evolving report plan and a "Start Now" button to trigger generation at any point.

## Where to Find the Design

Read these documents in this order:

1. **`docs/BIG_UPGRADE_PLAN/REPORT_PLAN_CARD_V1.md`** — the primary design spec. Read this first. It covers the full data model (plan state JSON), frontend behavior, API changes, orchestrator behavior, event types, and a conceptual wireframe.

2. **`docs/BIG_UPGRADE_PLAN/API_CONTRACT_V2.md`** — updated with the new request fields (`report_plan_state`, `report_plan_action`) on `POST /respond` and the `report_plan_card` in response `content_json`. See the "Report Workflow Semantics" section.

3. **`docs/BIG_UPGRADE_PLAN/WORKFLOW_ALIGNMENT_V1.md`** — section 5 ("Report Creation Mode") has been rewritten to describe the plan card lifecycle and the two entry paths (simple vs detailed).

4. **`docs/BIG_UPGRADE_PLAN/implementation/IMPLEMENTATION_PLAN_V1.md`** — Phase 8a defines the implementation deliverables across frontend, API, and orchestrator layers with success criteria.

5. **`docs/BIG_UPGRADE_PLAN/schemas/POSTGRES_SCHEMA_V1.md`** — updated with three new `message_events` event types for plan card tracking.

## Files to Modify

### 1. Frontend: `src/word_ui/static/index.html`

This is a single-file HTML/CSS/JS application (~1221 lines). Key areas:

- **`renderMessages()` function (~line 844)**: currently renders chat bubbles as plain text from `msg.content_text`. You need to extend this to detect `msg.content_json.report_plan_card` and render the plan card widget inside the bubble.

- **`sendMessage()` function (~line 1131)**: currently builds a payload with `message`, `response_mode`, and optional `data_source_filters`. You need to extend this to include `report_plan_state` and `report_plan_action` when relevant.

- **New state**: add a `currentReportPlanState` variable to track the local plan state. Updated by card controls and included in the next `/respond` call.

- **New function**: `renderReportPlanCard(planCard, isLatest)` — builds the card HTML with section tree, action buttons (add section, add subsection, edit instructions, remove), and "Start Now" button. `isLatest` controls whether interactive controls are enabled (older cards are read-only).

- **New function**: `handlePlanCardAction(action, data)` — handles button clicks from the card. For "Start Now", sends a `/respond` with `report_plan_action: "start_now"`. For manual edits, updates `currentReportPlanState`.

- **CSS**: add styles for the plan card widget. Follow the existing design language (use CSS variables already defined: `--sidebar-bg`, `--sidebar-surface`, `--sidebar-border`, `--sidebar-accent`, etc.).

### 2. API Layer: `src/word_ui/web_server.py`

- In the V2 `/respond` route handler: parse `report_plan_state` and `report_plan_action` from the request JSON body. Pass them through to the workspace V2 `respond()` method. No new endpoints needed.

### 3. Orchestrator: `src/word_ui/workspace_v2.py` (~4273 lines)

This is the main orchestration engine. Key areas to modify:

- **Report intent detection**: when the orchestrator detects a user asking to create a report, it should create the initial plan state and include `report_plan_card` in the response's `content_json`.

- **Plan state handling in `respond()`**: when the request includes `report_plan_state`, inject a context note into the system prompt: "The report plan was recently updated by the user. Review the updated plan before proceeding." Use the incoming state as the authoritative plan state.

- **"Start Now" handling**: when `report_plan_action == "start_now"`, fill default instructions for any sections with `status: "pending"`, then trigger the existing gap-fill research and report generation pipeline.

- **Plan card in every scaffolding response**: each assistant response during the report workflow should include the current plan state as `report_plan_card` in `content_json`.

- **New events**: emit `report_plan_card_created`, `report_plan_state_updated`, and `report_plan_start_now_triggered` events via the existing `message_events` persistence.

### 4. Tests

- **Unit tests**: add tests in `tests/unit/` for:
  - `report_plan_state` and `report_plan_action` parsed correctly in `/respond` route.
  - Orchestrator emits `report_plan_card` in `content_json` when in report workflow.
  - "Start Now" action triggers finalization and generation.
  - Manual edits in `report_plan_state` are reflected in next response.
  - Plan card events are persisted.

## How to Approach Implementation

Recommended order:

1. **Start with the data model**: define the plan state JSON structure in the orchestrator. The schema is in `REPORT_PLAN_CARD_V1.md` under "Data Model: Report Plan State".

2. **Orchestrator changes**: modify `workspace_v2.py` to:
   - Create initial plan state on report intent detection.
   - Include `report_plan_card` in response `content_json`.
   - Accept `report_plan_state` and `report_plan_action` in respond input.
   - Handle "Start Now" by filling defaults and triggering generation.
   - Emit new event types.

3. **API layer**: update `web_server.py` to pass through the new fields.

4. **Frontend**: build the plan card renderer and interaction handlers in `index.html`.

5. **Tests**: add unit tests for the new behavior.

## Key Design Decisions Already Made

- **Batch edits**: manual edits via card controls update local state only. The accumulated changes are sent with the next message or "Start Now" click (no auto-send on every edit).
- **Read-only history**: only the most recent plan card in the chat has interactive controls. Older cards are read-only snapshots showing the plan evolution.
- **No confirmation on Start Now**: the card itself is the confirmation — the user sees the full plan before clicking.
- **Backward compatible**: the plan card wraps the existing report scaffolding logic. Users can still type section details in chat (existing conversational path). Both paths update the same underlying plan state.

## Existing Report Workflow Code

The current report scaffolding logic in `workspace_v2.py` handles:
- Report request detection
- Working DOCX artifact creation
- Primary section proposal/confirmation
- Subsection and recursive nested subsection expansion
- Instruction capture/defaulting
- Generation with gap-fill research
- Export

The plan card adds a structured visual layer on top of this. The same section/subsection/instruction data flows through — the card is an additional output format in `content_json` alongside the existing `content_text`.

## Questions?

If anything is unclear, the authoritative source is `docs/BIG_UPGRADE_PLAN/REPORT_PLAN_CARD_V1.md`. See the "Resolved Decisions (Locked 2026-03-03)" section for final behavior choices.
