from ocr_from2xlsx.recognition.layout import Option, Section, ValueSpec
from ocr_from2xlsx.recognition.llama_client import build_section_prompt, make_ollama_vlm_fn

SECTION = Section(
    "identity_gender",
    (0.0, 0.0, 1.0, 1.0),
    options=(Option("identity.patient", "病人", "identity", "patient"),),
    values=(ValueSpec("service_date", "service_date", "date"),),
)


def _crop(tmp_path):
    path = tmp_path / "crop.png"
    path.write_bytes(b"fake-image-bytes")
    return str(path)


def test_vlm_fn_parses_server_json(tmp_path):
    captured = {}

    def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "message": {
                "content": '{"options":[{"id":"identity.patient","marked":true,"confidence":0.9}],"values":[]}'
            }
        }

    vlm = make_ollama_vlm_fn("http://host:11434", "m", post_fn=fake_post)
    result = vlm(_crop(tmp_path), SECTION)
    assert result["options"][0]["id"] == "identity.patient"
    assert result["values"] == []
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["model"] == "m"
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["messages"][0]["images"]  # base64 image attached


def test_vlm_fn_degrades_on_connection_error(tmp_path):
    def boom(url, payload):
        raise ConnectionError("no server")

    vlm = make_ollama_vlm_fn("http://host", "m", post_fn=boom)
    assert vlm(_crop(tmp_path), SECTION) == {"options": [], "values": []}


def test_vlm_fn_degrades_on_bad_json(tmp_path):
    def bad(url, payload):
        return {"message": {"content": "this is not json"}}

    vlm = make_ollama_vlm_fn("http://host", "m", post_fn=bad)
    assert vlm(_crop(tmp_path), SECTION) == {"options": [], "values": []}


def test_prompt_lists_options_and_values():
    prompt = build_section_prompt(SECTION)
    assert "identity.patient" in prompt and "病人" in prompt
    assert "service_date" in prompt
    assert "JSON" in prompt
