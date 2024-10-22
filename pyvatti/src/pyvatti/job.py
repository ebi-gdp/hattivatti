# type: ignore
"""This module contains a state machine that represents job states and their transitions"""
import logging
import sys
from datetime import datetime
from functools import lru_cache
from typing import Optional, ClassVar

import httpx
from kafka import KafkaProducer
from transitions import Machine, EventData, MachineError

from pyvatti.config import settings
from pyvatti.jobstates import States
from pyvatti.messagemodels import JobRequest
from pyvatti.notifymodels import SeqeraLog, BackendStatusMessage, BackendEvents

from pyvatti.resources import GoogleResourceHandler, DummyResourceHandler

logger = logging.getLogger(__name__)

API_ROOT = "https://api.cloud.seqera.io"


class PolygenicScoreJob(Machine):
    """A state machine for polygenic score calculation jobs

    >>> import sys
    >>> logger.addHandler(logging.StreamHandler(sys.stdout))
    >>> job = PolygenicScoreJob("INT123456", dry_run=True)
    >>> job
    PolygenicScoreJob(id='INT123456')

    On instantiation the default job state is requested:

    >>> job.state
    <States.REQUESTED: 'requested'>

    Normally creating a resource requires some parameters from a message, but not in dry run mdoe:

    >>> job.trigger("create")  # doctest: +ELLIPSIS
    Creating resources for INT123456
    Job message: None
    ...

    A job is deployed once it's live on the cluster, doing work, and sending logs:

    >>> job.trigger("deploy")  # doctest: +ELLIPSIS
    Sending state notification: States.DEPLOYED
    ...

    Notifications are sent to the backend to update the user.

    A job may enter the succeed state if it's received a message confirming this:

    >>> job.trigger("succeed") # doctest: +ELLIPSIS
    Sending state notification: States.SUCCEEDED
    msg='{"run_name":"INT123456","utc_time":...,"event":"completed"}' prepared to send to pipeline-notify topic (PYTEST RUNNING)
    Deleting all resources: INT123456
    ...

    State machines are helpful to prevent illegal state transitions. For example, once a job has succeeded it can't error:

    >>> job.trigger("error")  # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    transitions.core.MachineError: "Can't trigger event error from state SUCCEEDED!"

    Let's look at a misbehaving job:

    >>> bad_job = PolygenicScoreJob("INT789123", dry_run=True)
    >>> bad_job.trigger("error")  # doctest: +ELLIPSIS
    Sending state notification: States.FAILED
    msg='{"run_name":"INT789123","utc_time":"...","event":"error"}' prepared to send to pipeline-notify topic (PYTEST RUNNING)
    Deleting all resources: INT789123
    ...

    It's important to clean up and delete resources in the event of a failure.
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
        States.DEPLOYED: "deployed",
    }
    # map from states to events recognised by the backend
    state_event_map: ClassVar[dict] = {
        States.FAILED: BackendEvents.ERROR,
        States.SUCCEEDED: BackendEvents.COMPLETED,
        States.DEPLOYED: BackendEvents.STARTED,
    }

    def __init__(self, intp_id, dry_run=False):
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

        if dry_run:
            self.handler = DummyResourceHandler(intp_id=intp_id)
        else:
            self.handler = GoogleResourceHandler(intp_id=intp_id)

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
        if isinstance(event.error, MachineError):
            logger.warning(f"Couldn't trigger error state for {self.intp_id}")
            raise event.error
        else:
            self.trigger("error")

    def create_resources(self, event: EventData):
        """Create resources required to start the job"""
        logger.info(f"Creating resources for {self.intp_id}")
        job_request: Optional[JobRequest] = event.kwargs.get("job_request", None)
        logger.info(f"Job message: {job_request}")
        self.handler.create_resources(job_request)

    def destroy_resources(self, event: EventData):
        """Delete all resources associated with this job"""
        logger.info(f"Deleting all resources: {self.intp_id}")
        self.handler.destroy_resources(state=event.state.value)

    def notify(self, event: Optional[EventData]):
        """Notify the backend about the job state"""
        logger.info(f"Sending state notification: {self.state}")
        event: str = self.state_event_map[self.state]
        msg: str = BackendStatusMessage(
            run_name=self.intp_id, utc_time=datetime.now(), event=event
        ).model_dump_json()
        if "pytest" in sys.modules:
            logger.info(
                f"{msg=} prepared to send to pipeline-notify topic (PYTEST RUNNING)"
            )
        else:
            producer = KafkaProducer(
                bootstrap_servers=[
                    f"{settings.KAFKA_BOOTSTRAP_SERVER.host}:{settings.KAFKA_BOOTSTRAP_SERVER.port}"
                ],
                value_serializer=lambda v: v.encode("utf-8"),
            )
            producer.send(settings.KAFKA_PRODUCER_TOPIC, msg)
            producer.flush()
            logger.info(f"{msg=} sent to pipeline-notify topic")

    def get_job_state(self) -> Optional[States]:
        """Get the state of a job by checking the Seqera Platform API

        Job state matches the state machine triggers"""
        params = {
            "workspaceId": settings.TOWER_WORKSPACE,
            "search": f"{settings.NAMESPACE}-{self.intp_id}",
            "max": 1,
        }

        with httpx.Client() as client:
            response = client.get(
                f"{API_ROOT}/workflow", headers=get_headers(), params=params
            )

        return SeqeraLog.from_response(response.json()).get_job_state()

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.intp_id!r})"


@lru_cache
def get_headers():
    return {
        "Authorization": f"Bearer {settings.TOWER_TOKEN}",
        "Accept": "application/json",
    }
