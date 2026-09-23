from pytest import MonkeyPatch

from src.config.config import Settings


def test_settings_reads_token_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")

    assert Settings().bot_token == "test-token"  # type: ignore[call-arg]  # токен из окружения


def test_database_url_prefers_db_url() -> None:
    settings = Settings(bot_token="t", db_url="postgresql+asyncpg://user:pass@db:5432/name")

    assert settings.database_url == "postgresql+asyncpg://user:pass@db:5432/name"


def test_database_url_falls_back_to_db_parts() -> None:
    settings = Settings(
        bot_token="t",
        db_user="user",
        db_password="pass",
        db_name="name",
        db_host_port=5437,
        db_url="",
    )

    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5437/name"
