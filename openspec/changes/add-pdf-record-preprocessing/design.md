## Context

The repository already has a safe downstream pipeline: normalized JSON can be validated, reviewed, and written into the Excel workbook without breaking workbook formatting. It now also has a `PdfDocumentSource` that proves the supplied `for testing only.pdf` can be treated as a stable document input fixture.

What is missing is the upstream half of the flow. There is no formal path yet for taking a fixed-layout PDF or image, preprocessing it, extracting fields, and producing the final normalized `Batch`/`Record` JSON that existing commands already understand. The project must stay Windows-first, portable, offline-friendly, and conservative about workbook safety.

## Goals / Non-Goals

**Goals:**
- Add a single upstream preparation boundary that turns one PDF page or image into one normalized record.
- Keep `Batch`/`Record` JSON as the final data contract consumed by `validate-json` and `import-json`.
- Preserve PDF/image provenance and OCR metadata in the normalized output for debugging and review.
- Make the OCR backend replaceable while selecting one local/offline-friendly default candidate for first integration.
- Establish a manually curated gold JSON fixture for `for testing only.pdf` so preprocessing and normalization can be regression-tested before OCR is trusted.

**Non-Goals:**
- Building a custom OCR engine from scratch.
- Replacing the existing workbook import, validation, or review workflow.
- Supporting arbitrary document layouts in the first iteration; this design assumes a fixed service-record form template.
- Solving multi-record pages or multi-page stitched records in the first iteration.

## Decisions

1. **Keep normalized `Batch`/`Record` JSON as the only final contract.**  
   This avoids creating a second "almost final" format that downstream code would need to understand. The alternative was a new intermediate extraction schema, but that would add translation layers before `json_io`, `validate-json`, and `import-json` for little benefit in this first fixed-layout workflow.

2. **Introduce a dedicated `prepare-records` front-end flow ahead of `validate-json` and `import-json`.**  
   The preparation stage owns document ingestion, preprocessing, OCR invocation, field extraction, and normalization. The alternative was extending `import-json` to also accept PDF/image input, but that would blur responsibilities and make workbook safety harder to reason about.

3. **Use a fixed-layout template map plus a pluggable OCR backend interface.**  
   The service-record form has a stable layout, so page preprocessing and field-zone extraction should be driven by a template definition rather than ad-hoc OCR parsing. The default backend candidate should be a local, offline-friendly Windows option such as a RapidOCR/ONNXRuntime-style backend; the alternative of binding directly to one OCR engine was rejected because it would entangle packaging, OCR, and normalization decisions too early.

4. **Expand normalized output with provenance and OCR metadata, not a separate debug artifact by default.**  
   `source` should capture input kind, document path, page number, template ID, and optional preprocessed image path. `ocr` should capture backend identity, confidence, warnings, raw text, and optional per-field confidence/debug data. The alternative of storing all OCR traces outside the normalized output was rejected because it weakens traceability during review and troubleshooting.

5. **Treat one page as one record for this capability.**  
   The supplied PDF fixture and the target paper workflow both align to a one-form-per-page model. Supporting page splitting or multi-page aggregation would add complexity before the base OCR-to-record path is proven.

6. **Make the provided PDF fixture the canonical regression document for this capability.**  
   The repository should keep the original PDF, a manually curated normalized gold JSON file, and an optional OCR debug fixture. The alternative of testing only synthetic JSON was rejected because it would not exercise the real document boundary the user cares about.

## Risks / Trade-offs

- **[OCR accuracy may be too weak on handwritten content] ->** Keep the backend replaceable, preserve gold fixtures, and treat OCR output as provisional until normalized output matches the approved reference cases.
- **[Portable Windows packaging may become heavier] ->** Prefer local/offline backends with simple redistribution stories and isolate OCR dependencies behind the preparation command.
- **[Form layout drift could break field zoning] ->** Version the template ID and keep template-based coordinates/configuration separate from normalization logic.
- **[Normalized schema growth could destabilize downstream code] ->** Limit additions to optional `source`/`ocr` metadata while preserving existing required workbook-facing fields.

## Migration Plan

1. Add OpenSpec artifacts for the new `record-preparation` capability.
2. Implement the front-end preparation flow and fixture-driven tests without changing workbook writer behavior.
3. Add the gold JSON fixture for the supplied PDF and connect it to CLI, normalizer, and end-to-end import tests.
4. Benchmark the default OCR backend candidate on real captures and switch backends only if the interface contract stays unchanged.

## Open Questions

- The default backend candidate is intentionally selected by characteristics (local, offline, Windows portable) rather than locked to a single package name until real document accuracy is benchmarked.
- If future paper forms deviate from the current fixed layout, a follow-up capability may be needed for template selection or calibration.
