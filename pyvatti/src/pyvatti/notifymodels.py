""" This module contains pydantic models that represent responses from the Seqera platform API

The platform API is queried to poll and monitor the state of running jobs
"""
import logging
from datetime import datetime
import enum
from functools import lru_cache
from typing import Optional

import httpx
from pydantic import BaseModel, PastDatetime

from pyvatti.config import settings
from pyvatti.jobstates import States

API_ROOT = "https://api.cloud.seqera.io"


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_headers():
    """Headers that authorise querying the Seqera platform API"""
    return {
        "Authorization": f"Bearer {settings.TOWER_TOKEN}",
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
    runName: str
    start: datetime
    dateCreated: datetime
    status: SeqeraJobStatus
    exitStatus: Optional[int] = None

    @classmethod
    def from_response(cls, response: httpx.Response):
        if len(workflow := response.json()["workflows"]) == 1:
            return cls(**workflow[0]["workflow"])
        else:
            return None

    def get_job_state(self) -> Optional[States]:
        """Get valid job states"""
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
    >>> d = {"run_name": "INTP123456", "utc_time": datetime(1999, 12, 31), "event": States.SUCCEEDED}
    >>> BackendStatusMessage(**d).model_dump_json()
    '{"run_name":"INTP123456","utc_time":"1999-12-31T00:00:00","event":"succeeded"}'
    """

    run_name: str
    utc_time: PastDatetime
    event: States
