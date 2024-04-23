import enum


class States(enum.Enum):
    REQUESTED = "requested"
    CREATED = "created"
    DEPLOYED = "deployed"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
