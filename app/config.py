from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    MAX_FILE_SIZE_MB: int = 15
    ENVIRONMENT: str = "production"

    class Config:
        env_file = ".env"

settings = Settings()