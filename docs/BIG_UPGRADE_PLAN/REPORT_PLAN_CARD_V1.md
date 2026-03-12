# Report Plan Card V1

## Purpose

Define the interactive report plan card: an inline HTML widget rendered within assistant chat messages during report scaffolding. The card gives users a visual, editable representation of the evolving report plan and a "Start Now" shortcut to begin generation at any point.

## Problem Statement

The current report scaffolding flow is purely conversational. The agent asks clarifying questions about sections, subsections, and instructions one step at a time. This works but has UX friction:

1. Users cannot see the full report plan at a glance during the conversation.
2. Users who want a quick report must step through every confirmation prompt.
3. Users cannot directly add or edit sections without typing structured text commands.
4. The agent has no signal that the user made manual edits outside of the chat message.

## Design Overview

The report plan card is an HTML block embedded in the `content_json` of each assistant message during the report workflow. The frontend renders it inline in the chat bubble as a structured, interactive widget.

### Card Contents

1. **Report title** (editable inline).
2. **Report summary/description** from user's original request.
3. **Section tree** showing the full nested hierarchy:
   - Primary sections.
   - Subsections (recursively nested).
   - Per-section instructions (collapsed by default, expandable).
4. **Status indicators** per section: `pending`, `has_instructions`, `generated`.
5. **Action buttons**:
   - "Start Now" — triggers generation with agent defaults for any missing details.
   - "Add Section" — opens inline input to add a primary section.
   - "Add Subsection" — appears next to each section to add a child.
   - "Edit Instructions" — opens inline input to set/update section instructions.
   - "Remove" — removes a section/subsection from the plan.

### Card Lifecycle

1. **Initial card** — created when the agent detects a report request. Shows title, summary, and agent-suggested primary sections.
2. **Iterative updates** — each assistant response during scaffolding includes an updated card reflecting:
   - Sections/subsections confirmed or added.
   - Instructions captured or defaulted.
   - Any manual edits made by the user via card controls.
3. **Final card** — the last card before generation shows the locked structure with all instructions. Once generation starts, the card state transitions to `generating`.
4. **Post-generation card** — optionally shows the completed structure with `generated` status on all sections.

## Data Model: Report Plan State

The report plan state is a JSON structure that flows between frontend and backend. It is the single source of truth for the report structure during scaffolding.

```json
{
  "plan_id": "uuid",
  "title": "Q2 Supplier Risk Assessment",
  "summary": "Comprehensive report analyzing supplier risk across key categories",
  "status": "scaffolding",
  "sections": [
    {
      "section_id": "uuid",
      "title": "Executive Summary",
      "depth": 0,
      "instructions": "Provide a high-level overview of key risk findings",
      "instruction_source": "user",
      "status": "has_instructions",
      "subsections": [
        {
          "section_id": "uuid",
          "title": "Key Findings",
          "depth": 1,
          "instructions": null,
          "instruction_source": null,
          "status": "pending",
          "subsections": []
        }
      ]
    }
  ],
  "updated_by": "agent",
  "updated_at": "2026-03-03T10:00:00Z"
}
```

### Plan Status Values

1. `scaffolding` — structure is being built interactively.
2. `ready` — structure and instructions are finalized, awaiting generation trigger.
3. `generating` — report generation is in progress.
4. `completed` — generation finished, final content available.

### Section Status Values

1. `pending` — section exists but has no instructions.
2. `has_instructions` — section has instructions (user-provided or agent-defaulted).
3. `generated` — section content has been generated.

### Instruction Source Values

1. `user` — instruction was typed by the user (via chat or card controls).
2. `agent` — instruction was suggested by the agent as a default.
3. `null` — no instruction set yet.

## Frontend Behavior

### Rendering

1. When an assistant message has `content_json.report_plan_card`, the frontend renders the plan card widget inside the chat bubble, below the `content_text`.
2. The card uses the existing sidebar/surface color scheme for consistency.
3. Sections are displayed as a collapsible tree with indentation by depth.
4. The "Start Now" button is always visible and prominent at the bottom of the card.

### User Interactions via Card Controls

When the user interacts with card controls (add section, edit instructions, remove, etc.):

1. The frontend updates a local copy of the `report_plan_state`.
2. Sets `updated_by` to `"user"`.
3. The updated plan state is sent with the next `/respond` call in the request payload.
4. The frontend may optionally auto-send a `/respond` call on certain actions (e.g., "Start Now"), or batch edits until the user sends their next message.

### "Start Now" Button

When clicked:

1. Frontend sends a `/respond` request with:
   - `message`: `null` or empty (no user text needed).
   - `report_plan_state`: current plan state with `status` set to `"ready"`.
   - `report_plan_action`: `"start_now"`.
2. The orchestrator receives this signal, fills in default instructions for any sections that lack them, performs gap-fill research, and triggers report generation.

### Manual Edit Controls

1. **Add Section** — button at the bottom of the section list. Opens an inline text input. On submit, appends a new section to the plan with `status: "pending"`.
2. **Add Subsection** — icon/button next to each section. Opens an inline text input. On submit, appends a child subsection.
3. **Edit Instructions** — icon/button next to each section. Opens an inline textarea. On submit, sets `instructions` and `instruction_source: "user"`.
4. **Remove** — icon/button next to each section. Removes the section (and its children) from the local plan state.
5. **Edit Title** — click on the report title to make it editable inline.

All manual edits update the local plan state. The updated state is included in the next `/respond` request payload.

## API Contract Changes

### `POST /api/v2/sessions/{session_id}/respond` — Request Additions

```json
{
  "message": "Add a section on financial risk",
  "data_source_filters": [],
  "response_mode": "auto",
  "report_plan_state": { ... },
  "report_plan_action": "start_now"
}
```

New optional fields:

1. `report_plan_state` (object, optional) — the current plan state from the frontend. Included when the user has made manual edits via card controls, or when triggering "Start Now".
2. `report_plan_action` (string, optional) — explicit action signal. Values:
   - `"start_now"` — user clicked Start Now; agent should finalize and begin generation.
   - `null` / absent — normal conversational turn during scaffolding.

### `POST /api/v2/sessions/{session_id}/respond` — Response Additions

The assistant message `content_json` includes the plan card when in report workflow:

```json
{
  "status": "ok",
  "contract_version": "v2",
  "assistant_message": {
    "message_id": "uuid",
    "content_text": "I've added the Financial Risk section. Would you like to add subsections or instructions?",
    "content_json": {
      "report_plan_card": {
        "plan_id": "uuid",
        "title": "Q2 Supplier Risk Assessment",
        "summary": "...",
        "status": "scaffolding",
        "sections": [ ... ],
        "updated_by": "agent",
        "updated_at": "2026-03-03T10:05:00Z"
      }
    }
  }
}
```

## Orchestrator Behavior

### Detecting Report Requests

When the orchestrator detects a report creation intent (user says "create a report about X"):

1. Create the initial `report_plan_state` with:
   - Generated `plan_id`.
   - Title extracted from user request.
   - Summary from user request context.
   - Agent-suggested primary sections based on topic.
   - `status: "scaffolding"`.
   - `updated_by: "agent"`.
2. Include the plan card in `content_json.report_plan_card` of the assistant response.
3. Ask the user conversationally if they want to modify sections, add instructions, or start now.

### Processing User Edits from Card

When a `/respond` request includes `report_plan_state`:

1. Inject a context note into the orchestrator prompt: "The report plan was recently updated by the user. Review the updated plan before proceeding."
2. The orchestrator compares the incoming plan state with the last known state to identify changes.
3. The orchestrator acknowledges the changes in its response text and includes an updated plan card.

### Processing "Start Now"

When `report_plan_action` is `"start_now"`:

1. The orchestrator takes the current plan state.
2. For any section with `status: "pending"` (no instructions), the agent generates default instructions based on title, summary, and conversation context.
3. The plan status transitions to `"generating"`.
4. The orchestrator triggers the existing gap-fill research and report generation pipeline.
5. The response includes a plan card with `status: "generating"` or `"completed"`.

### Plan State Persistence

The report plan state is persisted via:

1. `message_events` with `event_type: "report_plan_state_updated"` — captures each version of the plan state as it evolves.
2. The `report_working_doc` artifact metadata can reference the `plan_id` for linkage.
3. On session hydrate, the latest plan state is reconstructable from the most recent `report_plan_card` in `content_json` of assistant messages.

## Event Types (New)

1. `report_plan_card_created` — initial plan card generated.
2. `report_plan_state_updated` — plan state changed (by user edit or agent update).
3. `report_plan_start_now_triggered` — user clicked Start Now.

These supplement the existing report workflow events (`report_structure_proposed`, `report_structure_confirmed`, etc.).

## Migration from Current Report Flow

The plan card does not replace the existing report scaffolding logic. It wraps it:

1. The same section/subsection/instruction data model is used internally.
2. The plan card is an additional structured output in `content_json` alongside the existing `content_text` conversational response.
3. The "Start Now" action maps to the existing "finalize and generate" trigger.
4. Manual edits via card controls are equivalent to the user typing structured section commands in chat.

The orchestrator should support both paths:
- Users who prefer to type section details in chat (existing flow).
- Users who prefer to use card controls for direct editing.

Both paths update the same underlying plan state.

## UI Wireframe (Conceptual)

```
+--------------------------------------------------+
|  REPORT PLAN                                      |
|  Title: Q2 Supplier Risk Assessment  [edit]       |
|  Summary: Comprehensive report analyzing...       |
|                                                   |
|  SECTIONS                                         |
|  +----------------------------------------------+ |
|  | 1. Executive Summary          [instructions]  | |
|  |    Status: has_instructions                   | |
|  |    + Add Subsection                           | |
|  |----------------------------------------------| |
|  | 2. Supplier Risk Analysis     [instructions]  | |
|  |    Status: pending                            | |
|  |    2.1 Financial Risk         [instructions]  | |
|  |        Status: pending                        | |
|  |    2.2 Operational Risk       [instructions]  | |
|  |        Status: pending                        | |
|  |    + Add Subsection                           | |
|  |----------------------------------------------| |
|  | 3. Recommendations            [instructions]  | |
|  |    Status: pending                            | |
|  |    + Add Subsection                           | |
|  +----------------------------------------------+ |
|                                                   |
|  [+ Add Section]                                  |
|                                                   |
|  [============ Start Now ============]            |
|                                                   |
+--------------------------------------------------+
```

## Resolved Decisions (Locked 2026-03-03)

1. Plan card manual edits are batched locally and sent on the next `/respond` request or explicit "Start Now" action (no auto-send per edit).
2. Historical cards are rendered as read-only snapshots; only the most recent plan card is interactive.
3. "Start Now" does not require an additional confirmation step.
