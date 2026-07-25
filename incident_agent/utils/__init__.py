"""Utility layer.

Small, stateless, dependency-free helpers: structured logging setup, ID
generation, retry/backoff decorators, and malformed-JSON recovery. Utils
must never import from agents/, graphs/, or services/ to avoid circular
dependencies.
"""
