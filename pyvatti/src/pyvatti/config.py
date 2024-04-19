from typing import Optional

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
    TOWER_TOKEN: str = Field(description="Seqera platform token")
    TOWER_WORKSPACE: str = Field(description="Seqera platform workspace ID")
    GCP_PROJECT: Optional[str] = Field(
        default=None, description="Google Cloud Platform (GCP) project ID"
    )
    GCP_LOCATION: Optional[str] = Field(
        default=None, description="Location to request GCP resources from"
    )


settings = Settings()
