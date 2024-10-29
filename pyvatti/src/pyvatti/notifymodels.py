"""This module contains pydantic models that represent responses from the Seqera platform API

The platform API is queried to poll and monitor the state of running jobs
"""

import logging
from datetime import datetime
import enum
from functools import lru_cache
from typing import Optional, Type, Self

from pydantic import BaseModel, PastDatetime

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
    <States.SUCCEEDED: 'succeeded'>

    A job can take time to start. During this time you'll get empty responses from the Seqera API:

    >>> missing_job = {"workflows":[],"totalSize":0}
    >>> SeqeraLog.from_response(missing_job) is None
    True
    """

    runName: str
    start: datetime
    dateCreated: datetime
    status: SeqeraJobStatus
    exitStatus: Optional[int] = None

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


class BackendEvents(str, enum.Enum):
    """Events recognised by the backend"""

    STARTED = "started"
    ERROR = "error"
    COMPLETED = "completed"


class BackendStatusMessage(BaseModel):
    """A message updating the backend about job state

    >>> from datetime import datetime
    >>> d = {"run_name": "INTP123456", "utc_time": datetime(1999, 12, 31), "event": BackendEvents.COMPLETED}
    >>> BackendStatusMessage(**d).model_dump_json()
    '{"run_name":"INTP123456","utc_time":"1999-12-31T00:00:00","event":"completed"}'
    """

    run_name: str
    utc_time: PastDatetime
    event: BackendEvents
