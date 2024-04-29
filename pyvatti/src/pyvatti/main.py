import asyncio
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, BackgroundTasks, HTTPException
import logging
import shelve

from starlette import status

from .job import PolygenicScoreJob, update_job_state
from .jobmodels import JobModel
from .config import settings
from . import CLIENT, SHELF_LOCK, SHELF_PATH, TEMP_DIR
from .monitor import API_ROOT, get_headers, SeqeraLog


logger = logging.getLogger()
logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

    async with SHELF_LOCK:
        with shelve.open(SHELF_PATH) as db:
            for job_id, job_instance in db.items():
                logger.warning(f"{job_id} active while shutting down, erroring")
                await update_job_state(workflow_id=job_id, trigger="error")

    shutil.rmtree(TEMP_DIR)
    logger.info(f"Cleaned up {SHELF_PATH}")

    # close the connection pool
    await CLIENT.aclose()
    logger.info("Closed httpx thread pool")


app = FastAPI(lifespan=lifespan)


async def launch_job(job_model: JobModel):
    """Background task to create a job, trigger create, and store the job on the shelf"""
    id: str = job_model.pipeline_param.id
    job_instance: PolygenicScoreJob = PolygenicScoreJob(intp_id=id)

    await job_instance.create(job_model=job_model, client=CLIENT)

    async with SHELF_LOCK:
        with shelve.open(SHELF_PATH) as db:
            db[id] = job_instance


@app.post("/launch", status_code=status.HTTP_201_CREATED)
async def launch(job: JobModel, background_tasks: BackgroundTasks):
    with shelve.open(SHELF_PATH) as db:
        if job.pipeline_param.id in db:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job {job.pipeline_param.id} already exists",
            )

    background_tasks.add_task(launch_job, job)
    background_tasks.add_task(monitor_job, job.pipeline_param.id)
    return {"id": job.pipeline_param.id}


async def monitor_job(workflow_id):
    """Monitor jobs using the Seqera API and update internal job state

    Updating job states will trigger notifications and the destruction of resources"""
    params = {
        "workspaceId": settings.TOWER_WORKSPACE,
        "search": f"{settings.NAMESPACE}-{workflow_id}",
    }
    log = None
    time_started = datetime.now(timezone.utc)

    while True:
        await asyncio.sleep(settings.POLL_INTERVAL)

        time_s: int = (datetime.now(timezone.utc) - time_started).seconds
        if time_s > settings.TIMEOUT_SECONDS:
            logger.warning(f"Timeout exceeded for {workflow_id}")
            await update_job_state(workflow_id=workflow_id, trigger="error")
            break

        logger.info(f"Polling API {workflow_id}")
        response = await CLIENT.get(
            f"{API_ROOT}/workflow", headers=get_headers(), params=params
        )
        new_log: SeqeraLog = SeqeraLog.from_response(response)

        if new_log is None:
            logger.info(f"No log found yet for {workflow_id}")
            continue

        if log != new_log:
            logger.info("Job state update detected")
            log = new_log
            job_state = log.get_job_state()
            await update_job_state(trigger=job_state, workflow_id=workflow_id)
            if job_state == "error" or job_state == "succeed":
                break

    logger.info(f"Monitoring stopped for {workflow_id}")
