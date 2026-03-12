# Release Checklist (v1 stabilization)

Related docs:
1. [Roadmap](ROADMAP.md)
2. [Phase Plan](PHASES.md)
3. [Execution Status](STATUS.md)
4. [API Contract](API_CONTRACT.md)

## Pre-Release Gates

1. Test and CI:
   - [ ] Local `pytest -q` is green.
   - [ ] GitHub Actions CI (`.github/workflows/ci.yml`) is green for all jobs.
2. Contract stability:
   - [ ] No breaking changes to v1 tool signatures.
   - [ ] Error code set remains consistent with `API_CONTRACT.md`.
3. Docs:
   - [ ] `STATUS.md` updated with latest verified test result.
   - [ ] `PHASES.md` reflects latest phase status and evidence.
   - [ ] `CHANGELOG.md` includes release notes.

## Packaging and Runtime

1. Python package:
   - [ ] `pyproject.toml` version updated.
   - [ ] Optional dependencies (`dev`, `mcp`) install cleanly.
2. MCP runtime:
   - [ ] `word-mcp-server` entry point starts when `fastmcp` is installed.
   - [ ] Missing-`fastmcp` guidance test passes.

## Release Steps

1. Tagging:
   - [ ] Create release commit with changelog and docs updates.
   - [ ] Create semver tag (`vX.Y.Z`).
2. Post-release:
   - [ ] Update `STATUS.md` to next milestone focus.
   - [ ] Carry forward unresolved risk items with owner and next action date.
