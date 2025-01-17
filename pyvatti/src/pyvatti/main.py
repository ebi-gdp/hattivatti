import json
import logging
import threading
import time
from typing import Optional

import pydantic
import schedule

from pyvatti.config import Settings
from pyvatti.db import SqliteJobDatabase

from kafka import KafkaConsumer

from pyvatti.pgsjob import PolygenicScoreJob  # type: ignore[attr-defined]
from pyvatti.jobstates import States
from pyvatti.messagemodels import JobRequest

logger = logging.getLogger()
logger.setLevel(logging.INFO)
kafka_logger = logging.getLogger("kafka")
kafka_logger.setLevel(logging.WARNING)


def check_job_state(db: SqliteJobDatabase, settings: Settings) -> None:
    """Check the state of the job on the Seqera Platform and update active jobs in the database if the state has changed

    Created (resources requested) -> Deployed (running) -> Succeeded / Failed
    """
    # active jobs: haven't succeeded or failed
    jobs: list[PolygenicScoreJob] = db.get_active_jobs()
    if jobs:
        logger.info(f"{len(jobs)} active jobs found")
    else:
        return

    for job in jobs:
        logger.info(f"Checking {job=} state")
        job_state: Optional[States] = job.get_job_state(
            namespace=settings.NAMESPACE,
            tower_token=settings.TOWER_TOKEN,
            tower_workspace=settings.TOWER_WORKSPACE,
        )
        if job_state is not None:
            if job_state != job.state:
                logger.info(
                    f"Job state change detected: From {job_state} to {job.state}"
                )
                # get the trigger from the destination state enum
                # e.g. "deploy" -> "succeed" / "error"
                trigger: str = PolygenicScoreJob.state_trigger_map[job_state]
                job.trigger(trigger)
                db.update_job(job)


def kafka_consumer(
    db: SqliteJobDatabase,
    topic: str,
    bootstrap_server_host: str,
    bootstrap_server_port: int,
    settings: Settings,
) -> None:
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=f"{bootstrap_server_host}:{bootstrap_server_port}",
        enable_auto_commit=False,
    )
    logger.info("Listening for kafka messages")

    for message in consumer:
        logger.info("Message read from kafka consumer")

        while len(db.get_active_jobs()) > settings.MAX_CONCURRENT_JOBS:
            time.sleep(1)

        try:
            decoded_msg = json.loads(message.value.decode("utf-8"))
            process_message(msg_value=decoded_msg, db=db, settings=settings)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON, skipping message")
            logger.warning(f"Message {message.value} caused exception: {e}")
        finally:
            consumer.commit()


def process_message(msg_value: dict, db: SqliteJobDatabase, settings: Settings) -> None:
    """Each kafka message:

    - Gets validated by the pydantic model JobRequest
    - Instantiate a PolygenicScoreJob object
    - Trigger the "create" state where compute resources are provisioned
    - Adds the job object to the database
    """
    try:
        job_message: JobRequest = JobRequest(**msg_value)
        job: PolygenicScoreJob = PolygenicScoreJob(
            intp_id=job_message.pipeline_param.id, settings=settings
        )
        job.trigger("create", job_model=job_message)
        db.insert_job(job)
    except pydantic.ValidationError as e:
        logger.critical("Job request message validation failed, skipping job")
        logger.critical(f"{e}")
    except Exception as e:
        logger.critical(f"Something went wildly wrong, skipping job: {e}")


def main() -> None:
    # create the job database if it does not exist (if it exists, nothing happens here)
    settings = Settings()
    db = SqliteJobDatabase(str(settings.SQLITE_DB_PATH))

    db.create()

    # consume new kafka messages and insert them into the database in a background thread
    if settings.KAFKA_BOOTSTRAP_SERVER is None:
        raise ValueError("KAFKA_BOOTSTRAP_SERVER is mandatory but not set")

    consumer_thread: threading.Thread = threading.Thread(
        target=kafka_consumer,
        daemon=True,
        kwargs={
            "db": db,
            "topic": settings.KAFKA_CONSUMER_TOPIC,
            "bootstrap_server_host": settings.KAFKA_BOOTSTRAP_SERVER.host,
            "bootstrap_server_port": settings.KAFKA_BOOTSTRAP_SERVER.port,
            "settings": settings,
        },
    )
    consumer_thread.start()

    # check for timed out jobs with schedule
    schedule.every(1).minutes.do(
        db.timeout_jobs, timeout_seconds=settings.TIMEOUT_SECONDS
    )

    # check if job states have changed and produce new messages
    schedule.every(settings.POLL_INTERVAL).seconds.do(
        check_job_state, db=db, settings=settings
    )

    # run scheduled tasks:
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
