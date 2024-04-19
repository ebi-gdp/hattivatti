from pydantic import Field, DirectoryPath
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HELM_CHART_PATH: DirectoryPath = Field(
        description="Path to the helmvatti chart directory"
    )
    TIMEOUT_SECONDS: int = Field(
        gt=0,
        default=60 * 60 * 24,
        description="Number of seconds before active (requested, created, "
        "or deployed) jobs are transitioned to FAILED state",
    )


settings = Settings()
