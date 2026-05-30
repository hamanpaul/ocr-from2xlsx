# Implementation Tasks: Handwritten name recognition

**Change ID:** `add-handwritten-name-agent`

All code uses TDD. Pure logic is tested with the main `.venv`; real cloud-VLM calls are a manual spike only.

---

## Phase 1: Confirmed-name roster + fuzzy match (pure)

- [ ] 1.1 Failing tests: `roster_match(candidate, roster, threshold)` returns the closest roster name when similarity ≥ threshold, else None; boundary and empty-roster cases.
- [ ] 1.2 Implement a pure stdlib (`difflib`) roster matcher in `src/ocr_from2xlsx/name_roster.py`.

**Quality Gate:** `.venv` pytest passes; pure stdlib only.

---

## Phase 2: Correction store (pure IO)

- [ ] 2.1 Failing tests: append a correction record (field, crop_path, ocr_raw, agent_suggestion, roster_suggestion, final_value, record_id, source, timestamp) to a JSONL store and read it back; roster derivable from the store's confirmed names.
- [ ] 2.2 Implement `src/ocr_from2xlsx/correction_store.py` (append-only JSONL; load distinct confirmed names for the roster).

**Quality Gate:** `.venv` pytest passes.

---

## Phase 3: Name agent interface + config (graceful-optional)

- [ ] 3.1 Failing tests: a `NameAgent` protocol with a fake implementation returns a suggestion from a crop path; a config loader reads `name_agent.yaml` (enabled/provider/model/endpoint/prompt) and returns a disabled/no-op agent when the file is missing or `enabled: false`.
- [ ] 3.2 Implement `src/ocr_from2xlsx/name_agent.py`: the protocol, a `NullNameAgent` (no-op), config loading, and a factory that returns the configured agent or the null agent. The cloud VLM implementation is wired but its network call is exercised only by the manual spike.

**Quality Gate:** `.venv` pytest passes; no network in CI.

---

## Phase 4: Name-crop extraction (offline plugin)

- [ ] 4.1 Failing tests: a pure geometry function computes the name-crop box from the 姓名/病歷號 anchor line bbox, EXCLUDING the medical-record-no digit line and the diagnosis-date line (verify the box bounds with synthetic line boxes).
- [ ] 4.2 Implement crop-geometry in the plugin and emit the cropped image + record its path in the record metadata (image I/O in the plugin wrapper; geometry pure).

**Quality Gate:** `.venv` pytest passes for the pure geometry; plugin wrapper exercised manually.

---

## Phase 5: Integration — suggestion + unconfirmed flag + learning write-back

- [ ] 5.1 Failing tests: given a record with an empty name and a name crop, the integration produces `record.name` from (roster match → else agent suggestion) and adds warning `name.unconfirmed`; with no agent and empty roster, the name stays empty, `name.unconfirmed` is set, and nothing errors.
- [ ] 5.2 Failing tests: on human confirmation/correction, a correction is appended to the store and the roster gains the confirmed name.
- [ ] 5.3 Implement the integration in the main app, using injected agent + roster + store so it is testable with fakes; preserve default behavior when the agent is absent.

**Quality Gate:** `.venv` pytest passes (fake-driven, no cloud).

---

## Phase 6: Weakest-tier evaluation (manual spike)

- [ ] 6.1 Send the real name crop to candidate cloud-VLM tiers (start with the configured Claude tier) and record which read「葉心安」; pick a sensible default tier and document it. Do NOT add a CI-gating real-call test.

**Quality Gate:** result recorded; default tier chosen.

---

## Phase 7: Docs, policy, integration

- [ ] 7.1 Update `README.md` (name agent config, PII note, human-confirm requirement) and `CHANGELOG.md [Unreleased]`.
- [ ] 7.2 `python -W error -m pytest -q`, `python build/package.py`, `python -m policy_check --repo .` all pass.

**Quality Gate:** all tests pass, policy clean, docs synced.

---

## Completion Checklist

- [ ] All phases complete and quality gates passed
- [ ] Name never written without human confirmation; agent absence does not affect the pipeline
- [ ] Correction store + roster fuzzy-match loop working (CI-tested with fakes)
- [ ] Ready for `requesting-code-review` then `openspec-archive`
