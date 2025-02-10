"""This module contains pydantic models that represent responses from the Seqera platform API

The platform API is queried to poll and monitor the state of running jobs
"""

import logging
from datetime import datetime
import enum
from functools import lru_cache
from typing import Optional, Type, Self

from pydantic import BaseModel, Field, model_serializer, field_validator

from pyvatti.jobstates import States

API_ROOT = "https://api.cloud.seqera.io"


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_headers(tower_token: str) -> dict[str, str]:
    """Headers that authorise querying the Seqera platform API"""
    return {
        "Authorization": f"Bearer {tower_token}",
        "Accept": "application/json",
    }


class SeqeraJobStatus(str, enum.Enum):
    """Job states on the Seqera platform"""

    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class SeqeraLog(BaseModel):
    """

    When jobs start they send logs back via the Seqera API. Let's try to parse a fake response from the Seqera API:

    >>> import json, pathlib
    >>> testmsg = pathlib.Path(__file__).parent.parent.parent / "tests" / "data" / "seqera-response.json"
    >>> with open(testmsg) as f:
    ...     d = json.load(f)
    >>> log = SeqeraLog.from_response(d)
    >>> log # doctest: +ELLIPSIS
    SeqeraLog(runName='intervene-dev-intp00000000044', ...

    Parse the seqera status to a job machine state:

    >>> log.get_job_state()
    <States.SUCCEEDED: 'Succeeded'>

    A job can take time to start. During this time you'll get empty responses from the Seqera API:

    >>> missing_job = {"workflows":[],"totalSize":0}
    >>> SeqeraLog.from_response(missing_job) is None
    True

    Extract extra information for failing workflows:

    >>> testmsg = pathlib.Path(__file__).parent.parent.parent / "tests" / "data" / "seqera-error.json"
    >>> with open(testmsg) as f:
    ...     d = json.load(f)
    >>> log = SeqeraLog.from_response(d)
    >>> log.exitStatus  # exit codes are used by pygscatalog to communicate specific errors
    12
    >>> log.errorReport
    "Error executing process > 'PGSCATALOG_PGSCCALC:PGSCCALC:INPUT_CHECK:COMBINE_SCOREFILES (1)'"
    """

    runName: str
    start: datetime
    dateCreated: datetime
    status: SeqeraJobStatus
    exitStatus: Optional[int] = Field(default=None)
    errorReport: Optional[str] = Field(default=None)

    @classmethod
    def from_response(cls: Type[Self], json: dict) -> Optional[Self]:
        log: Optional[SeqeraLog]
        size: int = json["totalSize"]
        if size == 0:
            logger.info("No workflow found in Seqera API")
            log = None
        elif size == 1:
            logger.info("Valid response received from Seqera API")
            log = cls(**json["workflows"][0]["workflow"])
        else:
            logger.warning(
                "More than one workflow in response. This should never happen, so setting response to None"
            )
            log = None

        return log

    @field_validator("errorReport", mode="after")
    @classmethod
    def trim_error_message(cls, message: Optional[str]) -> Optional[str]:
        if message is not None:
            message = message.strip().split("\n")[0]
        return message

    def get_job_state(self) -> Optional[States]:
        """Get valid job states"""
        state: Optional[States]
        match self.status:
            case SeqeraJobStatus.SUCCEEDED:
                state = States.SUCCEEDED
            case SeqeraJobStatus.FAILED | SeqeraJobStatus.UNKNOWN:
                state = States.FAILED
            case SeqeraJobStatus.RUNNING:
                state = States.DEPLOYED
            case _:
                logger.warning(f"Unknown state: {self.status}")
                state = None
        return state


class BackendStatusMessage(BaseModel):
    """A message updating the backend about job state

    >>> from datetime import datetime
    >>> d = {"run_name": "INTP123456", "utc_time": datetime(1999, 12, 31), "event": States.DEPLOYED }
    >>> BackendStatusMessage(**d).model_dump_json()
    '{"run_name":"INTP123456","utc_time":"1999-12-31T00:00:00","event":"Deployed"}'

    >>> d = {"run_name": "INTP123456", "utc_time": datetime(1999, 12, 31), "event": States.FAILED, "trace_name": "failed_process", "trace_exit": 1 }
    >>> BackendStatusMessage(**d).model_dump_json()
    '{"run_name":"INTP123456","utc_time":"1999-12-31T00:00:00","event":"Failed","trace_name":"failed_process","trace_exit":1}'
    """

    run_name: str
    utc_time: datetime
    event: States
    trace_name: Optional[str] = Field(default=None)
    trace_exit: Optional[int] = Field(default=None)

    @model_serializer()
    def serialize_model(self) -> dict:
        """Only serialize trace information when there's a failure"""
        if self.event == States.FAILED:
            return {
                "run_name": self.run_name,
                "utc_time": self.utc_time,
                "event": self.event,
                "trace_name": self.trace_name,
                "trace_exit": self.trace_exit,
            }
        return {
            "run_name": self.run_name,
            "utc_time": self.utc_time,
            "event": self.event,
        }
