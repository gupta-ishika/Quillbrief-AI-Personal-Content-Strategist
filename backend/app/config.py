from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # YouTube & Platform
    youtube_api_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/youtube/callback"

    # Encryption
    fernet_encryption_key: str = ""

    # Server & Security
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_origin: str = "http://localhost:5173"

    # Databases
    database_url: str = "sqlite:///./app.db"
    checkpoints_database_url: str = "sqlite:///./checkpoints.db"

    # Ollama & Models
    ollama_base_url: str = "http://localhost:11434"
    model_name: str = "qwen3.5:4b"
    embedding_model: str = "nomic-embed-text"

    # Brief defaults
    default_brief_day: str = "mon"
    default_brief_time: str = "08:00"
    default_time_zone: str = "Asia/Kolkata"
    default_depth_level: str = "standard"

    @property
    def api_key_configured(self) -> bool:
        return bool(self.youtube_api_key and self.youtube_api_key.strip())


settings = Settings()
