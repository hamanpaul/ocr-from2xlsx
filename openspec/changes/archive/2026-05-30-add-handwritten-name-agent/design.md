# Handwritten name recognition design

**Date:** 2026-05-30
**Status:** Implemented and archived

---

## Final design summary

The handwritten-name path is intentionally **assistive, never autonomous**:

1. The PaddleOCR plugin emits a privacy-minimized crop of the handwritten-name line.
2. `prepare-records` may run an optional handwritten-name suggestion pass when `--name-agent-config` is supplied.
3. The pass first reuses locally confirmed names from `name_corrections.jsonl`, then falls back to the configured cloud name agent when enabled.
4. Any machine-produced or roster-recommended name is marked `name.unconfirmed`.
5. `import-json` blocks records that still carry `name.unconfirmed`.
6. The review app is the human-confirmation path: confirming a record clears the warning and appends a correction entry back to the local JSONL store for future roster reuse.

## Notes

- The agent is strictly optional; absent, disabled, unreachable, or crop-missing cases are safe no-ops.
- Only the privacy-minimized handwritten-name crop is sent to the cloud agent.
- The learning loop is local-first: confirmed names accumulate in a JSONL correction store and are loaded back as a roster on future `prepare-records` runs.
