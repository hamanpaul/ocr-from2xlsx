"""Local Vision-LLM assisted recognition: layout, tile mapping, confidence, backend.

Pure logic here is model-free and unit-tested; the VLM call is injected as a
``vlm_fn`` so the backend composes without a running model.
"""
