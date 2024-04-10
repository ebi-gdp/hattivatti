# type: ignore
"""This module contains a state machine that represents job states and their transitions"""

import enum

from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout


class States(enum.Enum):
    CREATED = "created"  # a good request was received
    DEPLOYED = "deployed"  # job resources have been requested
    FAILED = "failed"  # something went wrong during job execution
    SUCCEEDED = "succeeded"  # everything was OK :)


@add_state_features(Timeout)
class TimeoutMachine(Machine):
    pass


class PolygenicScoreJob(TimeoutMachine):
    """This is a state machine for polygenic score calculation jobs

    >>> job = PolygenicScoreJob("INT123456")
    >>> job
    PolygenicScoreJob(id='INT123456')
    >>> job.state
    <States.CREATED: 'created'>
    >>> _ = job.deploy()
    creating resources
    sending state notification: States.DEPLOYED
    >>> job.state
    <States.DEPLOYED: 'deployed'>
    >>> _ = job.succeed()
    sending state notification: States.SUCCEEDED
    deleting all resources: INT123456

    Once a job has succeeded it can't error:

    >>> _ = job.error()
    Traceback (most recent call last):
    ...
    transitions.core.MachineError: "Can't trigger event error from state SUCCEEDED!"

    Let's look at a misbehaving job:

    >>> bad_job = PolygenicScoreJob("INT789123")
    >>> _ = bad_job.error()
    sending state notification: States.FAILED
    deleting all resources: INT789123

    When a deployed job times out the error transition is triggered:

    >>> job = PolygenicScoreJob("INT123456", timeout_seconds=1)
    >>> _ = job.deploy()
    creating resources
    sending state notification: States.DEPLOYED
    >>> import time
    >>> time.sleep(2)
    sending state notification: States.FAILED
    deleting all resources: INT123456

    It's really important that any jobs in the FAILED and SUCCEEDED states clean themselves up.
    """

    # when callback methods are invoked _after_ a transition, state = destination
    transitions = [
        {
            "trigger": "deploy",
            "source": States.CREATED,
            "dest": States.DEPLOYED,
            "prepare": ["create_resources"],
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

    def __init__(self, id, timeout_seconds=86400):
        states = [
            {"name": States.CREATED},
            {
                "name": States.DEPLOYED,
                "timeout": timeout_seconds,
                "on_timeout": "error",
            },
            {"name": States.SUCCEEDED},
            {"name": States.FAILED},
        ]

        self.id = id
        super().__init__(
            self,
            states=states,
            initial=States.CREATED,
            transitions=self.transitions,
        )

    def create_resources(self):
        """Create resources required to start the job"""
        print("creating resources")

    def destroy_resources(self):
        """Delete all resources associated with this job"""
        print(f"deleting all resources: {self.id}")

    def notify(self):
        """Notify the backend about the job state"""
        print(f"sending state notification: {self.state}")

    def __repr__(self):
        return f"{self.__class__.__name__}(id={self.id!r})"
