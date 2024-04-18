import asyncio
import pathlib
import shutil
import tempfile
from contextlib import asynccontextmanager
import datetime

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException
import logging
import shelve

from starlette import status

from .job import PolygenicScoreJob
from .jobmodels import JobModel
from .logmodels import LogMessage, LogEvent, MonitorMessage, SummaryTrace

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SHELF_LOCK = asyncio.Lock()
CLIENT = httpx.AsyncClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tempdir = tempfile.mkdtemp()
    Config.SHELF_PATH = pathlib.Path(tempdir) / "shelve.dat"
    logger.info(f"Created temporary shelf file {Config.SHELF_PATH}")
    yield
    shutil.rmtree(tempdir)
    logger.info(f"Cleaned up {Config.SHELF_PATH}")
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
        with shelve.open(Config.SHELF_PATH) as db:
            db[id] = job_instance


async def timeout_job(job_id: str):
    """Background task to check if a job is still on the shelf after a timeout.

    If it is, trigger the error state, which will force a cleanup and notify the backend"""
    logger.info(f"Async timeout for {Config.TIMEOUT_SECONDS}s started for {job_id}")
    await asyncio.sleep(Config.TIMEOUT_SECONDS)

    async with SHELF_LOCK:
        with shelve.open(Config.SHELF_PATH) as db:
            job_instance: PolygenicScoreJob = db.get(job_id, None)

    if job_instance is not None:
        logger.warning(f"{job_id} timed out, triggering error state")
        message = MonitorMessage(
            run_name=job_id, utc_time=datetime.datetime.now(), event=LogEvent.ERROR
        )
        await update_job_state("error", message=message, delete=True)
    else:
        logger.info(f"Timeout for {job_id} expired (it succeeded or failed)")


@app.post("/launch", status_code=status.HTTP_201_CREATED)
async def launch(job: JobModel, background_tasks: BackgroundTasks):
    with shelve.open(Config.SHELF_PATH) as db:
        if job.pipeline_param.id in db:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job {job.pipeline_param.id} already exists",
            )

    background_tasks.add_task(launch_job, job)
    background_tasks.add_task(timeout_job, job.pipeline_param.id)
    return {"id": job.pipeline_param.id}


@app.post("/monitor", status_code=status.HTTP_200_OK)
async def monitor(message: LogMessage):
    match message.event:
        case LogEvent.STARTED:
            message = MonitorMessage(
                run_name=message.runName, utc_time=message.utcTime, event=message.event
            )
            # await update_job_state("deploy", message)
        case LogEvent.COMPLETED:
            message = MonitorMessage(
                run_name=message.runName, utc_time=message.utcTime, event=message.event
            )
            await update_job_state("succeed", message, delete=True)
        case LogEvent.ERROR:
            # trace is only generated for this event
            if message.trace is not None:
                trace = SummaryTrace(
                    trace_exit=message.trace["exit"],
                    trace_name=message.trace["process"],
                )
            else:
                trace = None
            message = MonitorMessage(
                run_name=message.runName,
                utc_time=message.utcTime,
                event=message.event,
                trace=trace,
            )
            await update_job_state("error", message, delete=True)


async def update_job_state(state, message: MonitorMessage, delete=False):
    with shelve.open(Config.SHELF_PATH) as db:
        job_instance: PolygenicScoreJob = db[message.run_name]

    logger.info(f"Triggering state {state}")
    await job_instance.trigger(state, client=CLIENT, message=message)

    async with SHELF_LOCK:
        with shelve.open(Config.SHELF_PATH) as db:
            if not delete:
                db[message.run_name] = job_instance
            else:
                db.pop(message.run_name)


class Config:
    SHELF_PATH = None
    TIMEOUT_SECONDS = 60 * 60 * 24
