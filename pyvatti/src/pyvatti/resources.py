"""This module contains classes to handle the resources needed to run a job"""

import abc
import asyncio
import logging


from google.cloud import storage

from .jobmodels import JobModel

logger = logging.getLogger(__name__)


class ResourceHandler(abc.ABC):
    @abc.abstractmethod
    def create_resources(self, job_model: JobModel):
        """Create the compute resources needed to run a job

        For example:
        - Create storage buckets
        - Render a helm chart or a SLURM template
        """
        ...

    @abc.abstractmethod
    def destroy_resources(self):
        """Destroy the created resources

        Cleaning up properly is very important to keep sensitive data safe
        """
        ...


class GoogleResourceHandler(ResourceHandler):
    dry_run = False

    async def create_resources(self, job_model: JobModel):
        """Create some resources to run the job, including:

        - Create a bucket with lifecycle management
        - Render a helm chart
        - Run helm install
        """
        storage_client = storage.Client(project="prj-ext-dev-intervene-413412")
        bucket: storage.bucket.Bucket = storage_client.bucket("intervene-test-bucket")
        bucket.storage.bucket.SoftDeletePolicy(bucket, retention_duration_seconds=0)
        bucket.add_lifecycle_delete_rule(
            age=1,
            matches_suffix=[
                ".vcf",
                ".pgen",
                ".pvar",
                ".psam",
                ".bim",
                ".bed",
                ".fam",
                ".zst",
                ".gz",
            ],
        )
        bucket.create(location="europe-west2")
        storage.bucket.SoftDeletePolicy(bucket, retention_duration_seconds=0)
        storage_client.create_bucket(bucket, location="europe-west2")

        await helm_install(job_model=job_model)

    async def destroy_resources(self):
        await helm_uninstall(
            namespace="intervene-dev", release_name="helmvatti-1712756412"
        )


async def helm_install(job_model: JobModel):
    if GoogleResourceHandler.dry_run:
        logger.info("dry run enabled")
        dry_run = "--dry-run"
    else:
        dry_run = ""

    # TODO: add chart path and values file
    cmd = "helm"  # install -n intervene-dev {dry_run}"
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.critical(f"{stderr.decode()}")
        raise ValueError("helm install failed")
    else:
        logger.info("helm install OK")


async def helm_render(job_model: JobModel):
    pass


async def helm_uninstall(release_name: str, namespace: str):
    if GoogleResourceHandler.dry_run:
        dry_run = "--dry-run"
    else:
        dry_run = ""

    cmd = f"helm uninstall --namespace {namespace} {dry_run} {release_name}"

    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.critical(f"{stderr.decode()}")
        raise ValueError("helm uninstall failed")
    else:
        logger.info(f"helm uninstall {release_name} OK")
