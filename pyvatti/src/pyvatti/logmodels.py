"""This module contains pydantic models for nextflow web log messages"""

import enum

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, UUID4, Extra


class LogEvent(enum.Enum):
    STARTED = "started"
    PROCESS_SUBMITTED = "process_submitted"
    PROCESS_STARTED = "process_started"
    PROCESS_COMPLETED = "process_completed"
    ERROR = "error"
    COMPLETED = "completed"


class LogMessage(BaseModel, extra=Extra.allow):
    runName: str
    runId: UUID4
    event: LogEvent
    utcTime: datetime
    trace: Optional[dict] = None
    # metadata is intentionally not modelled because we don't use it
    metadata: Optional[dict] = None


class SummaryTrace(BaseModel):
    # the exit status of the process
    trace_exit: int
    # the name of the process
    trace_name: str


class MonitorMessage(BaseModel):
    run_name: str
    utc_time: datetime
    event: LogEvent
    trace: Optional[SummaryTrace] = None
