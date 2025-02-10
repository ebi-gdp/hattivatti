"""This module contains classes needed to load jobs into a database"""

import logging
import pathlib
import pickle
import sqlite3
import abc
from multiprocessing.queues import SimpleQueue
from typing import Optional

from pyvatti.pgsjob import PolygenicScoreJob  # type: ignore[attr-defined]


logger = logging.getLogger(__name__)


class JobDatabase(abc.ABC):
    @abc.abstractmethod
    def __init__(self, path: pathlib.Path | str) -> None:
        self.path = path

    @abc.abstractmethod
    def create(self) -> None:
        """Execute a SQL statement that creates the database table"""
        ...

    @abc.abstractmethod
    def insert_job(self, job: PolygenicScoreJob) -> None:
        """Insert a job in the database

        Each row must contain:

        - A job ID
        - A pickled state machine object
        - A state

        Insertions are triggered by kafka messages
        """
        ...

    @abc.abstractmethod
    def update_job(self, job: PolygenicScoreJob) -> None:
        """Update (update/insert) a job in the database

        Each row must contain:

        - A job ID
        - A pickled state machine object
        - A state

        Updates are triggered by Seqera platform updates
        """
        ...

    @abc.abstractmethod
    def timeout_jobs(self, timeout_seconds: int, queue: SimpleQueue) -> None:
        """Check if any unfinished jobs exceed the timeout.

        If they do, job objects should be loaded and the error state triggered
        """
        ...

    @abc.abstractmethod
    def load_job(self, job_id: str) -> PolygenicScoreJob:
        """Unpickle a state machine object from the database"""
        ...


class SqliteJobDatabase(JobDatabase):
    """A job database backed by a local sqlite database

    Create a new job database on application startup:

    >>> import queue
    >>> from tempfile import NamedTemporaryFile
    >>> from pyvatti.pgsjob import PolygenicScoreJob
    >>> db_path = NamedTemporaryFile(delete=False)
    >>> db = SqliteJobDatabase(path=db_path.name)
    >>> db.create()

    Prepare a message queue:

    >>> q = queue.SimpleQueue()

    Create a new job:

    >>> job = PolygenicScoreJob("test", dry_run=True)
    >>> _ = job.trigger("create")
    >>> job.state
    <States.CREATED: 'Created'>

    Insert the job to the empty database:

    >>> db.insert_job(job)

    Read a job back from the database:

    >>> job = db.load_job(job.intp_id)
    >>> job
    PolygenicScoreJob(id='test')
    >>> job.state
    <States.CREATED: 'Created'>

    Update the job state:

    >>> _ = job.trigger("deploy", queue=q)
    >>> job.state
    <States.DEPLOYED: 'Deployed'>

    Now update the existing job:

    >>> db.update_job(job)

    And make sure when loading the job back into an object the state is consistent:

    >>> updated_job = db.load_job(job.intp_id)
    >>> updated_job.state
    <States.DEPLOYED: 'Deployed'>

    Active jobs are jobs that haven't failed or succeeded:

    >>> db.get_active_jobs()
    [PolygenicScoreJob(id='test')]

    Let's update the job to make it exceed the timeout:

    >>> import datetime
    >>> yesterday = datetime.datetime.today() - datetime.timedelta(days=1)

    >>> with sqlite3.connect(db.path) as conn:
    ...     cursor = conn.cursor()
    ...     sql = "UPDATE jobs SET state = ?, created_at = ? WHERE id = ?"
    ...     _ = cursor.execute(sql, ('Created', str(yesterday), updated_job.intp_id))

    Deployed jobs time out by a separate Nextflow mechanism.

    Created jobs can time out because that means they've never started sending logs back.

    Trigger the error state for any timed out jobs:

    >>> updated_job = db.load_job(job.intp_id)
    >>> updated_job.state
    <States.DEPLOYED: 'Deployed'>
    >>> db.get_active_jobs()
    [PolygenicScoreJob(id='test')]

    >>> db.timeout_jobs(timeout_seconds=60, queue=q)

    Check for active jobs:

    >>> db.get_active_jobs()
    []

    (there are none!)

    Check the state of the timed out job:

    >>> db.load_job("test").state
    <States.FAILED: 'Failed'>

    Perfect :) Now clean up the db

    >>> import os
    >>> os.unlink(db_path.name)
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def create(self) -> None:
        """Make the database table and set up the date trigger"""
        logger.info(f"Creating database table: {self.path}")
        schema = """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            job BLOB NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            state TEXT CHECK(state IN ('Requested', 'Created', 'Deployed', 'Failed', 
            'Succeeded')) NOT NULL
        );

        CREATE TRIGGER IF NOT EXISTS update_timestamp
        AFTER UPDATE ON jobs
        FOR EACH ROW
        BEGIN
            UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;
        """
        with sqlite3.connect(self.path) as conn:
            conn.executescript(schema)

    def timeout_jobs(self, timeout_seconds: int, queue: SimpleQueue) -> None:
        """Trigger the error state in any jobs that exceed a timeout limit

        If a job has deployed successfully, it will timeout by itself because of --max_time capping processes
        """
        sql = """
        SELECT id FROM jobs
        WHERE state NOT IN ('Failed', 'Deployed', 'Succeeded')
            AND created_at <= datetime('now', ? || ' seconds');
        """
        logger.info("Checking for timed out jobs")
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            # - is important to select a time in the past
            cursor.execute(sql, (f"-{timeout_seconds}",))
            result: list[tuple] = cursor.fetchall()

            if result:
                logger.info("Jobs exceeding timeout detected")
                ids: list[str] = [x[0] for x in result]
                jobs: list[PolygenicScoreJob] = [self.load_job(x) for x in ids]
                for job in jobs:
                    logger.warning(f"Killing {job=}")
                    job.trigger("error", queue=queue)
                    self.update_job(job)  # don't forget to update the db

    def timeout_deployed_jobs(self, timeout_seconds: int, queue: SimpleQueue) -> None:
        """Trigger the error state in any jobs that exceed a timeout limit

        This should rarely trigger (Nextflow processes have time limits).
        """
        sql = """
        SELECT id FROM jobs
        WHERE state IN ('Deployed')
            AND created_at <= datetime('now', ? || ' seconds');
        """
        logger.info("Checking for deployed jobs for timeout")
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            # - is important to select a time in the past
            cursor.execute(sql, (f"-{timeout_seconds}",))
            result: list[tuple] = cursor.fetchall()

            if result:
                logger.info("Jobs exceeding timeout detected")
                ids: list[str] = [x[0] for x in result]
                jobs: list[PolygenicScoreJob] = [self.load_job(x) for x in ids]
                for job in jobs:
                    logger.warning(f"Killing {job=}")
                    job.trigger("error", queue=queue)
                    self.update_job(job)  # don't forget to update the db

    def insert_job(self, job: PolygenicScoreJob) -> None:
        pickled_job = pickle.dumps(job)
        sql = """
        INSERT INTO jobs(id, job, state) VALUES (:id, :job, :state)
        """
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            job_data = {"id": job.intp_id, "job": pickled_job, "state": job.state}
            cursor.execute(sql, job_data)

    def update_job(self, job: PolygenicScoreJob) -> None:
        pickled_job = pickle.dumps(job)
        sql = """
        UPDATE jobs
        SET job = :job, state = :state
        WHERE id == :id 
        """
        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            job_data = {"id": job.intp_id, "job": pickled_job, "state": job.state}
            cursor.execute(sql, job_data)

    def load_job(self, job_id: str) -> PolygenicScoreJob:
        sql = "SELECT job FROM jobs WHERE id = ?"

        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (job_id,))
            result: Optional[tuple] = cursor.fetchone()

        if result is not None:
            pickled_job = result[0]
            return pickle.loads(pickled_job)

    def get_active_jobs(self) -> list[PolygenicScoreJob]:
        sql = """
        SELECT id FROM jobs WHERE state NOT IN ('Failed', 'Succeeded')
        """

        with sqlite3.connect(self.path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            result = cursor.fetchall()

        if result:
            ids: list[str] = [x[0] for x in result]
            jobs: list[PolygenicScoreJob] = [self.load_job(x) for x in ids]
        else:
            jobs = []

        return jobs
