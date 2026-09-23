from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки бота.

    Значения берутся из переменных окружения,
    при их отсутствии — из файла .env в корне проекта.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str

    db_user: str = "bot"
    db_password: str = "bot"
    db_name: str = "birthday_bot"
    db_host_port: int = 5437
    db_url: str = ""

    @property
    def database_url(self) -> str:
        """Полный DSN: DB_URL, либо сборка из DB_* частей (локальный запуск)."""
        if self.db_url:
            return self.db_url
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@localhost:{self.db_host_port}/{self.db_name}"
        )
