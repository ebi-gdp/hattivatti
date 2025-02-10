# type: ignore
"""This module contains a state machine that represents job states and their transitions"""

import logging
import sys
from datetime import datetime
from functools import lru_cache
from queue import SimpleQueue
from typing import Optional, ClassVar

import httpx
from transitions import Machine, EventData, MachineError

from pyvatti.config import Settings, K8SNamespace
from pyvatti.jobstates import States
from pyvatti.messagemodels import JobRequest
from pyvatti.notifymodels import SeqeraLog, BackendStatusMessage

from pyvatti.resources import GoogleResourceHandler, DummyResourceHandler

logger = logging.getLogger(__name__)

API_ROOT = "https://api.cloud.seqera.io"


class PolygenicScoreJob(Machine):
    """A state machine for polygenic score calculation jobs

    >>> import sys
    >>> logger.addHandler(logging.StreamHandler(sys.stdout))

    It's important to use a queue to put state messages in:
    >>> q = SimpleQueue()

    >>> job = PolygenicScoreJob("INT123456", dry_run=True)
    >>> job
    PolygenicScoreJob(id='INT123456')

    On instantiation the default job state is requested:

    >>> job.state
    <States.REQUESTED: 'Requested'>

    Normally creating a resource requires some parameters from a message, but not in dry run mdoe:

    >>> job.trigger("create")  # doctest: +ELLIPSIS
    Creating resources for INT123456
    Job message: None
    ...

    A job is deployed once it's live on the cluster, doing work, and sending logs:

    >>> job.trigger("deploy", queue=q)  # doctest: +ELLIPSIS
    Sending state notification: States.DEPLOYED
    ...

    Notifications are sent to the backend to update the user.

    A job may enter the succeed state if it's received a message confirming this:

    >>> job.trigger("succeed", queue=q) # doctest: +ELLIPSIS
    Sending state notification: States.SUCCEEDED
    msg='{"run_name":"INT123456","utc_time":...,"event":"Succeeded"}' prepared to send to pipeline-notify topic (PYTEST RUNNING)
    Deleting all resources: INT123456
    ...

    State machines are helpful to prevent illegal state transitions. For example, once a job has succeeded it can't error:

    >>> job.trigger("error", queue=q)  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    transitions.core.MachineError: "Can't trigger event error from state SUCCEEDED!"

    Let's look at a misbehaving job:

    >>> bad_job = PolygenicScoreJob("INT789123", dry_run=True)
    >>> bad_job.trigger("error", queue=q)  # doctest: +ELLIPSIS
    Sending state notification: States.FAILED
    msg='{"run_name":"INT789123","utc_time":"...","event":"Failed","trace_name":null,"trace_exit":null}' prepared to send to pipeline-notify topic (PYTEST RUNNING)
    Deleting all resources: INT789123
    ...

    It's important to clean up and delete resources in the event of a failure.

    trace_name and trace_exit are null because this information is set by a scheduled function that triggers the error state (check_job_state)
    """

    # when callback methods are invoked _after_ a transition, state = destination
    transitions = [
        {
            "trigger": "create",
            "source": States.REQUESTED,
            "dest": States.CREATED,
            "prepare": ["create_resources"],
        },
        {
            "trigger": "deploy",
            "source": States.CREATED,
            "dest": States.DEPLOYED,
            "after": ["notify"],
        },
        {
            "trigger": "succeed",
            "source": States.DEPLOYED,
            "dest": States.SUCCEEDED,
            "after": ["notify", "destroy_resources"],
        },
        {
            "trigger": "error",
            "source": States.REQUESTED,
            "dest": States.FAILED,
            "after": ["notify", "destroy_resources"],
        },
        {
            "trigger": "error",
            "source": States.CREATED,
            "dest": States.FAILED,
            "after": ["notify", "destroy_resources"],
        },
        {
            "trigger": "error",
            "source": States.DEPLOYED,
            "dest": States.FAILED,
            "after": ["notify", "destroy_resources"],
        },
    ]

    # map from destination states to triggers
    state_trigger_map: ClassVar[dict] = {
        States.FAILED: "error",
        States.SUCCEEDED: "succeed",
        States.DEPLOYED: "deploy",
    }

    def __init__(
        self,
        intp_id: str,
        settings: Optional[Settings] = None,
        dry_run: bool = False,
        trace_name: Optional[str] = None,
        trace_exit: Optional[int] = None,
    ):
        states = [
            # a dummy initial state: /launch got POSTed
            {"name": States.REQUESTED},
            # helm install worked (creating the workflow pod)
            {"name": States.CREATED},
            # the workflow POSTed the started event to the monitor API
            {"name": States.DEPLOYED},
            # the workflow POSTed the completed event to the monitor API
            {"name": States.SUCCEEDED},
            # the workflow POSTed the error event to the monitor API, timed out, or
            # an exception was raised in any of the previous states
            {"name": States.FAILED},
        ]

        self.intp_id = intp_id

        if not dry_run and settings is None:
            raise TypeError("Settings cannot be none when not a dry run")

        if dry_run:
            self.handler = DummyResourceHandler(intp_id=intp_id)
        else:
            self.handler = GoogleResourceHandler(intp_id=intp_id, settings=settings)

        # read from seqera API when the failed state happens
        self.trace_name = trace_name  # the name of the failing process
        self.trace_exit = trace_exit  # exit code of failing process

        # set up the state machine
        super().__init__(
            self,
            states=states,
            initial=States.REQUESTED,
            transitions=self.transitions,
            on_exception=self.handle_error,
            send_event=True,
        )

    def handle_error(self, event):
        logger.warning(f"Exception raised for {self.intp_id}")
        logger.warning(event.error)
        if isinstance(event.error, MachineError):
            logger.warning(f"Couldn't trigger error state for {self.intp_id}")
            raise event.error
        else:
            self.trigger("error")

    def create_resources(self, event: EventData):
        """Create resources required to start the job"""
        logger.info(f"Creating resources for {self.intp_id}")
        job_request: Optional[JobRequest] = event.kwargs.get("job_model", None)

        if job_request is None and isinstance(self.handler, GoogleResourceHandler):
            raise ValueError("Can't create google resources without a job request")

        logger.info(f"Job message: {job_request}")
        self.handler.create_resources(job_request)

    def destroy_resources(self, event: EventData):
        """Delete all resources associated with this job"""
        logger.info(f"Deleting all resources: {self.intp_id}")
        self.handler.destroy_resources(state=event.state.value)

    def notify(self, event: EventData):
        """Notify the backend about the job state"""
        # bootstrap_server_host: str, bootstrap_server_port: int
        queue: Optional[SimpleQueue] = event.kwargs.get("queue", None)
        if queue is None:
            raise TypeError("Can't notify without a queue kwarg to the notify method")

        logger.info(f"Sending state notification: {self.state}")
        msg: BackendStatusMessage = BackendStatusMessage(
            run_name=self.intp_id,
            utc_time=datetime.now(),
            event=self.state,
            trace_name=self.trace_name,
            trace_exit=self.trace_exit,
        )
        if "pytest" in sys.modules:
            queue.put(msg)
            logger.info(
                f"{msg=} prepared to send to pipeline-notify topic (PYTEST RUNNING)"
            )
        else:
            queue.put(msg)
            logger.info(f"{msg=} sent to pipeline-notify topic")

    def get_seqera_log(
        self, tower_workspace: int, tower_token: str, namespace: K8SNamespace
    ) -> Optional[SeqeraLog]:
        """Get a job log from the Seqera Platform API"""
        params = {
            "workspaceId": tower_workspace,
            "search": f"{namespace.value}-{self.intp_id}",
            "max": 1,
        }

        with httpx.Client() as client:
            response = client.get(
                f"{API_ROOT}/workflow", headers=get_headers(tower_token), params=params
            )

        return SeqeraLog.from_response(response.json())

    def get_job_state(
        self, tower_workspace: int, tower_token: str, namespace: K8SNamespace
    ) -> Optional[States]:
        """Get the state of a job by checking the Seqera Platform API

        Job state matches the state machine triggers"""
        params = {
            "workspaceId": tower_workspace,
            "search": f"{namespace.value}-{self.intp_id}",
            "max": 1,
        }

        with httpx.Client() as client:
            response = client.get(
                f"{API_ROOT}/workflow", headers=get_headers(tower_token), params=params
            )

        log: Optional[SeqeraLog] = SeqeraLog.from_response(response.json())

        if log is not None:
            state: Optional[States] = log.get_job_state()
        else:
            state = None

        return state

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.intp_id!r})"


@lru_cache(maxsize=1)
def get_headers(tower_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tower_token}",
        "Accept": "application/json",
    }
