import json
import logging
import signal
import sys
import threading
import time
from typing import Optional

import pydantic
import schedule

from pyvatti.config import settings
from pyvatti.db import SqliteJobDatabase

from kafka import KafkaConsumer

from pyvatti.job import PolygenicScoreJob
from pyvatti.jobstates import States
from pyvatti.messagemodels import JobRequest

logger = logging.getLogger()
logger.setLevel(logging.INFO)

JOB_DATABASE = SqliteJobDatabase(settings.SQLITE_DB_PATH)
SHUTDOWN_EVENT = threading.Event()


def check_job_state() -> None:
    """Check the state of the job on the Seqera Platform and update active jobs in the database if the state has changed

    Created (resources requested) -> Deployed (running) -> Succeeded / Failed
    """
    # active jobs: haven't succeeded or failed
    jobs: list[PolygenicScoreJob] = JOB_DATABASE.get_active_jobs()
    logger.info(f"{len(jobs)} active jobs found")
    for job in jobs:
        logger.info(f"Checking {job=} state")
        job_state: Optional[States] = job.get_job_state()
        if job_state is not None:
            if job_state != job.state:
                logger.info(
                    f"Job state change detected: From {job_state} to {job.state}"
                )
                # get the trigger from the destination state enum
                # e.g. "deploy" -> "succeed" / "error"
                trigger: str = PolygenicScoreJob.state_trigger_map[job_state]
                job.trigger(trigger)
                JOB_DATABASE.update_job(job)


def kafka_consumer() -> None:
    consumer = KafkaConsumer(
        topic=settings.KAFKA_CONSUMER_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        enable_auto_commit=False,
        value_deserializer=lambda m: json.loads(m.decode("ascii")),
    )

    # want to avoid partially processing a commit if the thread is terminated
    try:
        for message in consumer:
            if SHUTDOWN_EVENT.is_set():
                logger.info("Shutdown event received")
                break
            process_message(message.value)
            consumer.commit()
    finally:
        logger.info("Closing kafka connection")
        consumer.close()


def process_message(msg_value: dict) -> None:
    """Each kafka message:

    - Gets validated by the pydantic model JobRequest
    - Instantiate a PolygenicScoreJob object
    - Trigger the "create" state where compute resources are provisioned
    - Adds the job object to the database
    """
    try:
        job_message: JobRequest = JobRequest(**msg_value)
        job: PolygenicScoreJob = PolygenicScoreJob(
            intp_id=job_message.pipeline_param.id
        )
        PolygenicScoreJob.create(job_model=job_message)
        JOB_DATABASE.insert_job(job)
    except pydantic.ValidationError as e:
        logger.critical("Job request message validation failed")
        logger.critical(f"{e}")


def graceful_shutdown(*args):
    logger.info("Shutdown signal received")
    SHUTDOWN_EVENT.set()


def main():
    # handle shutdowns gracefully (partially processing a job request would be bad)
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # create the job database if it does not exist (if it exists, nothing happens here)
    JOB_DATABASE.create()

    # consume new kafka messages and insert them into the database in a background thread
    consumer_thread: threading.Thread = threading.Thread(
        target=kafka_consumer, daemon=True
    )
    consumer_thread.start()

    # check for timed out jobs with schedule
    schedule.every(15).minutes.do(JOB_DATABASE.timeout_jobs)

    # check if job states have changed and produce new messages
    schedule.every(1).minutes.do(check_job_state)

    # run scheduled tasks:
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
