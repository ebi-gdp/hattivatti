"""This module contains classes to handle the resources needed to run a job"""

import abc
import asyncio
import logging
import tempfile

import yaml
from google.cloud import storage

from pyvatti.messagemodels import JobRequest
from pyvatti.helm import render_template
from pyvatti.config import settings
from pyvatti.jobstates import States

logger = logging.getLogger(__name__)


class ResourceHandler(abc.ABC):
    @abc.abstractmethod
    def __init__(self, intp_id: str):
        self.intp_id = intp_id

    @abc.abstractmethod
    async def create_resources(self, job_model: JobRequest):
        """Create the compute resources needed to run a job

        For example:
        - Create storage buckets
        - Render a helm chart or a SLURM template
        """
        ...

    @abc.abstractmethod
    async def destroy_resources(self, state):
        """Destroy the created resources

        Cleaning up properly is very important to keep sensitive data safe

        In the error state all buckets should be cleared up if they weren't already present
        """
        ...


class DummyResourceHandler(ResourceHandler):
    """A dummy resource handler that doesn't do anything for testing"""

    def __init__(self, intp_id: str):
        self.intp_id = intp_id

    def create_resources(self, job_model: JobRequest):
        pass

    def destroy_resources(self, state):
        pass


class GoogleResourceHandler(ResourceHandler):
    def __init__(
        self,
        intp_id,
        project_id="prj-ext-dev-intervene-413412",
        location="europe-west2",
    ):
        super().__init__(intp_id=intp_id.lower())
        self.project_id = project_id
        self._bucket_root = f"{str(settings.NAMESPACE)}-{self.intp_id}"
        self._work_bucket = f"{self._bucket_root}-work"
        self._results_bucket = f"{self._bucket_root}-results"
        self._location = location
        self._work_bucket_existed_on_create = False
        self._results_bucket_existed_on_create = False
        self._helm_installed = False

    async def create_resources(self, job_model: JobRequest):
        """Create some resources to run the job, including:

        - Create a bucket with lifecycle management
        - Render a helm chart
        - Run helm install
        """

        self.make_buckets(job_model=job_model)
        try:
            await helm_install(
                job_model=job_model,
                work_bucket_path=self._work_bucket,
                results_bucket_path=self._results_bucket,
            )
        except ValueError:
            self._helm_installed = False
        else:
            self._helm_installed = True

    async def destroy_resources(self, state):
        if self._helm_installed:
            await helm_uninstall(self.intp_id)

        if state == States.FAILED:
            self._delete_buckets(results=True)
        else:
            self._delete_buckets(results=False)

    def make_buckets(self, job_model: JobRequest):
        """Create the buckets needed to run the job"""
        self._make_work_bucket(job_model)
        self._make_results_bucket(job_model)

    def _make_work_bucket(self, job_model: JobRequest):
        """Unfortunately google cloud storage doesn't support async

        The work bucket has much stricter lifecycle policies than the results bucket
        """
        client = storage.Client(project=self.project_id)
        bucket: storage.Bucket = client.bucket(self._work_bucket)

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
        iam.uniform_bucket_level_access_enabled = True

        bucket.create(location=self._location)

    def _make_results_bucket(self, job_model: JobRequest):
        """Unfortunately the google storage library doesn't support async"""
        client = storage.Client(project=self.project_id)
        bucket: storage.Bucket = client.bucket(self._results_bucket)

        if bucket.exists():
            logger.critical(f"Bucket {self._results_bucket} exists!")
            self._results_bucket_existed_on_create = True
            raise FileExistsError

        # results stay live for 7 days
        bucket.add_lifecycle_delete_rule(age=7)
        bucket.add_lifecycle_abort_incomplete_multipart_upload_rule(age=1)

        # don't soft delete, it's annoying
        soft_policy = storage.bucket.SoftDeletePolicy(bucket)
        soft_policy.retention_duration_seconds = 0
        iam = storage.bucket.IAMConfiguration(bucket=bucket)
        iam.public_access_prevention = "enforced"
        iam.uniform_bucket_level_access_enabled = True

        bucket.create(location=self._location)

    def _delete_buckets(self, results=False):
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

        if results:
            results_bucket = client.get_bucket(self._results_bucket)
            logger.info(f"Deleting {results_bucket}")
            results_bucket.delete(force=True)


async def helm_install(
    job_model: JobRequest, work_bucket_path: str, results_bucket_path: str
):
    release_name: str = job_model.pipeline_param.id.lower()
    template = render_template(
        job_model,
        work_bucket_path=work_bucket_path,
        results_bucket_path=results_bucket_path,
    )

    with tempfile.NamedTemporaryFile(mode="wt") as temp_f:
        yaml.dump(template, temp_f)
        cmd = f"helm install {release_name} {settings.HELM_CHART_PATH} -n {str(settings.NAMESPACE)} -f {temp_f.name}"
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.critical(f"{stderr.decode()}")
        raise ValueError("helm install failed")
    else:
        logger.info("helm install OK")


async def helm_uninstall(release_name: str):
    cmd = f"helm uninstall --namespace {str(settings.NAMESPACE)} {release_name.lower()}"

    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.critical(f"{stderr.decode()}")
        raise ValueError("helm uninstall failed")
    else:
        logger.info(f"helm uninstall {release_name} OK")
