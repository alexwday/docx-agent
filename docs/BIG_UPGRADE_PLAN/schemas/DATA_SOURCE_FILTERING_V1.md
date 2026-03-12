# Data Source Filtering V1 (UI-Driven)

## Goal

The UI may optionally provide a data source filter list per request:

1. If no filter list is provided, agent sees all enabled entries in `data_source_catalog`.
2. If a filter list is provided, agent sees only those allowed sources.
3. The agent then chooses which sources to use from that effective set.
4. Effective source context is injected into the orchestrator system prompt.

## Request Behavior

`POST /api/sessions/{session_id}/respond` request payload should support:

1. `message` (optional string): user message for this turn.
2. `data_source_filters` (optional array of `source_id` values).

Rules:

1. `data_source_filters` missing or empty means unfiltered mode.
2. Non-empty filters mean filtered mode; only matching + enabled sources are included.
3. Unknown `source_id` values are ignored and logged in an event payload.
4. If filters are provided and no sources remain after validation, return a structured `INVALID_ARGUMENT` error.

## Prompt Injection Contract

The orchestrator prompt builder should include one clearly labeled section:

1. `AVAILABLE_DATA_SOURCES` with only the effective (post-filter) source list.
2. Include `source_id`, `name`, `source_type`, and key schema summary per source.
3. Never inject sources outside the effective list.
4. Include `DATA_SOURCE_FILTER_MODE` (`filtered` or `unfiltered`) for transparent behavior.

## Agent Selection Contract

Filtering and selection are separate concerns:

1. UI filter controls visibility scope.
2. Agent source selection controls which visible sources are actually queried.
3. Agent must not call tools for sources outside the effective filter scope.
4. Selected sources should be logged for replay/debug.

## Storage and Auditing

Filters are not stored as a separate table in v1.

Instead, record filter usage in `message_events`:

1. `event_type`: `ui_data_source_filter_applied`
2. `payload` should include:
   - `requested_source_ids`
   - `effective_source_ids`
   - `ignored_source_ids`
   - `mode` (`filtered` or `unfiltered`)

Also record selected sources in:

1. `event_type`: `agent_data_source_selected`
2. `payload` should include:
   - `selected_source_ids`
   - `selection_reasoning_summary`
   - `selection_inputs` (user query + session context references)

This keeps per-turn provenance and avoids duplicating source state.

## Example Effective Filter Logic

1. Query `data_source_catalog where enabled = true`.
2. If request has no filters: effective set = all enabled.
3. If request has filters: effective set = enabled rows where `source_id` in filter list.
4. Inject only effective set into system prompt.
5. Agent chooses one or more sources from effective set and triggers source-specific tool calls.
