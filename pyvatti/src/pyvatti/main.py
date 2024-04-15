from fastapi import FastAPI
import logging

from .job import PolygenicScoreJob
from .jobmodels import JobModel
from .logmodels import LogMessage, LogEvent, MonitorMessage

app = FastAPI()

logger = logging.getLogger()
# a dict is good enough for now
jobs: dict[str:PolygenicScoreJob] = {}


@app.post("/launch", status_code=201)
async def launch(job: JobModel):
    job_instance: PolygenicScoreJob = PolygenicScoreJob(id=job.pipeline_param.id)
    job_instance.create()
    jobs[job.pipeline_param.id] = job_instance
    return {"id": job.pipeline_param.id}


@app.post("/monitor", status_code=200)
async def monitor(message: LogMessage):
    match message.event:
        case LogEvent.STARTED:
            message = MonitorMessage(
                run_name=message.runName, utc_time=message.utcTime, event=message.event
            )
            # TODO: pass message to succeed function
            jobs[message.runName].deploy()
        case LogEvent.COMPLETED:
            message = MonitorMessage(
                run_name=message.runName, utc_time=message.utcTime, event=message.event
            )
            job: PolygenicScoreJob = jobs[message.runName]
            # TODO: pass message to succeed function
            job.succeed()
            jobs.pop(message.runName)
        case LogEvent.ERROR:
            message = MonitorMessage(
                run_name=message.runName,
                utc_time=message.utcTime,
                event=message.event,
                trace=message.trace,
            )
            job: PolygenicScoreJob = jobs[message.runName]
            # TODO: pass message to succeed function
            job.error()
            jobs.pop(message.runName)
