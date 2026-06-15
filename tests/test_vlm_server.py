from ocr_from2xlsx.recognition.vlm_server import resolve_ollama


def _fake_bundle(tmp_path):
    vlm = tmp_path / "vlm"
    (vlm / "models").mkdir(parents=True)
    exe = vlm / ("ollama.exe" if __import__("os").name == "nt" else "ollama")
    exe.write_bytes(b"fake")
    return vlm, exe


def test_resolve_prefers_explicit_env(tmp_path, monkeypatch):
    vlm, exe = _fake_bundle(tmp_path)
    monkeypatch.setenv("OCR_VLM_OLLAMA_EXE", str(exe))
    monkeypatch.setenv("OCR_VLM_OLLAMA_MODELS", str(vlm / "models"))
    got_exe, got_models = resolve_ollama(roots=[])
    assert got_exe == exe
    assert got_models == vlm / "models"


def test_resolve_finds_bundle_root(tmp_path, monkeypatch):
    monkeypatch.delenv("OCR_VLM_OLLAMA_EXE", raising=False)
    monkeypatch.delenv("OCR_FROM2XLSX_HOME", raising=False)
    vlm, exe = _fake_bundle(tmp_path)
    got_exe, got_models = resolve_ollama(roots=[tmp_path])
    assert got_exe == exe
    assert got_models == vlm / "models"


def test_resolve_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("OCR_VLM_OLLAMA_EXE", raising=False)
    monkeypatch.delenv("OCR_FROM2XLSX_HOME", raising=False)
    got_exe, got_models = resolve_ollama(roots=[tmp_path / "nope"])
    assert got_exe is None
    assert got_models is None
