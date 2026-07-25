"""REST API tool -- generic outbound HTTP calls (e.g. a vendor status page,
an internal health-check endpoint).

Security note: this tool's URL argument is ultimately LLM-controlled, so it
is a textbook SSRF vector -- a compromised or confused agent could be
steered into requesting `http://169.254.169.254/...` (cloud instance
metadata) or an internal-only service. We block that at the network layer:
resolve the hostname first and refuse to connect if it resolves to a
loopback, private, or link-local address, in addition to restricting the
scheme to http/https and enforcing a response-size cap and timeout.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from langchain_core.tools import tool

from incident_agent.tools.base import run_structured

_ALLOWED_SCHEMES = {"http", "https"}
_TIMEOUT_SECONDS = 10.0
_MAX_RESPONSE_BYTES = 200_000


class UnsafeURLError(ValueError):
    """Raised when a requested URL resolves to a disallowed network target."""


def _assert_url_is_safe(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"Scheme '{parsed.scheme}' is not permitted; use http or https.")
    if not parsed.hostname:
        raise UnsafeURLError("URL must include a hostname.")
    try:
        resolved_addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve hostname '{parsed.hostname}': {exc}") from exc
    for address in resolved_addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeURLError(
                f"URL resolves to a disallowed network target ({address}); "
                "internal/loopback/link-local addresses are blocked."
            )


def _fetch(url: str, method: str) -> dict:
    _assert_url_is_safe(url)
    with httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=False) as client:
        response = client.request(method.upper(), url)
        body = response.text[:_MAX_RESPONSE_BYTES]
        return {
            "url": url,
            "method": method.upper(),
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
            "truncated": len(response.text) > _MAX_RESPONSE_BYTES,
        }


@tool
def rest_api_call(url: str, method: str = "GET") -> str:
    """Make an outbound HTTP request (GET or POST, no body support) to check a
    vendor status page or an accessible internal health-check endpoint.

    Only http/https URLs that resolve to a public, non-internal address are
    permitted -- requests to loopback, private, or link-local addresses
    (including cloud metadata endpoints) are refused for safety.
    """
    return run_structured("rest_api_call", lambda: _fetch(url, method))
