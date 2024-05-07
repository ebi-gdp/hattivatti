# type: ignore
"""This module contains a state machine that represents job states and their transitions"""

import logging
import shelve
import urllib.parse
from datetime import timezone, datetime
from functools import lru_cache
from typing import Optional

from transitions import EventData
from transitions.extensions.asyncio import AsyncMachine

from . import SHELF_PATH, CLIENT, SHELF_LOCK
from .config import settings
from .monitor import BackendStatusMessage

from .resources import GoogleResourceHandler
from .jobstates import States

logger = logging.getLogger(__name__)


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

    def __init__(self, intp_id):
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
        self.handler = GoogleResourceHandler(intp_id=intp_id)

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
        try:
            await self.handler.create_resources(job_model=event.kwargs["job_model"])
        except Exception as e:
            logger.warning(f"Something went wrong, {self.intp_id} entering error state")
            await self.error()
            raise Exception from e

    async def destroy_resources(self, event: EventData):
        """Delete all resources associated with this job"""
        print(f"deleting all resources: {self.intp_id}")
        await self.handler.destroy_resources(state=event.state.value)

    async def notify(self, event: Optional[EventData]):
        """Notify the backend about the job state"""
        print(f"sending state notification: {self.state}")
        if event is not None:
            # TODO: grab event data
            utc_time = datetime.now(timezone.utc)
        else:
            utc_time = datetime.now(timezone.utc)

        msg = BackendStatusMessage(
            run_name=self.intp_id, utc_time=utc_time, event=self.state
        )

        url = f"bff/pipeline-manager/integration/pipeline/{msg.run_name}/status"
        notify_url = urllib.parse.urljoin(str(settings.NOTIFY_URL), url)
        response = await CLIENT.patch(
            url=notify_url, data=msg.dict(), headers=notify_headers()
        )

        if response.status_code == 200:
            logger.info(f"Notification success: {msg}")
        else:
            logger.warning(f"Notification failed: {msg}")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.intp_id!r})"


async def update_job_state(workflow_id: str, trigger: str):
    with shelve.open(SHELF_PATH) as db:
        job_instance: PolygenicScoreJob = db[workflow_id]

    logger.info(f"Triggering state {trigger}")
    await job_instance.trigger(trigger, client=CLIENT)

    match trigger:
        case "succeed" | "error":
            delete = True
        case _:
            delete = False

    async with SHELF_LOCK:
        with shelve.open(SHELF_PATH) as db:
            if not delete:
                db[workflow_id] = job_instance
            else:
                db.pop(workflow_id)


@lru_cache
def notify_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {settings.NOTIFY_TOKEN}",
    }
