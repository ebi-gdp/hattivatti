import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone, timedelta
from queue import SimpleQueue
from typing import Optional

import pydantic
import schedule
from google.cloud import storage

from pyvatti.config import Settings
from pyvatti.db import SqliteJobDatabase

from kafka import KafkaConsumer, errors, KafkaProducer

from pyvatti.notifymodels import SeqeraLog, BackendStatusMessage
from pyvatti.pgsjob import PolygenicScoreJob  # type: ignore[attr-defined]
from pyvatti.jobstates import States
from pyvatti.messagemodels import JobRequest

logger = logging.getLogger()
logger.setLevel(logging.INFO)
kafka_logger = logging.getLogger("kafka")
kafka_logger.setLevel(logging.WARNING)

KAFKA_CONSUMER_NOT_OK = threading.Event()
KAFKA_PRODUCER_NOT_OK = threading.Event()


def check_job_state(
    db: SqliteJobDatabase, settings: Settings, queue: SimpleQueue
) -> None:
    """Check the state of the job on the Seqera Platform and update active jobs in the database if the state has changed

    Created (resources requested) -> Deployed (running) -> Succeeded / Failed
    """
    # active jobs: haven't succeeded or failed
    jobs: list[PolygenicScoreJob] = db.get_active_jobs()
    if jobs:
        logger.info(f"{len(jobs)} active jobs found")
    else:
        return

    seqera_api = {
        "namespace": settings.NAMESPACE,
        "tower_token": settings.TOWER_TOKEN,
        "tower_workspace": settings.TOWER_WORKSPACE,
    }

    for job in jobs:
        logger.info(f"Checking {job=} state")
        job_state: Optional[States] = job.get_job_state(**seqera_api)

        if job_state is not None:
            if job_state != job.state:
                logger.info(
                    f"Job state change detected: From {job_state} to {job.state}"
                )

                if job_state == States.FAILED:
                    log: SeqeraLog = job.get_seqera_log(**seqera_api)
                    # (there's definitely an API response, job_state was OK!)
                    job.trace_exit = log.exitStatus
                    job.trace_name = log.errorReport

                # get the trigger from the destination state enum
                # e.g. "deploy" -> "succeed" / "error"
                trigger: str = PolygenicScoreJob.state_trigger_map[job_state]
                job.trigger(trigger, queue=queue)
                db.update_job(job)


def kafka_consumer(
    db: SqliteJobDatabase,
    topic: str,
    host: str,
    port: int,
    settings: Settings,
) -> None:
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=f"{host}:{port}",
            enable_auto_commit=False,
            group_id="hattivatti",
        )
        logger.info("Listening for kafka messages")

        for message in consumer:
            logger.info("Message read from kafka consumer")

            while len(db.get_active_jobs()) >= settings.MAX_CONCURRENT_JOBS:
                time.sleep(1)

            try:
                decoded_msg = json.loads(message.value.decode("utf-8"))
                process_message(msg_value=decoded_msg, db=db, settings=settings)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON, skipping message")
                logger.warning(f"Message {message.value} caused exception: {e}")
            finally:
                consumer.commit()
    except errors.KafkaError as e:
        logger.critical(f"Kafka error: {e}")
        KAFKA_CONSUMER_NOT_OK.set()


def kafka_producer(
    topic: str, host: str, port: int, msg_queue: SimpleQueue[BackendStatusMessage]
) -> None:
    producer = KafkaProducer(
        bootstrap_servers=[f"{host}:{port}"],
        value_serializer=lambda v: v.encode("utf-8"),
    )

    while True:
        try:
            msg: BackendStatusMessage = msg_queue.get(block=False, timeout=1)
        except queue.Empty:
            time.sleep(1)
        except errors.KafkaError as e:
            logger.critical(f"Kafka error: {e}")
            KAFKA_PRODUCER_NOT_OK.set()
        else:
            producer.send(topic, msg.model_dump_json())
            logger.info(f"{msg=} sent to pipeline-notify topic")


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


def start_consumer_thread(
    *, db: SqliteJobDatabase, topic: str, host: str, port: int, settings: Settings
) -> None:
    """Start a thread to consume messages from the pipeline-kaunch topic"""
    logger.info("Starting kafka consumer thread")
    KAFKA_CONSUMER_NOT_OK.clear()
    threading.Thread(
        target=kafka_consumer,
        daemon=True,
        kwargs={
            "db": db,
            "topic": topic,
            "host": host,
            "port": port,
            "settings": settings,
        },
    ).start()


def start_producer_thread(
    *, topic: str, host: str, port: int, msg_queue: SimpleQueue[BackendStatusMessage]
) -> None:
    """Start a thread to read notification messages from the queue and send them to pipeline-notify"""
    logger.info("Starting kafka producer thread")
    KAFKA_PRODUCER_NOT_OK.clear()
    threading.Thread(
        target=kafka_producer,
        daemon=True,
        kwargs={
            "topic": topic,
            "host": host,
            "port": port,
            "msg_queue": msg_queue,
        },
    ).start()


def main() -> None:
    kafka_fail_count: int = 0
    # create the job database if it does not exist (if it exists, nothing happens here)
    settings = Settings()  # type: ignore
    db = SqliteJobDatabase(str(settings.SQLITE_DB_PATH))
    db.create()

    if settings.KAFKA_PRODUCER_TOPIC is None or settings.KAFKA_CONSUMER_TOPIC is None:
        raise TypeError("Missing mandatory kafka argument")
    else:
        consumer_topic: str = settings.KAFKA_CONSUMER_TOPIC
        producer_topic: str = settings.KAFKA_PRODUCER_TOPIC

    if settings.KAFKA_BOOTSTRAP_SERVER is None:
        raise TypeError("Missing mandatory kafka argument")

    if (
        settings.KAFKA_BOOTSTRAP_SERVER.host is None
        or settings.KAFKA_BOOTSTRAP_SERVER.port is None
    ):
        raise TypeError("Missing mandatory kafka argument")

    kafka_host: str = settings.KAFKA_BOOTSTRAP_SERVER.host
    kafka_port: int = settings.KAFKA_BOOTSTRAP_SERVER.port

    # consume new kafka messages and insert them into the database in a background thread
    start_consumer_thread(
        db=db,
        topic=consumer_topic,
        host=kafka_host,
        port=kafka_port,
        settings=settings,
    )

    # create a message queue for the kafka producer thread to read from in a background thread
    msg_queue: SimpleQueue[BackendStatusMessage] = queue.SimpleQueue()
    start_producer_thread(
        topic=producer_topic,
        host=kafka_host,
        port=kafka_port,
        msg_queue=msg_queue,
    )

    # check for requested/created jobs that never started on cloud batch
    # (shorter timeout)
    schedule.every(1).minutes.do(
        db.timeout_jobs, timeout_seconds=settings.TIMEOUT_SECONDS, queue=msg_queue
    )

    # check for long-running deployed jobs that never finished
    # this is quite rare
    schedule.every(1).minutes.do(
        db.timeout_deployed_jobs,
        timeout_seconds=settings.DEPLOYED_TIMEOUT_SECONDS,
        queue=msg_queue,
    )

    # check if job states have changed and produce new messages
    schedule.every(settings.POLL_INTERVAL).seconds.do(
        check_job_state, db=db, settings=settings, queue=msg_queue
    )

    schedule.every(1).hours.do(
        bucket_clean_up,
        project_id=settings.GCP_PROJECT,
        bucket_prefix=f"{settings.NAMESPACE.value}-intp",
    )

    while True:
        if KAFKA_CONSUMER_NOT_OK.is_set():
            # restart the kafka consumer thread
            start_consumer_thread(
                db=db,
                topic=consumer_topic,
                host=kafka_host,
                port=kafka_port,
                settings=settings,
            )
            kafka_fail_count += 1

        if KAFKA_PRODUCER_NOT_OK.is_set():
            # restart the kafka producer thread
            start_producer_thread(
                topic=producer_topic,
                host=kafka_host,
                port=kafka_port,
                msg_queue=msg_queue,
            )
            kafka_fail_count += 1

        if kafka_fail_count > settings.MAX_KAFKA_FAILS:
            raise Exception("Kafka thread failed too many times, exploding loudly")

        # run any pending tasks
        schedule.run_pending()

        time.sleep(1)


def bucket_clean_up(project_id: str, bucket_prefix: str) -> None:
    """Deletes buckets older than two weeks with a specific prefix.

    This scheduled function is meant to clean empty results buckets,
    but it's helpful to make sure work buckets are empty and deleted, because:

    - Objects always have a lifecycle policy and delete themselves
    - When a job enters a failed state buckets should get deleted

    If anything goes wrong with these approaches this is an additional deletion step
    """
    logger.info("Checking for expired buckets")

    TWO_WEEKS_AGO = datetime.now(timezone.utc) - timedelta(days=14)
    storage_client = storage.Client(project=project_id)
    buckets = [
        x
        for x in storage_client.list_buckets()
        if x.name.startswith(bucket_prefix) and x.time_created < TWO_WEEKS_AGO
    ]

    for bucket in buckets:
        try:
            bucket.delete(force=True)
            logger.info(f"Deleted expired bucket: {bucket.name}")
        except Exception as e:
            logger.critical(f"Error deleting bucket {bucket.name}: {e}")


if __name__ == "__main__":
    main()
