"""Explicit domain errors instead of leaking provider exceptions to clients."""

class PlanningError(Exception):
    """An agent could not produce a safe, valid plan."""


class QueryError(Exception):
    """The requested analysis cannot be performed with these inputs."""


class UpstreamError(Exception):
    """A provider was unreachable or returned an invalid response."""


class IntegrityError(Exception):
    """A generated visualization contradicted its normalized source evidence."""
