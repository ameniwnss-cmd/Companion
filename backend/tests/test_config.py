import pytest

from companion.config import Environment, Settings


@pytest.mark.parametrize(
    ("environment", "flag", "expected"),
    [
        (Environment.DEVELOPMENT, True, True),
        (Environment.TEST, True, True),
        (Environment.DEVELOPMENT, False, False),
        (Environment.PRODUCTION, True, False),
    ],
)
def test_dev_text_channel_is_never_enabled_in_production(
    environment: Environment, flag: bool, expected: bool
) -> None:
    settings = Settings(environment=environment, dev_text_channel=flag, _env_file=None)

    assert settings.dev_text_channel_enabled is expected


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", '["https://companion.example"]')

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.PRODUCTION
    assert settings.cors_origins == ["https://companion.example"]
