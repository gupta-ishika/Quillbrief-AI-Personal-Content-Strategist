from unittest.mock import MagicMock, patch

import pytest

from app.tools.url_guard import (
    DisallowedDestinationError,
    InvalidSchemeError,
    ResponseSizeLimitError,
    is_ip_allowed,
    safe_fetch_url,
    validate_url,
)


def test_scheme_validation() -> None:
    """UT-28: Schemes other than http and https are refused."""
    with pytest.raises(InvalidSchemeError):
        validate_url("file:///etc/passwd")

    with pytest.raises(InvalidSchemeError):
        validate_url("ftp://example.com/file.txt")

    with pytest.raises(InvalidSchemeError):
        validate_url("gopher://example.com")

    with pytest.raises(InvalidSchemeError):
        validate_url("javascript:alert(1)")

    with pytest.raises(InvalidSchemeError):
        validate_url("")


def test_is_ip_allowed_loopback() -> None:
    """UT-28: Loopback addresses are refused."""
    for ip in ["127.0.0.1", "127.0.1.1", "127.255.255.255", "::1"]:
        allowed, reason = is_ip_allowed(ip)
        assert not allowed
        assert "Loopback" in reason


def test_is_ip_allowed_private() -> None:
    """UT-28: Private addresses are refused."""
    for ip in [
        "10.0.0.1",
        "10.255.255.255",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "fc00::1",
    ]:
        allowed, reason = is_ip_allowed(ip)
        assert not allowed
        assert "Private" in reason


def test_is_ip_allowed_link_local_and_metadata() -> None:
    """UT-28: Link-local and cloud metadata addresses are refused."""
    for ip in ["169.254.169.254", "169.254.1.1", "fe80::1", "100.100.100.200"]:
        allowed, reason = is_ip_allowed(ip)
        assert not allowed
        assert "metadata" in reason.lower() or "link-local" in reason.lower()


def test_is_ip_allowed_multicast_reserved_unspecified() -> None:
    for ip in ["224.0.0.1", "ff02::1", "0.0.0.0", "::", "240.0.0.1"]:
        allowed, reason = is_ip_allowed(ip)
        assert not allowed


def test_is_ip_allowed_public_ips() -> None:
    for ip in ["8.8.8.8", "1.1.1.1", "93.184.216.34"]:
        allowed, reason = is_ip_allowed(ip)
        assert allowed
        assert reason == ""


def test_validate_url_blocks_localhost_and_metadata_hostnames() -> None:
    with pytest.raises(DisallowedDestinationError):
        validate_url("http://localhost:8000/api")

    with pytest.raises(DisallowedDestinationError):
        validate_url("http://metadata.google.internal/computeMetadata/v1/")

    with pytest.raises(DisallowedDestinationError):
        validate_url("http://instance-data/latest/meta-data/")


@pytest.mark.asyncio
async def test_safe_fetch_blocks_disallowed_destination() -> None:
    with pytest.raises(DisallowedDestinationError):
        await safe_fetch_url("http://127.0.0.1:8000/api/v1/health")

    with pytest.raises(DisallowedDestinationError):
        await safe_fetch_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_safe_fetch_redirect_to_disallowed_refused() -> None:
    """UT-28: Redirects that lead to disallowed addresses are refused."""
    # Mock redirect response from allowed URL to localhost
    with patch("app.tools.url_guard.validate_url") as mock_validate:
        # Initial URL passes validation
        mock_validate.return_value = None

        with patch("httpx.AsyncClient.stream") as mock_stream:
            # First response is a 302 redirect to http://127.0.0.1
            redirect_resp = MagicMock()
            redirect_resp.is_redirect = True
            redirect_resp.headers = {"location": "http://127.0.0.1:8000/secret"}

            # Context manager returns redirect_resp
            mock_stream.return_value.__aenter__.return_value = redirect_resp

            # When following redirect, validate_url will be called with redirect target
            # Simulate validate_url failing on the redirect target
            mock_validate.side_effect = [
                None,
                DisallowedDestinationError("Loopback address is forbidden"),
            ]

            with pytest.raises(DisallowedDestinationError) as exc_info:
                await safe_fetch_url("https://example.com/redirect")

            assert "Loopback" in str(exc_info.value) or "disallowed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_safe_fetch_size_cap_enforced() -> None:
    """UT-28: Time and size caps hold."""
    with patch("app.tools.url_guard.validate_url", return_value=None):
        with patch("httpx.AsyncClient.stream") as mock_stream:
            resp = MagicMock()
            resp.is_redirect = False
            resp.headers = {"content-length": "2000000"}  # 2MB > 1MB limit

            mock_stream.return_value.__aenter__.return_value = resp

            with pytest.raises(ResponseSizeLimitError):
                await safe_fetch_url("https://example.com/big_file", max_size_bytes=1000)


@pytest.mark.asyncio
async def test_safe_fetch_success_with_provenance() -> None:
    with patch("app.tools.url_guard.validate_url", return_value=None):
        with patch("httpx.AsyncClient.stream") as mock_stream:
            resp = MagicMock()
            resp.is_redirect = False
            resp.status_code = 200
            resp.headers = {"content-type": "text/html", "content-length": "100"}
            resp.encoding = "utf-8"

            async def mock_chunks():
                yield b"<html><body>Hello World</body></html>"

            resp.aiter_bytes = mock_chunks
            mock_stream.return_value.__aenter__.return_value = resp

            res = await safe_fetch_url("https://example.com/page")
            assert res.status_code == 200
            assert "Hello World" in res.content
            assert res.source == "web_fetch"
            assert res.verified is True
            assert res.size_bytes > 0
            assert len(res.timestamp) > 0
