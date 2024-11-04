"""
This module provides classes for validating and rendering a helm template.

It's assumed input parameters are validated by JobModels. This module aims to model and
validate generated job configuration, like work bucket names.
"""

import pathlib
from typing import Optional

import yaml
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ConfigDict,
    UUID4,
    field_serializer,
    HttpUrl,
)

from pyvatti.config import Settings
from pyvatti.messagemodels import JobRequest, GlobusConfig, TargetGenome


def parse_value_template(helm_chart_path: pathlib.Path) -> dict:
    values_template = helm_chart_path / "values-example.yaml"
    return yaml.safe_load(values_template.read_text())


class NextflowParams(BaseModel):
    """Represents nextflow configuration values that can be templated by helm"""

    model_config = ConfigDict(validate_assignment=True)

    workBucketPath: str
    gcpProject: str
    location: str
    spot: bool
    wave: bool
    fusion: bool

    @field_validator("workBucketPath")  # type: ignore
    @classmethod
    def check_gcp_bucket(cls, name: str):
        if not name.startswith("gs://"):
            raise ValueError("Bucket name doesn't start with gs://")
        return name


class CalcJobParams(BaseModel):
    """Represents workflow instance values that can be templated by helm"""

    model_config = ConfigDict(validate_assignment=True)

    input: str
    min_overlap: float = Field(ge=0, le=1)
    pgs_id: Optional[str]
    pgp_id: Optional[str]
    trait_efo: Optional[str]
    target_build: str
    format: str
    outdir: str

    @field_validator("outdir")  # type: ignore
    @classmethod
    def check_gcp_bucket(cls, name: str):
        if not name.startswith("gs://"):
            raise ValueError("Bucket name doesn't start with gs://")
        return name


class JobInput(BaseModel):
    sampleset: str
    chrom: Optional[str]
    vcf_import_dosage: bool
    geno: str
    pheno: str
    variants: str
    format: str


class GlobflowParams(BaseModel):
    input: str
    outdir: str
    config_application: str
    config_crypt4gh: str


class Secrets(BaseModel):
    globusDomain: str
    globusClientId: str
    globusClientSecret: str
    globusScopes: str
    towerToken: str
    towerId: str
    keyHandlerToken: str
    keyHandlerPassword: str
    keyHandlerURL: HttpUrl

    @field_serializer("keyHandlerURL")
    @classmethod
    def url_to_string(cls, url: HttpUrl) -> str:
        return str(url)


class KeyHandlerDetails(BaseModel):
    secretId: UUID4
    secretIdVersion: str

    @field_serializer("secretId")
    @classmethod
    def uuid_to_str(cls, uuid: UUID4) -> str:
        return str(uuid).upper()


class HelmValues(BaseModel):
    """Represents all fields in the helm chart that can be templated"""

    model_config = ConfigDict(validate_assignment=True, use_enum_values=True)

    baseImage: str
    dockerTag: str
    pullPolicy: str

    # don't model this
    serviceAccount: dict

    nxfParams: NextflowParams

    calcWorkflowInput: list[TargetGenome]

    calcJobParams: CalcJobParams
    keyHandlerSecret: KeyHandlerDetails
    globflowInput: GlobusConfig
    globflowParams: GlobflowParams
    secrets: Secrets


def _add_secrets(job: HelmValues, settings: Settings) -> None:
    """Add secrets from the settings object"""
    job.secrets.towerToken = settings.TOWER_TOKEN
    job.secrets.towerId = settings.TOWER_WORKSPACE
    job.secrets.globusDomain = settings.GLOBUS_DOMAIN
    job.secrets.globusClientId = settings.GLOBUS_CLIENT_ID
    job.secrets.globusClientSecret = settings.GLOBUS_CLIENT_SECRET
    job.secrets.globusScopes = settings.GLOBUS_SCOPES
    job.secrets.keyHandlerToken = settings.KEY_HANDLER_TOKEN
    job.secrets.keyHandlerPassword = settings.KEY_HANDLER_PASSWORD
    job.secrets.keyHandlerURL = settings.KEY_HANDLER_URL


def _add_bucket_path(job: JobRequest, bucketPath: str) -> None:
    """Add bucket details to the job request"""
    if bucketPath.startswith("gs://"):
        raise ValueError("Raw bucket names only, please drop the gs:// prefix")

    for x in ("geno", "pheno", "variants"):
        for genome in job.pipeline_param.target_genomes:
            setattr(genome, x, f"gs://{bucketPath}/data/{getattr(genome, x)}")


def render_template(
    job: JobRequest, work_bucket_path: str, results_bucket_path: str, settings: Settings
) -> dict:
    """Render the helm template using new values from the job model"""
    _add_bucket_path(job, work_bucket_path)

    job_values: HelmValues = HelmValues(
        **parse_value_template(settings.HELM_CHART_PATH)
    )
    _add_secrets(job_values, settings)

    if settings.GCP_PROJECT is None or settings.GCP_LOCATION is None:
        raise ValueError("Missing GCP_PROJECT or GCP_LOCATION")

    # set bucket paths to follow nextflow standards (gs:// prefix and can't use root of bucket)
    job_values.globflowParams.outdir = f"gs://{work_bucket_path}/data"
    job_values.nxfParams.workBucketPath = f"gs://{work_bucket_path}/work"
    job_values.nxfParams.gcpProject = settings.GCP_PROJECT
    job_values.nxfParams.location = settings.GCP_LOCATION
    job_values.calcJobParams.outdir = f"gs://{results_bucket_path}/results"

    job_values.calcWorkflowInput = job.pipeline_param.target_genomes
    job_values.globflowInput = job.globus_details

    for x in ("pgs_id", "pgp_id", "trait_efo", "target_build"):
        setattr(
            job_values.calcJobParams, x, getattr(job.pipeline_param.nxf_params_file, x)
        )

    job_values.keyHandlerSecret.secretId = job.secret_key_details.secret_id
    job_values.keyHandlerSecret.secretIdVersion = (
        job.secret_key_details.secret_id_version
    )
    return job_values.model_dump()
