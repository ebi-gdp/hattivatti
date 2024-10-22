import enum
import os
import pathlib
import sys
from tempfile import NamedTemporaryFile
from typing import Optional

from pydantic import Field, DirectoryPath, KafkaDsn
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
        default=60 * 60 * 24,
        description="Number of seconds before active (requested, created, "
        "or deployed) jobs are transitioned to FAILED state",
    )
    TOWER_TOKEN: str = Field(description="Seqera platform token")
    TOWER_WORKSPACE: str = Field(description="Seqera platform workspace ID")
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
    KAFKA_BOOTSTRAP_SERVER: KafkaDsn
    KAFKA_CONSUMER_TOPIC: str = Field(default="pipeline-launch")
    KAFKA_PRODUCER_TOPIC: str = Field(default="pipeline-status")


if "pytest" in sys.modules:
    settings = Settings(
        TOWER_TOKEN="test",
        TOWER_WORKSPACE="test",
        GLOBUS_DOMAIN="https://example.com",
        GLOBUS_CLIENT_ID="test",
        GLOBUS_CLIENT_SECRET="test",
        GLOBUS_SCOPES="test",
        KAFKA_BOOTSTRAP_SERVER="kafka://localhost:9092",
        GCP_PROJECT="testproject",
        GCP_LOCATION="europe-west2",
    )
else:
    settings = Settings()
