# type: ignore
"""This module contains a state machine that represents job states and their transitions"""

import enum
import logging

from transitions import EventData
from transitions.extensions.asyncio import AsyncMachine

from .resources import GoogleResourceHandler

logger = logging.getLogger(__name__)


class States(enum.Enum):
    REQUESTED = "requested"
    CREATED = "created"
    DEPLOYED = "deployed"
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class PolygenicScoreJob(AsyncMachine):
    """This is a state machine for polygenic score calculation jobs

    >>> import asyncio
    >>> job = PolygenicScoreJob("INT123456")
    >>> job
    PolygenicScoreJob(id='INT123456')
    >>> job.state
    <States.REQUESTED: 'requested'>
    >>> _ = asyncio.run(job.create())
    creating resources
    >>> _ = asyncio.run(job.deploy())
    sending state notification: States.DEPLOYED
    >>> job.state
    <States.DEPLOYED: 'deployed'>
    >>> _ = asyncio.run(job.succeed())
    sending state notification: States.SUCCEEDED
    deleting all resources: INT123456

    Once a job has succeeded it can't error:

    >>> _ = asyncio.run(job.error())
    Traceback (most recent call last):
    ...
    transitions.core.MachineError: "Can't trigger event error from state SUCCEEDED!"

    Let's look at a misbehaving job:

    >>> bad_job = PolygenicScoreJob("INT789123")

    >>> _ = asyncio.run(bad_job.error())
    sending state notification: States.FAILED
    deleting all resources: INT789123

    It's important that jobs can be pickled and loaded back OK:

    >>> import pickle
    >>> dump = pickle.dumps(job)
    >>> job2 = pickle.loads(dump)
    >>> job.states.keys() == job2.states.keys()
    True
    >>> job.state == job2.state
    True
    """

    # when callback methods are invoked _after_ a transition, state = destination
    transitions = [
        {
            "trigger": "create",
            "source": States.REQUESTED,
            "dest": States.CREATED,
            "prepare": ["create_resources", "notify"],
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

    def __init__(self, id):
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

        self.id = id
        self.handler = GoogleResourceHandler()

        # set up the state machine
        super().__init__(
            self,
            states=states,
            initial=States.REQUESTED,
            transitions=self.transitions,
            send_event=True,
        )

    async def create_resources(self, event: EventData):
        """Create resources required to start the job"""
        print("creating resources")
        await self.handler.create_resources(job_model=event.kwargs["job_model"])

    async def destroy_resources(self, event: EventData):
        """Delete all resources associated with this job"""
        print(f"deleting all resources: {self.id}")
        await self.handler.destroy_resources()

    async def notify(self, event):
        """Notify the backend about the job state"""
        print(f"sending state notification: {self.state}")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id!r})"
