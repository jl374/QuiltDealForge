from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://dealforge:dealforge_local@localhost:5432/dealforge"
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    INTERNAL_API_KEY: str = "dev-internal-key-change-in-prod"
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_PLACES_API_KEY: str = ""
    APOLLO_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @classmethod
    def settings_customise_sources(cls, settings_cls, **kwargs):  # type: ignore[override]
        """Give .env file priority over shell environment variables locally.

        By default Pydantic Settings reads env vars first, then .env file.
        Claude Desktop exports an empty ANTHROPIC_API_KEY which shadows the
        real key in our .env file. Reversing the order fixes this locally.
        In production (no .env file), env vars work normally.
        """
        import os
        init = kwargs.get("init_settings")
        env = kwargs.get("env_settings")
        dotenv = kwargs.get("dotenv_settings")
        file_secret = kwargs.get("file_secret_settings")
        # In production, prefer env vars (no .env file present)
        if os.environ.get("ENVIRONMENT") == "production":
            return (init, env, dotenv, file_secret)
        # Locally, .env file wins over shell env vars
        return (init, dotenv, env, file_secret)


settings = Settings()
