import enum
import sys
from typing import Optional

from pydantic import Field, DirectoryPath, AnyHttpUrl
from pydantic_settings import BaseSettings


class K8SNamespace(str, enum.Enum):
    DEV = "intervene-dev"
    TEST = "intervene-test"
    PROD = "intervene-prod"


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
    GLOBUS_DOMAIN: str = Field(description="Globus collection domain")
    GLOBUS_CLIENT_ID: str = Field(description="Globus client ID")
    GLOBUS_CLIENT_SECRET: str = Field(description="Secret for Globus API")
    GLOBUS_SCOPES: str = Field(description="Globus scopes")
    GCP_PROJECT: Optional[str] = Field(
        default=None, description="Google Cloud Platform (GCP) project ID"
    )
    GCP_LOCATION: Optional[str] = Field(
        default=None, description="Location to request GCP resources from"
    )
    NAMESPACE: K8SNamespace = Field(
        default=K8SNamespace.DEV,
        description="Kubernetes namespace to deploy resources to",
    )
    NOTIFY_URL: AnyHttpUrl = Field(description="Backend notification URL")
    POLL_INTERVAL: int = Field(
        gt=0,
        default=60,
        description="Number of seconds to wait before polling Seqera platform API",
    )
    NOTIFY_TOKEN: str = Field(description="Token for backend notifications")


if "pytest" in sys.modules:
    settings = None
else:
    settings = Settings()
