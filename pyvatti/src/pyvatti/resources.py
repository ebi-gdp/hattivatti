"""This module contains classes to handle the resources needed to run a job"""

import abc


class ResourceProvider(abc.ABC):
    @abc.abstractmethod
    def create_resources(self):
        """Create the compute resources needed to run a job

        For example:
        - Create storage buckets
        - Render a helm chart or a SLURM template
        """
        ...

    @abc.abstractmethod
    def destroy_resources(self):
        """Destroy the created resources

        Cleaning up properly is very important to keep sensitive data safe
        """
        ...


class GoogleResourceProvider(ResourceProvider):
    def __init__(self):
        pass

    def create_resources(self):
        raise NotImplementedError

    def destroy_resources(self):
        raise NotImplementedError
