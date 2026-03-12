# Coding Standards

## General

1. Keep API response shapes stable under `contract_version = "v1"`.
2. Use explicit error codes from `word_engine.errors.ErrorCode`.
3. Keep filesystem operations path-validated and lock-protected.

## Naming

1. Tool names use snake_case and match API contract.
2. Internal helpers use `_` prefix and are not exported.

## Logging

1. Log one success or failure event per operation.
2. Include `event`, `file_path`, `status`, and `duration_ms`.
3. Include `error_code` on failures.

## Tests

1. Add unit coverage for all new public APIs.
2. Add e2e coverage for workflow changes.
3. Prefer generated fixtures under `tmp_path`; keep long-lived fixtures in `tests/fixtures`.
