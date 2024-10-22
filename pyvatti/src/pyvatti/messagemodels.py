"""This module contains pydantic models that parse and validate a job request message"""

import enum
import pathlib
from typing import Optional, Self, Annotated, Any

from pydantic import (
    BaseModel,
    model_validator,
    field_validator,
    Field,
    UUID4,
    field_serializer,
    RootModel,
)


class GlobusFile(BaseModel):
    """Globus files have a name and size.

    These parameters are passed to the file handler CLI to start and resume transfers.

    Files must be rejected if they don't look like they've been encrypted with crypt4gh.

    >>> f = {"filename": "hapnest.pvar.c4gh", "size": 215004174}
    >>> GlobusFile(**f)
    GlobusFile(filename='hapnest.pvar.c4gh', size=215004174)

    >>> GlobusFile(**{"filename": "bad_file.txt", "size": 100})  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: 1 validation error for GlobusFile
    filename
      Value error, Filename value='bad_file.txt' must end with .c4gh [type=value_error, input_value='bad_file.txt', input_type=str]
      ...
    """

    filename: Annotated[str, Field(description="Filename")]
    size: Annotated[int, Field(description="Size of file in bytes", gt=0)]

    @field_validator("filename")  # type: ignore
    @classmethod
    def must_have_c4gh_suffix(cls, value: str):
        if value.endswith(".c4gh"):
            return value
        else:
            raise ValueError(f"Filename {value=} must end with .c4gh")


class GlobusConfig(BaseModel):
    """Details required to stage files from Globus for working on

    >>> f = {"filename": "hapnest.pgen.c4gh", "size": 278705850}
    >>> GlobusConfig(dir_path_on_guest_collection="test@ebi.ac.uk/test", files=[GlobusFile(**f)])
    GlobusConfig(dir_path_on_guest_collection='test@ebi.ac.uk/test', files=[GlobusFile(filename='hapnest.pgen.c4gh', size=278705850)])
    """

    dir_path_on_guest_collection: Annotated[
        str, Field(description="Globus path to directory where file is stored")
    ]
    files: Annotated[
        list[GlobusFile],
        Field(description="A list of files the file handler must download"),
    ]


class TargetFormat(str, enum.Enum):
    """The PGS Catalog Calculator supports target genomes in PLINK1/2 format and VCF"""

    PFILE = "pfile"
    BFILE = "bfile"
    VCF = "vcf"


class TargetGenome(BaseModel):
    """A target genome contains one or more genotypes and associated metadata

    Genomes may optionally be split by chromosome to speed up calculation on larger datasets

    >>> data = {"sampleset": "test", "chrom": None, "geno": "hi.pgen", "pheno": "hi.psam", "variants": "hi.pvar.zst", "format": "pfile"}
    >>> TargetGenome(**data)
    TargetGenome(sampleset='test', chrom=None, vcf_import_dosage=False, geno=PosixPath('hi.pgen'), pheno=PosixPath('hi.psam'), variants=PosixPath('hi.pvar.zst'), format=<TargetFormat.PFILE: 'pfile'>)

    >>> TargetGenome(**data).model_dump_json()
    '{"sampleset":"test","chrom":null,"vcf_import_dosage":false,"geno":"hi.pgen","pheno":"hi.psam","variants":"hi.pvar.zst","format":"pfile"}'

    VCFs are a special case. They contain genotypes, variants, and sample metadata in a single file, so the path should be repeated:

    >>> data = {"sampleset": "test", "chrom": None, "geno": "hi.vcf.gz", "pheno": "hi.vcf.gz", "variants": "hi.vcf.gz", "format": "vcf"}
    >>> TargetGenome(**data)
    TargetGenome(sampleset='test', chrom=None, vcf_import_dosage=False, geno=PosixPath('hi.vcf.gz'), pheno=PosixPath('hi.vcf.gz'), variants=PosixPath('hi.vcf.gz'), format=<TargetFormat.VCF: 'vcf'>)
    """

    sampleset: Annotated[str, Field(description="A human label for a cohort / dataset")]
    chrom: Annotated[
        Optional[str],
        Field(
            description="Which chromosome do genetic variants belong to? (None = multiple chromosomes)",
            default=None,
            coerce_numbers_to_str=True,
        ),
    ]
    vcf_import_dosage: Annotated[
        bool,
        Field(
            description="Should dosage data be imported or hard genotypes be used?",
            default=False,
        ),
    ]
    geno: Annotated[
        pathlib.Path,
        Field(description="Path to a genotype file (e.g. pgen / bed / vcf)"),
    ]
    pheno: Annotated[
        pathlib.Path, Field(description="Path to a phenotype file (e.g. psam / fam)")
    ]
    variants: Annotated[
        pathlib.Path,
        Field(description="Path to a variant information file (e.g. bim / pvar"),
    ]
    format: Annotated[
        TargetFormat, Field(description="What format are the target genomes in?")
    ]

    @field_validator("sampleset")  # type: ignore
    @classmethod
    def check_sampleset_name(cls, value: str) -> str:
        if "_" in value:
            raise ValueError("Sampleset name can't contain _")
        if value == "reference":
            raise ValueError("Sampleset name can't be reference")
        return value

    @field_validator("geno")  # type: ignore
    @classmethod
    def check_geno_suffix(cls, value: pathlib.Path) -> pathlib.Path:
        match suffix := value.suffix:
            case ".pgen" | ".bed":
                pass
            case ".gz" if ".vcf" in value.suffixes:
                pass
            case _:
                raise ValueError(f"Genotype file {suffix=} is not a supported format")
        return value

    @field_validator("variants")  # type: ignore
    @classmethod
    def check_variant_suffix(cls, value: pathlib.Path) -> pathlib.Path:
        match suffix := value.suffix:
            case ".pvar" | ".bim":
                pass
            case ".zst" if ".pvar" in value.suffixes or ".bim" in value.suffixes:
                pass
            case ".gz" if ".bim" in value.suffixes or ".vcf" in value.suffixes:
                pass
            case _:
                raise ValueError(
                    f"Variant information file {suffix=} is not a supported format"
                )

        return value

    @field_validator("pheno")  # type: ignore
    @classmethod
    def check_pheno_suffix(cls, value: pathlib.Path) -> pathlib.Path:
        match suffix := value.suffix:
            case ".psam" | ".fam":
                pass
            case ".gz" if ".vcf" in value.suffixes:
                pass
            case _:
                raise ValueError(
                    f"Phenotype information file {suffix=} is not a supported format"
                )

        return value

    @model_validator(mode="after")
    def check_format_and_filenames(self) -> Self:
        """Checks the declared format aligns with the file list"""
        paths: list[pathlib.Path] = [self.geno, self.pheno, self.variants]
        suffixes: list[list[str]] = [x.suffixes for x in paths]
        extensions: set[str] = {item for sublist in suffixes for item in sublist}

        # PLINK1/2 files are a triplet of variant information file (text), genotype (binary), and sample information file (text)
        # variant information files may be compressed with zstandard
        # VCFs are a single file, with optional bgzip compression
        match self.format:
            case TargetFormat.PFILE:
                if (
                    not {".pvar", ".psam", ".pgen"} == extensions
                    and not {".pvar", ".zst", ".psam", ".pgen"} == extensions
                ):
                    raise ValueError(
                        f"Invalid combination {self.format=} and file paths: {paths}"
                    )
            case TargetFormat.BFILE:
                if (
                    not {".bed", ".bim", ".fam"} == extensions
                    and not {".bed", ".bim", ".zst", ".fam"} == extensions
                ):
                    raise ValueError(
                        f"Invalid combination {self.format=} and file paths: {paths}"
                    )
            case TargetFormat.VCF:
                if not {".vcf"} == extensions and not {".vcf", ".gz"} == extensions:
                    raise ValueError(
                        f"Invalid combination {self.format=} and file paths: {paths}"
                    )
            case _:
                raise ValueError("Invalid format")

        return self

    @field_serializer("geno", "pheno", "variants")
    def serialise_path_to_str(self, path: pathlib.Path) -> str:
        return str(path)


class SamplesheetFormat(str, enum.Enum):
    """Nextflow samplesheet format. The API only accepts json, currently.

    By default, the nextflow workflow accepts and uses csv.
    """

    JSON = "json"


class GenomeBuild(str, enum.Enum):
    GRCh37 = "GRCh37"
    GRCh38 = "GRCh38"


class PGSParams(BaseModel):
    """Runtime parameters for the PGS calculation workflow

    >>> params = {"pgs_id": "PGS001229,PGS000013", "pgp_id": None, "trait_efo": "", "target_build": "GRCh37"}
    >>> PGSParams(**params)
    PGSParams(pgs_id='PGS001229,PGS000013', pgp_id=None, trait_efo=None, target_build=<GenomeBuild.GRCh37: 'GRCh37'>, format=<SamplesheetFormat.JSON: 'json'>)

    >>> PGSParams(**params).model_dump_json()
    '{"pgs_id":"PGS001229,PGS000013","pgp_id":null,"trait_efo":null,"target_build":"GRCh37","format":"json"}'

    >>> PGSParams(**{"pgs_id": None, "pgp_id": None, "trait_efo": "", "target_build": "GRCh37"})  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: 1 validation error for PGSParams
      Value error, Missing all pgs_id, pgp_id, or trait_efo [type=value_error, input_value={'pgs_id': None, 'pgp_id'...target_build': 'GRCh37'}, input_type=dict]
      ...
    """

    pgs_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description="A comma separated string of PGS Catalog polygenic score identifers",
        ),
    ]
    pgp_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description="A comma separated string of PGS Catalog publication identifiers",
        ),
    ]
    trait_efo: Annotated[
        Optional[str],
        Field(
            default=None,
            description="A comma separated string of experimental factor ontology traits (used to query the PGS Catalog API)",
        ),
    ]
    target_build: Annotated[GenomeBuild, Field(description="Build of target genomes")]
    format: Annotated[
        SamplesheetFormat,
        Field(
            description="What format is the samplesheet in?",
            default=SamplesheetFormat.JSON,
        ),
    ]

    @field_validator("pgs_id", "pgp_id", "trait_efo", mode="before")
    @classmethod
    def parse_pgs_requests(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            if v.strip() == "":
                v = None
        return v

    @model_validator(mode="after")
    def check_calculation_requests(self) -> Self:
        if all(getattr(self, x) is None for x in ("pgs_id", "pgp_id", "trait_efo")):
            raise ValueError("Missing all pgs_id, pgp_id, or trait_efo")
        return self


class SecretKeyDetails(BaseModel):
    """Secret key metadata, used to call the key handler service

    >>> SecretKeyDetails(**{"secret_id": "81D5C400-21B4-4E88-8208-8D64C9920283", "secret_id_version": "1"})
    SecretKeyDetails(secret_id=UUID('81d5c400-21b4-4e88-8208-8d64c9920283'), secret_id_version='1')
    """

    secret_id: Annotated[UUID4, Field(description="UUIDv4 of secret key")]
    secret_id_version: Annotated[
        str, Field(description="Version of secret key", coerce_numbers_to_str=True)
    ]


class TargetGenomes(RootModel):
    root: list[TargetGenome]

    def __iter__(self):
        for item in self.root:
            yield item


class PGSJobParams(BaseModel):
    id: Annotated[str, Field(description="PGS Job ID", pattern="INTP.*")]
    target_genomes: Annotated[
        TargetGenomes,
        Field(
            description="Equivalent to a PGS Catalog Calculator samplesheet",
        ),
    ]
    nxf_params_file: Annotated[
        PGSParams,
        Field(description="Nextflow parameters for the PGS Catalog Calculator"),
    ]


class JobRequest(BaseModel):
    """
    >>> import json
    >>> testmsg = pathlib.Path(__file__).parent.parent.parent / "tests" / "data" / "test.json"
    >>> with open(testmsg) as f:
    ...     d = json.load(f)
    >>> JobRequest(**d)  # doctest: +ELLIPSIS
    JobRequest(globus_details=GlobusConfig(dir_path_on_guest_collection...
    """

    globus_details: Annotated[
        GlobusConfig,
        Field(description="Globus file handler parameters for data transfer"),
    ]
    pipeline_param: Annotated[
        PGSJobParams,
        Field(description="PGS Catalog Calculator parameters (i.e. nextflow runtime)"),
    ]
    secret_key_details: Annotated[
        SecretKeyDetails,
        Field(
            description="crypt4gh secret key metadata, used by the file handler to query the key handler service"
        ),
    ]
