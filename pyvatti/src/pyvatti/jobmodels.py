import enum
import pathlib
from typing import Optional, Self

from pgscatalog.core import GenomeBuild

from pydantic import BaseModel, UUID4, model_validator, field_validator


class GlobusFile(BaseModel):
    """Globus files have a name and size. Size is used to restart interrupted transfers."""

    filename: str
    size: int


class GlobusConfig(BaseModel):
    """Details required to stage files from Globus for working on"""

    guest_collection_id: UUID4
    dir_path_on_guest_collection: str
    files: list[GlobusFile]


class TargetFormat(enum.Enum):
    """Genotypes can be in plink1 (bfile) or plink2 (pfile) format currently

    plink2 is preferred"""

    PFILE = "pfile"
    BFILE = "bfile"


class TargetGenome(BaseModel):
    """A target genome contains one or more genotypes and associated metadata

    Genomes may optionally be split by chromosome to speed up calculation on larger datasets"""

    sampleset: str
    chrom: str | None
    vcf_import_dosage: bool = False
    geno: pathlib.Path
    pheno: pathlib.Path
    variants: pathlib.Path
    format: TargetFormat


class SamplesheetFormat(enum.Enum):
    """Nextflow samplesheet format. The API only accepts json, currently.

    By default, the nextflow workflow accepts and uses csv.
    """

    JSON = "json"


class PGSParams(BaseModel):
    """Runtime parameters for the PGS calculation workflow"""

    pgs_id: Optional[str] = None
    pgp_id: Optional[str] = None
    trait_efo: Optional[str] = None
    target_build: GenomeBuild
    format: SamplesheetFormat = SamplesheetFormat.JSON

    @model_validator(mode="after")
    def check_pgs(self) -> Self:
        if all(getattr(self, x) is None for x in ("pgs_id", "pgp_id", "trait_efo")):
            raise ValueError("Missing all pgs_id, pgp_id, or trait_efo")
        return self


class PGSJobParams(BaseModel):
    id: str
    target_genomes: list[TargetGenome]
    nxf_params_file: PGSParams
    nxf_work: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, x: str) -> str:
        if not x.startswith("INTP"):
            raise ValueError(f"id must start with INTP, got {x}")
        return x


class JobModel(BaseModel):
    globus_details: GlobusConfig
    pipeline_param: PGSJobParams
