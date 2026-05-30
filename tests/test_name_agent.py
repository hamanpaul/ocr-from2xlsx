from __future__ import annotations

from pathlib import Path

import pytest

from ocr_from2xlsx.name_agent import (
    NameAgentConfig,
    NullNameAgent,
    build_agent,
    load_config,
)


def test_missing_config_is_disabled(tmp_path: Path):
    config = load_config(tmp_path / "absent.toml")
    assert config.enabled is False


def test_disabled_config_builds_null_agent(tmp_path: Path):
    path = tmp_path / "name_agent.toml"
    path.write_text('enabled = false\nprovider = "claude"\n', encoding="utf-8")
    agent = build_agent(load_config(path))
    assert isinstance(agent, NullNameAgent)
    assert agent.suggest("anything.png") is None


def test_enabled_config_parsed(tmp_path: Path):
    path = tmp_path / "name_agent.toml"
    path.write_text(
        'enabled = true\nprovider = "claude"\nmodel = "claude-x"\n'
        'endpoint = "https://api.example/v1/messages"\nprompt = "read the name"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.enabled is True
    assert config.provider == "claude"
    assert config.model == "claude-x"


def test_enabled_config_without_prompt_uses_default_prompt_string(tmp_path: Path):
    path = tmp_path / "name_agent.toml"
    path.write_text(
        'enabled = true\nprovider = "claude"\nmodel = "claude-x"\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.prompt == "讀出圖片中的手寫中文姓名，只回傳姓名本身，不要其他文字。"


def test_load_config_rejects_non_boolean_enabled(tmp_path: Path):
    path = tmp_path / "name_agent.toml"
    path.write_text('enabled = "false"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="enabled must be a bool"):
        load_config(path)


@pytest.mark.parametrize("value", ["0", "1", "1.5", '["true"]'])
def test_load_config_rejects_non_boolean_enabled_edge_cases(tmp_path: Path, value: str):
    path = tmp_path / "name_agent.toml"
    path.write_text(f"enabled = {value}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="enabled must be a bool"):
        load_config(path)


@pytest.mark.parametrize("field", ["provider", "model", "endpoint", "prompt", "api_key_env"])
def test_load_config_rejects_non_string_fields(tmp_path: Path, field: str):
    path = tmp_path / "name_agent.toml"
    path.write_text(f"{field} = 123\n", encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{field} must be a string"):
        load_config(path)


@pytest.mark.parametrize("field", ["provider", "model", "endpoint", "prompt", "api_key_env"])
def test_load_config_rejects_non_string_field_containers(tmp_path: Path, field: str):
    path = tmp_path / "name_agent.toml"
    path.write_text(f'{field} = ["bad"]\n', encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{field} must be a string"):
        load_config(path)


def test_unknown_provider_falls_back_to_null(tmp_path: Path):
    config = NameAgentConfig(enabled=True, provider="nope")
    assert isinstance(build_agent(config), NullNameAgent)
