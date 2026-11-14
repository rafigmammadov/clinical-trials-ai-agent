# Changelog

## Unreleased — reliability and contract improvements

- Reuse the OpenAI planner's HTTP connection pool across application requests; close it on shutdown.
- Add generated request IDs, elapsed-time response headers and privacy-aware request telemetry.
- Validate chart encoding fields, graph node references and response-record accounting.
- Change enrollment-scatter citations to carry both required source fields in a single study citation.
- Honor HTTP-date `Retry-After` headers and retry HTTP 408 responses with bounded delays.
- Reject invalid registry timeouts and misconfigured non-HTTPS external endpoints at startup.
- Extend live planner evaluation reports with category-level intent and filter metrics.
- Add regression tests for those behaviors and expand the API, architecture and security documentation.

This section describes changes prepared in the current working tree. It is not a claim that a GitHub release or PyPI package has been published.
