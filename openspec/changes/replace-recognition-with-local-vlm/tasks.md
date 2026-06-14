# Implementation Tasks: Replace OCR/geometry recognition with a fully-local Vision-LLM pre-fill

**Change ID:** `replace-recognition-with-local-vlm`

All code uses TDD (test first, watch it fail, implement, watch it pass, commit). Pure logic runs in
the main `.venv`; real-VLM checks run against a locally served model and are optional-marker gated.
Per paulsha-conventions: every code commit syncs `CHANGELOG.md [Unreleased]`.

## Status (2026-06-14)

Phases 0–4 **landed** (pure core, backend, real Ollama client + tiler, CLI `--ocr-backend vision`,
review-form low-confidence flags). Phase 0 measured on `qwen3-vl:2b`: after six fixes (band
alignment, terse prompts, option chunking, temperature=0, lenient parsing, greyscale crops) it
pre-fills **~8/10 fields single-pass** (incl. handwritten MRN). Decision: **2B + human correction**,
opt-in (default backend unchanged). **Remaining / follow-up:** dense `cancers` grid needs narrower
sub-tiles; `service_date`/`source` occasionally missed; handwriting (date) deferred to human;
Phase 5 portable llama.cpp packaging not started (uses local Ollama for now); Phase 6 ground-truth
fixture/test pending; Phase 7 keeps the old plugin as default (vision is opt-in). **Not archived** —
change remains in progress.

---

## Phase 0: De-risk — model + runtime bake-off (manual, on user hardware)

- [ ] 0.1 Stand up a local `llama-server` (llama.cpp) and confirm the **vision path** works for each candidate model on the user's machine.
- [ ] 0.2 Bake-off candidates {Qwen 3.5 VL 2B (default), 4B, Gemma 4 E2B, 7B} on real samples (`output/reg/filled_cam` etc.): record per-section pre-fill accuracy + per-image latency.
- [ ] 0.3 Build a small real-capture ground-truth set via the review UI / `correction_store`.
- [ ] 0.4 Decide model default, section-band coordinates, and prompt template; record the "work-saved" verdict.

**Quality Gate:**
- [ ] Chosen model's vision path verified in the portable runtime
- [ ] Phase 0 report committed (accuracy / latency / decision)

---

## Phase 1: Tile + schema mapping core (pure, model-free)

- [ ] 1.1 Failing tests: split an upright image into the configured proportional section bands; assert band rectangles for the reference layout.
- [ ] 1.2 Failing tests: map a per-tile VLM JSON (option→marked/unmarked, handwritten date/number values) into `service_record.v1` fields; cover identity/gender/cancers/services/patient_fields.
- [ ] 1.3 Implement the pure tiler + schema mapper (no model, no image-decode in the pure core where avoidable).

**Quality Gate:**
- [ ] `.venv` pytest passes for the new pure modules
- [ ] No regression in the full suite

---

## Phase 2: Confidence flags + name/MRN + roster snap (pure)

- [ ] 2.1 Failing tests: derive low-confidence/unfilled flags (empty, roster-miss, abnormal digit length) per field.
- [ ] 2.2 Failing tests: parse name (CJK run) + medical-record-no (digit run) from the name-MRN tile JSON; snap name to the local roster; keep `name.unconfirmed`.
- [ ] 2.3 Implement; reuse `name_roster`/`name_suggestion`; preserve the unconfirmed-until-human flow.

**Quality Gate:**
- [ ] `.venv` pytest passes

---

## Phase 3: vision_backend composition + injectable VLM client

- [ ] 3.1 Failing test for `vision_backend.run(request, vlm_fn)` with a fake `vlm_fn` returning reference tile JSON: the record is a full `service_record.v1` with the reference fields populated and confidence flags set.
- [ ] 3.2 Implement `vision_backend` (compose tiler → vlm_fn per tile → merge → map → flags) behind the existing replaceable-backend interface; same normalized `Batch`/`Record` contract.
- [ ] 3.3 Implement the real `vlm_fn`: HTTP client to local `llama-server` (model/port/path from config + env), graceful no-op fallback when the server/model is absent.

**Quality Gate:**
- [ ] `.venv` pytest passes (fake-driven, no model)
- [ ] Backend substitution keeps the downstream contract (existing backend-substitution scenario stays green)

---

## Phase 4: Review UI — low-confidence flagging

- [ ] 4.1 Failing test: `confirm_form` marks low-confidence/unfilled fields visibly distinct.
- [ ] 4.2 Implement minimal UI flagging; corrections still flow to `correction_store`.

**Quality Gate:**
- [ ] `.venv` pytest passes; existing review/confirm tests green

---

## Phase 5: Portable packaging (runtime + weights, not in git)

- [ ] 5.1 `build/` script: fetch `llama-server` (Vulkan) + default GGUF + mmproj into `dist/`; weights gitignored.
- [ ] 5.2 App launches/locates the local server (resolution order: env → user runtime → bundle), mirroring the mark/name-model resolution pattern.
- [ ] 5.3 `python build/package.py` produces a runnable bundle; document size + setup.

**Quality Gate:**
- [ ] Bundle runs end-to-end on the reference image; weights absent from git

---

## Phase 6: Ground-truth regression + real-VLM verification

- [ ] 6.1 Add a real-capture ground-truth fixture for the reference form (full fields).
- [ ] 6.2 Optional-marker real-VLM test asserting the backend's output for the reference form matches the ground truth (skipped in default CI).
- [ ] 6.3 Manually run the full chain on the reference form; confirm each field against the image; record results.

**Quality Gate:**
- [ ] Pure/CI tests pass; manual real-VLM verification matches the image field-by-field

---

## Phase 7: Retire old recognition + docs/policy

- [ ] 7.1 Unwire PaddleOCR field-extract/mark/geometry from the recognition path (keep archived or remove per review); mark `fix-core-field-recognition` superseded.
- [ ] 7.2 Update `CHANGELOG.md [Unreleased]`.
- [ ] 7.3 Update README recognition section + the parked registration spec pointer.
- [ ] 7.4 `python -W error -m pytest -q`, `python build/package.py`, and `python -m policy_check --repo .` pass.

**Quality Gate:**
- [ ] All tests pass, policy check clean, docs synced

---

## Completion Checklist

- [ ] All phases complete and quality gates passed
- [ ] Reference form pre-filled correctly field-by-field (verified against image)
- [ ] Ready for `requesting-code-review` then `openspec-archive`
