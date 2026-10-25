import ipaddress
import logging
import socket
import urllib.parse
from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.db.base import utc_now

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}

DISALLOWED_METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
    "metadata.azure.com",
}

# Special cloud metadata IPs
CLOUD_METADATA_IPS = {
    "169.254.169.254",  # AWS / Azure / GCP
    "100.100.100.200",  # Alibaba Cloud
    "fd00:ec2::254",  # AWS IPv6
}

DEFAULT_MAX_SIZE_BYTES = 1_000_000  # 1 MB
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_REDIRECTS = 5


class URLGuardError(Exception):
    """Base error for URL guard validation failures."""


class InvalidSchemeError(URLGuardError):
    """Raised when URL scheme is not http or https."""


class DisallowedDestinationError(URLGuardError):
    """Raised when destination is loopback, private, link-local, multicast, or metadata."""


class ResponseSizeLimitError(URLGuardError):
    """Raised when response body exceeds maximum allowed size."""


class SafeFetchResult(BaseModel):
    url: str
    status_code: int
    content: str
    content_type: str
    size_bytes: int
    redirect_history: list[str] = Field(default_factory=list)
    source: str = "web_fetch"
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())
    verified: bool = True


def is_ip_allowed(ip_str: str) -> tuple[bool, str]:
    """Validates an IP address against loopback, private, link-local, multicast, and metadata ranges.

    Returns (True, "") if allowed, or (False, reason) if disallowed (UT-28, RULES.md).
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address format: {ip_str}"

    if ip_str in CLOUD_METADATA_IPS:
        return False, f"Cloud metadata IP address is forbidden: {ip_str}"

    if ip.is_loopback:
        return False, f"Loopback address is forbidden: {ip_str}"

    if ip.is_link_local:
        return False, f"Link-local address is forbidden: {ip_str}"

    if ip.is_private:
        return False, f"Private network address is forbidden: {ip_str}"

    if ip.is_multicast:
        return False, f"Multicast address is forbidden: {ip_str}"

    if ip.is_reserved:
        return False, f"Reserved address is forbidden: {ip_str}"

    if ip.is_unspecified:
        return False, f"Unspecified address (0.0.0.0/::) is forbidden: {ip_str}"

    return True, ""


def validate_hostname_and_ips(hostname: str) -> list[str]:
    """Resolves a hostname and verifies that all resolved IP addresses are safe public IPs."""
    clean_host = hostname.strip().lower()

    if clean_host in DISALLOWED_METADATA_HOSTS or clean_host.endswith(".internal"):
        raise DisallowedDestinationError(f"Cloud metadata hostname is forbidden: '{hostname}'")

    if clean_host in ("localhost", "localhost.localdomain", "broadcasthost"):
        raise DisallowedDestinationError(f"Loopback hostname is forbidden: '{hostname}'")

    # If hostname is already an IP address
    try:
        ip = ipaddress.ip_address(clean_host)
        allowed, reason = is_ip_allowed(str(ip))
        if not allowed:
            raise DisallowedDestinationError(reason)
        return [str(ip)]
    except ValueError:
        pass  # It's a domain name to resolve

    # Resolve hostname to IPv4 and IPv6 addresses
    try:
        addr_info = socket.getaddrinfo(clean_host, None)
    except socket.gaierror as e:
        raise DisallowedDestinationError(f"Could not resolve hostname '{hostname}': {e}") from e

    resolved_ips: list[str] = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = str(sockaddr[0])
        if ip_str not in resolved_ips:
            resolved_ips.append(ip_str)

    if not resolved_ips:
        raise DisallowedDestinationError(f"No IP addresses found for hostname '{hostname}'.")

    for ip_str in resolved_ips:
        allowed, reason = is_ip_allowed(ip_str)
        if not allowed:
            logger.warning(
                "Hostname '%s' resolved to disallowed IP '%s': %s", hostname, ip_str, reason
            )
            raise DisallowedDestinationError(
                f"Host '{hostname}' resolved to disallowed destination: {reason}"
            )

    return resolved_ips


def validate_url(url: str) -> urllib.parse.ParseResult:
    """Validates URL scheme and destination host before network access."""
    if not url or not isinstance(url, str):
        raise InvalidSchemeError("URL must be a non-empty string.")

    parsed = urllib.parse.urlparse(url.strip())
    scheme = parsed.scheme.lower()

    if scheme not in ALLOWED_SCHEMES:
        raise InvalidSchemeError(
            f"Scheme '{scheme}' is forbidden. Only {sorted(ALLOWED_SCHEMES)} are permitted."
        )

    if not parsed.hostname:
        raise DisallowedDestinationError("URL must contain a valid hostname.")

    validate_hostname_and_ips(parsed.hostname)
    return parsed


async def safe_fetch_url(
    url: str,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> SafeFetchResult:
    """Fetches a URL safely enforcing scheme, SSRF checks, redirects, size, and timeouts (UT-28)."""
    current_url = url.strip()
    redirect_history: list[str] = []

    # Initial check
    validate_url(current_url)

    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))

    # We manage redirects manually to validate destination at each hop
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        redirect_count = 0

        while True:
            try:
                # Use stream to enforce response size cap
                async with client.stream("GET", current_url) as resp:
                    # Check for redirect status
                    if resp.is_redirect:
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise DisallowedDestinationError(
                                f"Exceeded maximum allowed redirects ({max_redirects})."
                            )

                        location = resp.headers.get("location")
                        if not location:
                            raise DisallowedDestinationError(
                                "Redirect response missing Location header."
                            )

                        # Resolve relative redirect URLs against current URL
                        redirect_url = urllib.parse.urljoin(current_url, location)
                        logger.debug("Redirecting from '%s' to '%s'", current_url, redirect_url)

                        # Validate redirect destination BEFORE making request
                        validate_url(redirect_url)

                        redirect_history.append(current_url)
                        current_url = redirect_url
                        continue

                    # Check Content-Length header if present
                    content_length = resp.headers.get("content-length")
                    if content_length and int(content_length) > max_size_bytes:
                        raise ResponseSizeLimitError(
                            f"Response size ({content_length} bytes) exceeds limit ({max_size_bytes} bytes)."
                        )

                    # Stream and count bytes
                    chunks = []
                    bytes_read = 0
                    async for chunk in resp.aiter_bytes():
                        bytes_read += len(chunk)
                        if bytes_read > max_size_bytes:
                            raise ResponseSizeLimitError(
                                f"Response exceeded maximum size limit of {max_size_bytes} bytes."
                            )
                        chunks.append(chunk)

                    raw_body = b"".join(chunks)
                    # Attempt decode (prefer utf-8, fallback with replacement)
                    content_text = raw_body.decode(resp.encoding or "utf-8", errors="replace")

                    return SafeFetchResult(
                        url=current_url,
                        status_code=resp.status_code,
                        content=content_text,
                        content_type=resp.headers.get("content-type", "text/plain"),
                        size_bytes=bytes_read,
                        redirect_history=redirect_history,
                        source="web_fetch",
                        timestamp=utc_now().isoformat(),
                        verified=True,
                    )

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning("Network error fetching '%s': %s", current_url, e)
                raise URLGuardError(f"Connection error fetching URL: {e}") from e


def safe_fetch_url_sync(
    url: str,
    max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> SafeFetchResult:
    """Synchronously fetches a URL safely enforcing scheme, SSRF checks, redirects, size, and timeouts (UT-28)."""
    current_url = url.strip()
    redirect_history: list[str] = []

    validate_url(current_url)

    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))

    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        redirect_count = 0

        while True:
            try:
                with client.stream("GET", current_url) as resp:
                    if resp.is_redirect:
                        redirect_count += 1
                        if redirect_count > max_redirects:
                            raise DisallowedDestinationError(
                                f"Exceeded maximum allowed redirects ({max_redirects})."
                            )

                        location = resp.headers.get("location")
                        if not location:
                            raise DisallowedDestinationError(
                                "Redirect response missing Location header."
                            )

                        next_url = urllib.parse.urljoin(current_url, location)
                        redirect_history.append(current_url)
                        validate_url(next_url)
                        current_url = next_url
                        continue

                    if resp.status_code >= 400:
                        raise URLGuardError(f"HTTP {resp.status_code} error fetching destination.")

                    chunks = []
                    bytes_read = 0
                    for chunk in resp.iter_bytes():
                        bytes_read += len(chunk)
                        if bytes_read > max_size_bytes:
                            raise ResponseSizeLimitError(
                                f"Response exceeded maximum size limit of {max_size_bytes} bytes."
                            )
                        chunks.append(chunk)

                    raw_body = b"".join(chunks)
                    content_text = raw_body.decode(resp.encoding or "utf-8", errors="replace")

                    return SafeFetchResult(
                        url=current_url,
                        status_code=resp.status_code,
                        content=content_text,
                        content_type=resp.headers.get("content-type", "text/plain"),
                        size_bytes=bytes_read,
                        redirect_history=redirect_history,
                        source="web_fetch",
                        timestamp=utc_now().isoformat(),
                        verified=True,
                    )

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning("Network error fetching '%s': %s", current_url, e)
                raise URLGuardError(f"Connection error fetching URL: {e}") from e


@tool
async def safe_web_fetch_tool(url: str) -> dict[str, Any]:
    """Safely reads the content of a public web page with strict SSRF protection and size limits.

    Only http and https schemes are permitted. Private, loopback, and metadata destinations are refused.
    """
    result = await safe_fetch_url(url)
    return result.model_dump()
