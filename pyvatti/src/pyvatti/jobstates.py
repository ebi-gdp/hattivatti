import enum


class States(str, enum.Enum):
    REQUESTED = "requested"
    CREATED = "created"
    DEPLOYED = "deployed"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
