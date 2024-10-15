"""
This module provides classes for validating and rendering a helm template.

It's assumed input parameters are validated by JobModels. This module aims to model and
validate generated job configuration, like work bucket names.
"""

import pathlib
from functools import lru_cache
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from pyvatti.config import settings
from pyvatti.models import JobRequest


@lru_cache
def parse_value_template():
    values_template = pathlib.Path(settings.HELM_CHART_PATH / "values-example.yaml")
    return yaml.safe_load(values_template.read_text())


def check_gcp_bucket(name: str) -> str:
    if not name.startswith("gs://"):
        raise ValueError("Bucket name doesn't start with gs://")
    return name


class NextflowParams(BaseModel, validate_assignment=True):
    """Represents nextflow configuration values that can be templated by helm"""

    workBucketPath: str
    gcpProject: str
    location: str
    spot: bool
    wave: bool
    fusion: bool

    check_bucket = field_validator("workBucketPath")(check_gcp_bucket)


class CalcJobParams(BaseModel, validate_assignment=True):
    """Represents workflow instance values that can be templated by helm"""

    input: str
    min_overlap: float = Field(ge=0, le=1)
    pgs_id: Optional[str]
    pgp_id: Optional[str]
    trait_efo: Optional[str]
    target_build: str
    format: str
    outdir: str

    check_bucket = field_validator("outdir")(check_gcp_bucket)


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
    config_secrets: str


class Secrets(BaseModel):
    """These secrets must be templated with pyvatti environment variables"""

    globusDomain: str
    globusClientId: str
    globusClientSecret: str
    globusScopes: str
    towerToken: str
    towerId: str


class HelmValues(BaseModel, validate_assignment=True):
    """Represents all fields in the helm chart that can be templated"""

    baseImage: str
    dockerTag: str
    pullPolicy: str

    # don't model this
    serviceAccount: dict

    nxfParams: NextflowParams
    # a JSON string
    calcWorkflowInput: str

    calcJobParams: CalcJobParams
    # a JSON string
    globflowInput: str
    globflowParams: GlobflowParams
    secrets: Secrets
    # don't model this
    serviceAccount: dict


def _add_secrets(job: HelmValues):
    """Add secrets from the fastAPI settings object"""
    job.secrets.towerToken = settings.TOWER_TOKEN
    job.secrets.towerId = settings.TOWER_WORKSPACE
    job.secrets.globusDomain = settings.GLOBUS_DOMAIN
    job.secrets.globusClientId = settings.GLOBUS_CLIENT_ID
    job.secrets.globusClientSecret = settings.GLOBUS_CLIENT_SECRET
    job.secrets.globusScopes = settings.GLOBUS_SCOPES


def _add_bucket_path(job, bucketPath):
    """Add bucket details to the job request"""
    for x in ("geno", "pheno", "variants"):
        for genome in job.pipeline_param.target_genomes:
            setattr(genome, x, f"gs://{bucketPath}/data/{getattr(genome, x)}")


def render_template(
    job: JobRequest, work_bucket_path: str, results_bucket_path: str
) -> dict:
    """Render the helm template using new values from the job model"""
    _add_bucket_path(job, work_bucket_path)

    job_values: HelmValues = HelmValues(**parse_value_template())
    _add_secrets(job_values)

    # set bucket paths to follow nextflow standards (gs:// prefix and can't use root of bucket)
    job_values.globflowParams.outdir = f"gs://{work_bucket_path}/data"
    job_values.nxfParams.workBucketPath = f"gs://{work_bucket_path}/work"
    job_values.calcJobParams.outdir = f"gs://{results_bucket_path}/results"

    job_values.calcWorkflowInput = job.pipeline_param.target_genome.model_dump_json()
    job_values.globflowInput = job.globus_details.model_dump_json()

    for x in ("pgs_id", "pgp_id", "trait_efo", "target_build"):
        setattr(
            job_values.calcJobParams, x, getattr(job.pipeline_param.nxf_params_file, x)
        )

    return job_values.model_dump()
