from __future__ import annotations

import pytest

from ocr_from2xlsx import cli


def test_bare_invocation_launches_app(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("ocr_from2xlsx.app.run_app", lambda: calls.append("app") or 0)

    exit_code = cli.main([])

    assert exit_code == 0
    assert calls == ["app"]


def test_version_still_short_circuits(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("ocr_from2xlsx.app.run_app", lambda: (_ for _ in ()).throw(AssertionError("app launched")))

    exit_code = cli.main(["--version"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip()  # printed a version, did not launch app


def test_explicit_subcommand_does_not_launch_app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr("ocr_from2xlsx.app.run_app", lambda: (_ for _ in ()).throw(AssertionError("app launched")))
    output = tmp_path / "sample.json"

    exit_code = cli.main(["sample-json", "--output", str(output)])

    assert exit_code == 0
    assert output.is_file()
