# Workflow Alignment V1

## Purpose

This document validates that the planned schema aligns with the intended end-to-end product behavior.

## 1) Login and Session Resume

User behavior:

1. User logs into UI with 9-digit employee id.
2. UI loads all sessions for that user.
3. User selects a session to continue.
4. UI loads message history and related documents.

Planned data mapping:

1. Read `sessions` by `user_id`.
2. Read `session_messages` by `session_id` ordered by `sequence_no`.
3. Read `session_artifacts` by `session_id`, grouped by `artifact_type`.
4. Preview opens by resolving `session_artifacts.storage_uri`.

## 2) Session Document Panes in UI

UI sections:

1. Uploaded documents
2. Research outputs
3. Report documents

Artifact type mapping:

1. Uploaded documents: `upload`
2. Research outputs: `research_markdown`, `research_output_doc`
3. Report documents: `report_working_doc`, `report_final_doc`, `export_file`

## 3) Research Interaction Mode

User behavior:

1. User asks a query.
2. Agent researches internal data sources and uploaded files.
3. Agent returns answer + creates research outputs.

Planned process:

1. Create `session_messages` row for user message.
2. Build orchestration context from:
   - conversation history (`session_messages`)
   - available data sources (`data_source_catalog`, optionally filtered)
   - uploaded docs and derived knowledge (`session_artifacts`, `artifact_knowledge_units`)
   - prior orchestration events (`message_events`)
3. Agent selects source-specific tools from available set.
4. Tool calls perform extraction/retrieval and create outputs:
   - markdown output for agent ingestion (`research_markdown`)
   - user-facing file output (`research_output_doc` in `docx/pdf/xlsx`)
5. Persist assistant response message.
6. Persist detailed events in `message_events` for replay/debug.

## 4) Uploaded Document Intelligence

User behavior:

1. User uploads documents.
2. Agent can use those documents for future research and reports.

Planned process:

1. Store source file as `session_artifacts` with `artifact_type='upload'`.
2. Run ingestion pipeline to create `artifact_knowledge_units`:
   - one or more summaries (`unit_type='summary'`)
   - retrievable chunks (`unit_type='chunk'`)
   - optional table extracts (`unit_type='table_extract'`)
3. Agent dynamically decides whether uploaded content is relevant for each turn.

## 5) Report Creation Mode (Interactive Plan Card)

User behavior:

1. User asks to create a report (simple: "create a report about X", or detailed: "create a report with these specific sections...").
2. Agent responds with an inline **report plan card** in the chat — an interactive HTML widget showing the evolving report structure.
3. The plan card displays: report title, summary, section tree, per-section instructions, and a "Start Now" button.
4. User can interact in two ways:
   - **Conversational**: type details/preferences in chat; agent updates the plan card each turn.
   - **Direct editing**: use card controls to add sections, add subsections, edit instructions, remove sections, or edit the title.
5. At any point, user can click **"Start Now"** to trigger generation. The agent fills in default instructions for any sections that lack them, performs gap-fill research, and generates the report.
6. If the user prefers a detailed flow, they continue the conversation and/or use card controls until all sections and instructions are defined, then click "Start Now" or tell the agent to proceed.

Plan card lifecycle:

1. **Initial card**: agent detects report intent, creates plan card with title, summary, and suggested primary sections. Status: `scaffolding`.
2. **Iterative updates**: each assistant response includes an updated plan card reflecting conversational and manual edits.
3. **Ready state**: all sections have instructions (user-provided or agent-defaulted). User clicks "Start Now" or confirms via chat.
4. **Generation**: agent runs gap-fill research and content generation. Card status: `generating`.
5. **Completed**: final content replaces instruction placeholders. Card status: `completed`.

Manual edit controls in the plan card:

1. "Add Section" — add a primary section.
2. "Add Subsection" — add a child under any section.
3. "Edit Instructions" — set or update per-section instructions.
4. "Remove" — remove a section and its children.
5. "Edit Title" — inline edit of report title.

When the user makes manual edits:

1. Frontend updates local plan state and includes it in the next `/respond` request as `report_plan_state`.
2. Orchestrator receives a context note: "The report plan was recently updated by the user."
3. Agent reviews changes, acknowledges them, and returns an updated plan card.

Planned data flow:

1. Create `report_working_doc` artifact (blank template seed).
2. Plan state is carried in `content_json.report_plan_card` of assistant messages and persisted via `report_plan_state_updated` events.
3. Each structural change is written to the working doc and logged via `message_events`.
4. Instruction capture per section/subsection is persisted in:
   - plan card state (in `content_json`)
   - working doc content
   - event payloads for traceability
5. "Start Now" signal triggers finalization: default instructions for pending sections, gap-fill research, then report generation tool call.
6. Tool call may produce additional `research_markdown` and `research_output_doc` artifacts for gaps.
7. Tool call updates/replaces report content in working doc.
8. Finalized output stored as:
   - updated `report_working_doc` (latest in-progress/final working state)
   - optional `report_final_doc`
   - optional exports in `export_file` (`pdf/docx/xlsx`).

See [`REPORT_PLAN_CARD_V1.md`](./REPORT_PLAN_CARD_V1.md) for full design specification.

## 6) Event Logging Requirements

Minimum events to persist per assistant turn:

1. prompt/context assembly events
2. source filter application event
3. source selection event
4. tool request and response events
5. report-structure and instruction-capture events
6. artifact creation/update events
7. error event (if applicable)

This keeps the system stateless at model runtime while preserving full session history and replay context.

## 7) Resolved V1 Decisions (Locked 2026-03-03)

1. Report generation executes synchronously in the current baseline; async/background execution remains a future enhancement.
2. Artifact bytes are filesystem-backed in the baseline, referenced by `storage_uri`; object storage remains a future enhancement.
3. Sessions are single-owner in V1 baseline scope.
4. Prompt windowing uses bounded recency with a character budget plus structured system-context injection.
