from ocr_from2xlsx.recognition.layout import Option, Section, ValueSpec
from ocr_from2xlsx.recognition.llama_client import (
    MAX_OPTIONS_PER_CALL,
    build_options_prompt,
    build_values_prompt,
    make_ollama_vlm_fn,
)

OPTION_SECTION = Section(
    "identity",
    (0.0, 0.0, 1.0, 1.0),
    options=(
        Option("identity.patient", "病人", "identity", "patient"),
        Option("identity.public_other", "一般民眾及其他", "identity", "public_other"),
    ),
)
VALUE_SECTION = Section(
    "name_mrn",
    (0.0, 0.0, 1.0, 1.0),
    values=(ValueSpec("name", "name", "name"),),
)


def _crop(tmp_path):
    path = tmp_path / "crop.png"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_options_prompt_lists_ids_and_labels():
    prompt = build_options_prompt(OPTION_SECTION.options)
    assert "identity.patient" in prompt and "病人" in prompt
    assert "JSON" in prompt


def test_values_prompt_lists_fields():
    prompt = build_values_prompt(VALUE_SECTION.values)
    assert "name" in prompt and "JSON" in prompt


def test_vlm_fn_parses_marked_options(tmp_path):
    def fake_post(url, payload):
        return {"message": {"content": '{"options":[{"id":"identity.patient","marked":true}]}'}}

    vlm = make_ollama_vlm_fn("http://host:11434", "m", post_fn=fake_post)
    result = vlm(_crop(tmp_path), OPTION_SECTION)
    assert {"id": "identity.patient", "marked": True} in result["options"]


def test_vlm_fn_reads_values(tmp_path):
    def fake_post(url, payload):
        return {"message": {"content": '{"values":[{"id":"name","text":"葉心安"}]}'}}

    vlm = make_ollama_vlm_fn("http://host", "m", post_fn=fake_post)
    result = vlm(_crop(tmp_path), VALUE_SECTION)
    assert result["values"] == [{"id": "name", "text": "葉心安"}]


def test_vlm_fn_chunks_large_option_lists(tmp_path):
    options = tuple(
        Option(f"cancer.{i}", f"癌{i}", "patient_fields.cancers", f"c{i}", "multi")
        for i in range(MAX_OPTIONS_PER_CALL * 2 + 1)
    )
    section = Section("cancers", (0.0, 0.0, 1.0, 1.0), options=options)
    calls = {"n": 0, "sizes": []}

    def fake_post(url, payload):
        calls["n"] += 1
        # each option line is "  <id> = <label>"; count via the " = " separator
        content = payload["messages"][0]["content"]
        calls["sizes"].append(content.count(" = "))
        return {"message": {"content": '{"options":[]}'}}

    vlm = make_ollama_vlm_fn("http://host", "m", post_fn=fake_post)
    vlm(_crop(tmp_path), section)
    assert calls["n"] == 3  # 25 options -> ceil(25/12) = 3 calls
    assert max(calls["sizes"]) <= MAX_OPTIONS_PER_CALL


def test_vlm_fn_degrades_on_connection_error(tmp_path):
    def boom(url, payload):
        raise ConnectionError("no server")

    vlm = make_ollama_vlm_fn("http://host", "m", post_fn=boom)
    assert vlm(_crop(tmp_path), OPTION_SECTION) == {"options": [], "values": []}


def test_vlm_fn_degrades_on_bad_json(tmp_path):
    def bad(url, payload):
        return {"message": {"content": ""}}

    vlm = make_ollama_vlm_fn("http://host", "m", post_fn=bad)
    assert vlm(_crop(tmp_path), OPTION_SECTION) == {"options": [], "values": []}
