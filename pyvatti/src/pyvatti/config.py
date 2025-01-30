import enum
import os
import pathlib
import sys
from tempfile import NamedTemporaryFile
from typing import Optional, Self

from pydantic import (
    Field,
    DirectoryPath,
    KafkaDsn,
    model_validator,
    HttpUrl,
    PositiveInt,
)
from pydantic_settings import BaseSettings


class K8SNamespace(str, enum.Enum):
    DEV = "intervene-dev"
    TEST = "intervene-test"
    PROD = "intervene-prod"


class Settings(BaseSettings):
    HELM_CHART_PATH: DirectoryPath = Field(
        description="Path to the helmvatti chart directory",
        default_factory=lambda: pathlib.Path(os.getcwd()) / "helmvatti",
    )
    TIMEOUT_SECONDS: int = Field(
        gt=0,
        default=60 * 60,
        description="Number of seconds before undeployed jobs are transitioned to FAILED state",
    )
    DEPLOYED_TIMEOUT_SECONDS: int = Field(
        gt=0,
        default=60 * 60 * 24 * 2,
        description="Number of seconds before deployed jobs are transitioned to FAILED state ",
    )
    MIN_OVERLAP: float = Field(
        ge=0,
        le=1,
        default=0.75,
        description="Minimum variant overlap for launched jobs (pgsc_calc)",
    )
    TOWER_TOKEN: str = Field(description="Seqera platform token")
    TOWER_WORKSPACE: int = Field(description="Seqera platform workspace ID")
    GLOBUS_DOMAIN: str = Field(description="Globus collection domain")
    GLOBUS_CLIENT_ID: str = Field(description="Globus client ID")
    GLOBUS_CLIENT_SECRET: str = Field(description="Secret for Globus API")
    GLOBUS_SCOPES: str = Field(description="Globus scopes")
    GCP_PROJECT: Optional[str] = Field(
        description="Google Cloud Platform (GCP) project ID"
    )
    GCP_LOCATION: Optional[str] = Field(
        description="Location to request GCP resources from"
    )
    NAMESPACE: K8SNamespace = Field(
        default=K8SNamespace.DEV,
        description="Kubernetes namespace to deploy resources to",
    )
    POLL_INTERVAL: int = Field(
        gt=0,
        default=60,
        description="Number of seconds to wait before polling Seqera platform API",
    )
    SQLITE_DB_PATH: pathlib.Path = Field(
        description="Path to a sqlite database",
        default_factory=lambda: NamedTemporaryFile(delete=False).name,
    )
    KAFKA_BOOTSTRAP_SERVER: Optional[KafkaDsn] = Field(default=None)
    KAFKA_CONSUMER_TOPIC: Optional[str] = Field(default="pipeline-launch")
    KAFKA_PRODUCER_TOPIC: Optional[str] = Field(default="pipeline-status")
    KEY_HANDLER_TOKEN: str = Field(
        description="Token to authenticate with the key handler service"
    )
    KEY_HANDLER_PASSWORD: str = Field(
        description="Password used by the globus file handler to decrypt the secret key"
    )
    KEY_HANDLER_URL: Optional[HttpUrl] = Field(
        description="URL used to contact the key handler service"
    )
    MAX_CONCURRENT_JOBS: PositiveInt = Field(
        description="Maximum number of concurrent jobs to run on GKE cluster.",
        default=10,
    )

    @model_validator(mode="after")
    def check_mandatory_settings(self) -> Self:
        if "pyvatti.cli" not in sys.modules:
            # kafka parameters are optional in the CLI
            if self.KAFKA_BOOTSTRAP_SERVER is None:
                raise ValueError(
                    "Missing KAFKA_BOOTSTRAP_SERVER in main (optional only for CLI)"
                )

        return self
