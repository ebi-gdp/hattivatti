import pathlib
from functools import lru_cache
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from .config import settings


@lru_cache
def parse_value_template():
    values_template = pathlib.Path(settings.HELM_CHART_PATH / "values.yaml")
    return yaml.safe_load(values_template.read_text())


def check_gcp_bucket(name: str) -> str:
    if not name.startswith("gs://"):
        raise ValueError("Bucket name doesn't start with gs://")
    return name


def valid_target_build(cls, target_build: str) -> str:
    good_builds = ["GRCh37", "GRCh38"]
    if target_build not in good_builds:
        raise ValueError(f"Target build not in {good_builds}")
    return target_build


class HelmNextflowValues(BaseModel, validate_assignment=True):
    """Represents nextflow configuration values that can be templated by helm"""

    workBucketPath: str
    gcpProject: str
    location: str
    spot: bool
    wave: bool
    fusion: bool

    check_bucket = field_validator("workBucketPath")(check_gcp_bucket)


class HelmJobValues(BaseModel, validate_assignment=True):
    """Represents workflow instance values that can be templated by helm"""

    min_overlap: float = Field(ge=0, le=1)
    pgs_id: Optional[str] = Field(pattern="PGS[0-9]{6}")
    pgp_id: Optional[str] = Field(pattern="PGP[0-9]{6}")
    trait_efo: Optional[str]
    target_build: str
    format: str
    outdir: str

    check_bucket = field_validator("outdir")(check_gcp_bucket)
    check_build = field_validator("target_build")(valid_target_build)


class HelmValues(BaseModel, validate_assignment=True):
    """Represents all fields in the helm chart that can be templated"""

    baseImage: str
    dockerTag: str
    pullPolicy: str
    towerToken: str
    towerId: str
    # do model these
    nxf: HelmNextflowValues
    job: HelmJobValues
    json_input: str
    # don't model this
    serviceAccount: dict


HELM_VALUES = HelmValues(**parse_value_template())
