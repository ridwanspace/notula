from pathlib import Path

import pytest

from notula.infrastructure.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "NOTULA_GEMINI_API_KEY",
        "NOTULA_DEEPSEEK_API_KEY",
        "NOTULA_PROVIDER",
        "NOTULA_DATA_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


def _settings(**kwargs: object) -> Settings:
    # _env_file=None: unit tests must not read the developer's real .env.
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def test_defaults() -> None:
    settings = _settings()
    assert settings.provider == "mock"
    assert settings.gemini_api_key == ""
    assert settings.deepseek_api_key == ""
    assert settings.gemini_model == "gemini-3.5-flash"
    assert settings.summarizer_model == "deepseek-v4-flash"
    assert settings.data_dir == Path("var")
    assert settings.db_path == Path("var/notula.db")
    assert settings.uploads_dir == Path("var/uploads")
    assert settings.workdir == Path("var/work")


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTULA_PROVIDER", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("NOTULA_DATA_DIR", "/tmp/notula-data")  # noqa: S108 - test value only
    settings = _settings()
    assert settings.provider == "live"
    assert settings.gemini_api_key == "gm-test"
    assert settings.deepseek_api_key == "ds-test"
    assert settings.data_dir == Path("/tmp/notula-data")  # noqa: S108


def test_validate_live_lists_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTULA_PROVIDER", "live")
    settings = _settings()
    with pytest.raises(ValueError, match="GEMINI_API_KEY, DEEPSEEK_API_KEY"):
        settings.validate_live()


def test_validate_live_passes_with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTULA_PROVIDER", "live")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    _settings().validate_live()


def test_validate_live_noop_for_mock() -> None:
    _settings().validate_live()
