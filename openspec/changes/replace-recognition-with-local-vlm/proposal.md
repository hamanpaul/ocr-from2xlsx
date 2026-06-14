# Proposal: Replace OCR/geometry recognition with a fully-local Vision-LLM pre-fill

**Change ID:** `replace-recognition-with-local-vlm`
**Created:** 2026-06-14
**Status:** Draft
**Design:** `docs/superpowers/specs/2026-06-14-offline-vlm-assisted-recognition-design.md`
**Supersedes:** `fix-core-field-recognition` (text-anchor + ink-probe hybrid)

---

## Problem Statement

On real document-camera captures (IPEVO DO-CAM, fixed mount, 8MP, lit), the existing
recognition pipeline is wrong/empty: only `service_date` is filled, and every checkbox-driven
field (identity / gender / cancers / services / age / disease status…) plus handwritten
dates/numbers is missed. All three offline approaches tried have failed:

- **PaddleOCR text layer + `field_extract`** — never reads the service-evaluation checkboxes; identity/gender rely on unstable OCR text anomalies.
- **Geometry registration + `template_boxes` ink-probe** — abandoned; 6px boxes need <1% warp error, unreachable on real photos (lens distortion + paper curl + corner error).
- **OCR text-leakage heuristic** — too noisy; row labels misparse as options.

The downstream is already complete: `domain.py` models the full `service_record.v1` and
`workbook.py` already writes the entire form (patient_fields + services) to Excel. The only
missing piece is recognition that actually fills those fields.

Affected: anyone scanning the cancer-resource-center service form via webcam/image into Excel.

## Proposed Solution

Replace the OCR/geometry/heuristic recognition layer with a **fully-local Vision-LLM (VLM)
pre-fill**, verified by a human in the existing review UI:

- A new `vision_backend` runs a local VLM (default **Qwen 3.5 VL 2B**, config-upgradable to 4B/7B)
  via a portable **llama.cpp** runtime, reading **wide proportional section tiles** with each
  tile's **known option list** and returning marked/unmarked + handwritten dates/numbers as JSON.
- The backend fills the **full** `service_record.v1`; name and medical-record-no are read locally
  (same model, name snapped to the existing roster). Fully offline → no cloud, no privacy boundary.
- Low-confidence / unfilled fields are flagged so the human verifies quickly in `confirm_form`.
  The final Excel ≥95% is guaranteed by the human-confirm step; the VLM reduces manual work.

The VLM runtime + GGUF weights are **not committed to git**; a `build/` script fetches them into
`dist/` (same portable-plugin pattern as PaddleOCR). The cloud option is left only as an interface
seam for the future.

## Scope

### In Scope
- `vision_backend`: local VLM pre-fill filling the full `service_record.v1` (checkboxes, handwritten dates/numbers, name, medical-record-no), behind the existing replaceable-backend interface.
- Wide proportional section tiling + schema-guided per-tile prompts (no 6px geometry).
- Confidence/low-confidence flagging surfaced to the existing review UI.
- Portable build script fetching runtime + GGUF into `dist/` (weights not in git).
- Phase 0 empirical bake-off (model + runtime vision-support) on real samples/hardware.
- Retire the OCR/geometry/heuristic recognition wiring; supersede `fix-core-field-recognition`.

### Out of Scope
- Cloud recognition backend (only the interface seam is kept).
- Model retraining or VLM fine-tuning (v1 uses prompts + known option lists).
- Changes to `workbook.py` write logic or `service_record.v1` field semantics (already complete; only the consultation-count mapping is verified during implementation).
- Auto-shutter / live guidance / multi-page stitching / super-resolution.

## Impact Analysis

| Component | Change Required | Details |
|-----------|-----------------|---------|
| Recognition backend (`src/`) | Yes | New `vision_backend` + local VLM client (HTTP to `llama-server`); injectable VLM call for tests. |
| OCR plugin (`plugins/paddleocr/`) | Yes (unwire) | Field-extract/mark/geometry no longer the recognition path; code may stay archived. |
| Pure logic / tests | Yes | New pure functions (tile merge, schema mapping, roster snap, confidence flags) unit-tested without a model. |
| Review UI (`confirm_form`) | Yes (small) | Flag low-confidence/unfilled fields. |
| `service_record.v1` / `domain.py` | No | Already models the full form. |
| `workbook.py` writer | No (verify counts) | Already writes the full form; verify consultation-count mapping. |
| Build / packaging (`build/`, `dist/`) | Yes | Portable runtime + GGUF fetch; weights not in git. |

## Architecture Considerations

Fits the existing "replaceable OCR backend behind a stable preparation interface" requirement: the
VLM backend emits the same normalized `Batch`/`Record` shape, so validation/import/workbook are
unchanged. Pure, CI-testable logic stays free of the model; the VLM HTTP call is injectable and
fakeable (mirrors the existing `ocr_fn`/`mark_fn` injection). Section tiling is config-driven
(proportional bands tuned once for the fixed camera), tolerant by design with the human-verify
backstop.

## Success Criteria

- [ ] `vision_backend` pre-fills the full `service_record.v1` for the reference form (checkboxes, dates, numbers, name, medical-record-no), each verifiable against the image.
- [ ] Pure logic (tile merge, schema mapping, roster snap, confidence flags) has model-free unit tests that pass.
- [ ] Review UI flags low-confidence/unfilled fields; human can correct and write to Excel.
- [ ] Phase 0 report: chosen model, per-section accuracy, per-image latency, "work saved" verdict.
- [ ] Portable build produces `dist/` with runtime + weights; weights absent from git.
- [ ] Existing tests + `policy_check` green; CHANGELOG / openspec / README synced.

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| 2B pre-fill accuracy insufficient (CheckboxQA: 3B=43.6 vs 7B=71.9 — size-sensitive) | Med-High | Med | Human verify is the ≥95% guarantee; one-line config bump to 4B/7B; Phase 0 measures the "work-saved" threshold. |
| Chosen model's vision path unsupported in portable llama.cpp | Med | High | Phase 0 verifies before bundling; fallback runtime or alternate model. |
| Fixed-camera framing drift → mis-tiled section | Med | Low | Wide proportional bands + human verify; not 6px precision. |
| Low-end hardware: minutes per image | High | Low | Seasonal batch can queue/run overnight; 2B is the lightest option. |
| Portable package multi-GB | Med | Low | One-time offline deploy; weights not in git. |
