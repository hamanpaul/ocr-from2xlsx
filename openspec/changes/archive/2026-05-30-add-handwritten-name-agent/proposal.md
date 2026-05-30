# Proposal: Handwritten name recognition via optional VLM agent + correction-learning loop

**Change ID:** `add-handwritten-name-agent`
**Created:** 2026-05-30
**Status:** Archived

---

## Problem Statement

The pipeline now recognizes `service_date`, `identity`, `gender`, and `medical_record_no` from the
service-record form, but the **handwritten name** — the most safety-critical field — remained unsolved.
On the reference form `tests/fixtures/pdf/for testing only.pdf` the name (confirmed by the user as「葉心安」)
is cursive running-script Chinese overlapping printed gridlines. A wrong name means the wrong patient, so
any machine-produced name must remain subject to human confirmation.

## Archived Outcome

This change was implemented as:

- an offline plugin crop that isolates the handwritten-name line while excluding the medical-record-no line;
- an optional handwritten-name suggestion pass in `prepare-records`, using only the minimized crop;
- a strict `name.unconfirmed` review gate so direct import cannot write unconfirmed names;
- a local JSONL correction store and roster reuse loop so confirmed names improve future runs.

The accepted behavior is captured in the base `openspec/specs/record-preparation/spec.md`.
