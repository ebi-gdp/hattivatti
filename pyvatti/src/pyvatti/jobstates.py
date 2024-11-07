import enum


class States(str, enum.Enum):
    REQUESTED = "Requested"
    CREATED = "Created"
    DEPLOYED = "Deployed"
    FAILED = "Failed"
    SUCCEEDED = "Succeeded"
