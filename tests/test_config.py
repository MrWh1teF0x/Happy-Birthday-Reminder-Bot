from pytest import MonkeyPatch

from src.config import Settings


def test_settings_reads_token_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")

    assert Settings().bot_token == "test-token"  # type: ignore[call-arg]  # токен из окружения
