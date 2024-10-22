import json
import logging
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
kafka_logger = logging.getLogger("kafka")
kafka_logger.setLevel(logging.WARNING)

JOB_DATABASE = SqliteJobDatabase(settings.SQLITE_DB_PATH)


def check_job_state() -> None:
    """Check the state of the job on the Seqera Platform and update active jobs in the database if the state has changed

    Created (resources requested) -> Deployed (running) -> Succeeded / Failed
    """
    # active jobs: haven't succeeded or failed
    jobs: Optional[list[PolygenicScoreJob]] = JOB_DATABASE.get_active_jobs()
    if jobs is not None:
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
        settings.KAFKA_CONSUMER_TOPIC,
        bootstrap_servers=f"{settings.KAFKA_BOOTSTRAP_SERVER.host}:{settings.KAFKA_BOOTSTRAP_SERVER.port}",
        enable_auto_commit=False,
    )
    logger.info("Listening for kafka messages")

    # TODO: want to avoid partially processing a commit if the thread is terminated
    for message in consumer:
        logger.info("Message read from kafka consumer")
        try:
            decoded_msg = json.loads(message.value.decode("utf-8"))
            process_message(decoded_msg)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON, skipping message")
            logger.warning(f"Message {message.value} caused exception: {e}")
            continue


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
        logger.critical("Job request message validation failed, skipping job")
        logger.critical(f"{e}")
    except Exception as e:
        logger.critical(f"Something went wildly wrong, skipping job: {e}")


def main():
    # create the job database if it does not exist (if it exists, nothing happens here)
    JOB_DATABASE.create()

    # consume new kafka messages and insert them into the database in a background thread
    consumer_thread: threading.Thread = threading.Thread(target=kafka_consumer)
    consumer_thread.start()

    # check for timed out jobs with schedule
    schedule.every(1).minutes.do(JOB_DATABASE.timeout_jobs)

    # check if job states have changed and produce new messages
    schedule.every(settings.POLL_INTERVAL).seconds.do(check_job_state)

    # run scheduled tasks:
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
