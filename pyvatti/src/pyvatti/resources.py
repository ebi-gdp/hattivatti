"""This module contains classes to handle the resources needed to run a job"""

import abc
import asyncio
import logging


from google.cloud import storage

from .jobmodels import JobModel

logger = logging.getLogger(__name__)


class ResourceHandler(abc.ABC):
    @abc.abstractmethod
    def __init__(self, intp_id: str):
        self.intp_id = intp_id

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

    def __init__(
        self,
        intp_id,
        project_id="prj-ext-dev-intervene-413412",
        location="europe-west2",
    ):
        super().__init__(intp_id=intp_id.lower())
        self.project_id = project_id
        self._work_bucket = f"{self.intp_id}-work"
        self._results_bucket = f"{self.intp_id}-results"
        self._location = location
        self._work_bucket_existed_on_create = False

    async def create_resources(self, job_model: JobModel):
        """Create some resources to run the job, including:

        - Create a bucket with lifecycle management
        - Render a helm chart
        - Run helm install
        """

        self.make_buckets(job_model=job_model)
        await helm_install(job_model=job_model)

    async def destroy_resources(self):
        # TODO: if the bucket exists already, we shouldn't destroy it in the error state
        await helm_uninstall(
            namespace="intervene-dev", release_name="helmvatti-1712756412"
        )
        self._delete_work_bucket()

    def make_buckets(self, job_model: JobModel):
        """Create the buckets needed to run the job"""
        self._make_work_bucket(job_model)
        self._make_results_bucket(job_model)

    def _make_work_bucket(self, job_model: JobModel):
        """Unfortunately google cloud storage doesn't support async

        The work bucket has much stricter lifecycle policies than the results bucket
        """
        client = storage.Client(project=self.project_id)
        bucket: storage.bucket.Bucket = client.bucket(self._work_bucket)

        if bucket.exists():
            logger.critical(f"Bucket {self._work_bucket} exists!")
            logger.critical(
                "This bucket won't get cleaned up automatically by the error state"
            )
            self._work_bucket_existed_on_create = True
            raise FileExistsError

        bucket.add_lifecycle_abort_incomplete_multipart_upload_rule(age=1)

        # these file suffixes are guaranteed to contain sensitive data
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

        # this is so dumb!
        # if you init the SoftDeletePolicy with retention_duration_seconds then it never patches the bucket soft_delete_policy property
        # the soft_delete_policy property has no setter
        # instead init a minimal SoftDeletePolicy, then use the retention_duration_seconds property to make sure the setter is called and patches the bucket config
        # took me way too long to figure this out
        soft_policy = storage.bucket.SoftDeletePolicy(bucket)
        soft_policy.retention_duration_seconds = 0
        iam = storage.bucket.IAMConfiguration(bucket=bucket)
        iam.public_access_prevention = "enforced"

        bucket.create(location=self._location)

    def _make_results_bucket(self, job_model: JobModel):
        """Unfortunately the google storage library doesn't support async"""
        client = storage.Client(project=self.project_id)
        bucket: storage.bucket.Bucket = client.bucket(self._results_bucket)

        if bucket.exists():
            logger.critical(f"Bucket {self._results_bucket} exists!")
            raise FileExistsError

        # results stay live for 7 days
        bucket.add_lifecycle_delete_rule(age=7)
        bucket.add_lifecycle_abort_incomplete_multipart_upload_rule(age=1)

        # don't soft delete, it's annoying
        soft_policy = storage.bucket.SoftDeletePolicy(bucket)
        soft_policy.retention_duration_seconds = 0
        iam = storage.bucket.IAMConfiguration(bucket=bucket)
        iam.public_access_prevention = "enforced"

        bucket.create(location=self._location)

    def _delete_work_bucket(self):
        # TODO: what if this is slow? it's not async!
        if self._work_bucket_existed_on_create:
            # don't delete a bucket that existed before the job was created
            # otherwise a bad job will interfere with an existing good job
            logger.warning(
                "Work bucket existed during creation, so not deleting it to avoid modifying existing jobs"
            )
            return

        client = storage.Client(project=self.project_id)
        bucket = client.get_bucket(self._work_bucket)

        if not bucket.exists():
            logger.info("work bucket not found, so not deleting")
            return

        blobs = list(bucket.list_blobs())
        if len(blobs) > 256:
            logger.warning(f"Deleting a very big bucket: {len(blobs)} items")
            for blob in blobs:
                blob.delete()

        logger.info(f"Deleting {bucket}")
        bucket.delete(force=True)


async def helm_install(job_model: JobModel):
    if GoogleResourceHandler.dry_run:
        dry_run = "--dry-run"
        logger.info("{dry_run} enabled")
    else:
        dry_run = ""

    # TODO: add chart path and values file
    cmd = f"helm # install -n intervene-dev {dry_run}"
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
        logger.info(f"{dry_run} enabled")
    else:
        dry_run = ""

    cmd = f"helm # uninstall --namespace {namespace} {dry_run} {release_name}"

    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.critical(f"{stderr.decode()}")
        raise ValueError("helm uninstall failed")
    else:
        logger.info(f"helm uninstall {release_name} OK")
