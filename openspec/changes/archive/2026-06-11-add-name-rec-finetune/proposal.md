# add-name-rec-finetune

Add a repeatable handwritten Chinese name recognition training engine: fine-tune PP-OCRv5_mobile_rec
on synthetic handwritten-name crops via the official PaddleOCR training pipeline (CPU-only), gate the
candidate on a fixed holdout (exact-match up, char accuracy not worse), deploy atomically as a second
name-only rec model resolved by the plugin (env -> user runtime dir -> bundle -> absent keeps current
behavior), and harvest confirmed `name_corrections.jsonl` entries back into the training corpus.

Design: `docs/superpowers/specs/2026-06-11-name-rec-finetune-design.md`.
