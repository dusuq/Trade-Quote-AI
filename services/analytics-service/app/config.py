from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "analytics-service"
    environment: str = "development"
    port: int = 8006

    # Database
    database_url: str = "postgresql://tradequote:tradequote_dev_pass@localhost:5432/tradequote_dev"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
