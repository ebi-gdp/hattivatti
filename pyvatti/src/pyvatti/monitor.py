import logging
from datetime import datetime
import enum
from functools import lru_cache
from typing import Optional

import httpx
from pydantic import BaseModel, Extra, field_serializer

from .config import settings
from .jobstates import States

API_ROOT = "https://api.cloud.seqera.io"


logger = logging.getLogger(__name__)


@lru_cache
def get_headers():
    return {
        "Authorization": f"Bearer {settings.TOWER_TOKEN}",
        "Accept": "application/json",
    }


class SeqeraJobStatus(enum.Enum):
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

    def __str__(self):
        return str(self.value)


class SeqeraLog(BaseModel, extra=Extra.ignore):
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

    def get_job_state(self):
        """Get valid state machine trigger strings from states"""
        match self.status:
            case SeqeraJobStatus.SUCCEEDED:
                state = "succeed"
            case SeqeraJobStatus.FAILED | SeqeraJobStatus.UNKNOWN:
                state = "error"
            case SeqeraJobStatus.RUNNING:
                state = "deploy"
            case _:
                logger.warning(f"Unknown state: {self.status}")
                raise Exception
        return state


class BackendStatusMessage(BaseModel):
    """A message updating the backend about job state"""

    run_name: str
    utc_time: datetime
    event: States

    @field_serializer("event")
    def event_field(self, event):
        return str(event)
