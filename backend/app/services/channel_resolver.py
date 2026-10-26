"""Channel identifier parser and resolution service (API.md Section 7, UT-35).

Accepted forms:
- @handle
- UC channel ID (UC followed by 22 URL-safe characters, length 24)
- https://youtube.com/@handle (also www. or m.)
- https://youtube.com/channel/<ID> (also www. or m.)

Rejects (returning CHANNEL_IDENTIFIER_INVALID before any network call):
- http://
- /c/, /user/, short links (youtu.be)
- other hosts, look-alikes (youtube.com.example.test)
- embedded credentials (https://user:pass@youtube.com)
- malformed input
"""

import re
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from app.api.errors import AppException
from app.config import settings

HANDLE_REGEX = re.compile(r"^@[a-zA-Z0-9_.-]{1,30}$")
CHANNEL_ID_REGEX = re.compile(r"^UC[a-zA-Z0-9_-]{22}$")
ALLOWED_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com")

IdentifierType = Literal["handle", "channel_id"]


def parse_channel_identifier(identifier: str) -> tuple[IdentifierType, str]:
    """Parses identifier locally without making any network calls.

    Returns:
        (type, value) where type is 'handle' (e.g. '@techchannel')
        or 'channel_id' (e.g. 'UC...')

    Raises:
        AppException(422, 'CHANNEL_IDENTIFIER_INVALID') if invalid.
    """
    raw = identifier.strip()
    if not raw:
        raise AppException(
            status_code=422,
            code="CHANNEL_IDENTIFIER_INVALID",
            message="Channel identifier cannot be empty.",
        )

    # 1. Plain handle
    if raw.startswith("@"):
        if HANDLE_REGEX.match(raw):
            return "handle", raw
        raise AppException(
            status_code=422,
            code="CHANNEL_IDENTIFIER_INVALID",
            message=f"Invalid YouTube handle format: '{raw}'.",
        )

    # 2. Plain channel ID (UC followed by 22 chars = 24 chars total)
    if raw.startswith("UC") and len(raw) == 24:
        if CHANNEL_ID_REGEX.match(raw):
            return "channel_id", raw
        raise AppException(
            status_code=422,
            code="CHANNEL_IDENTIFIER_INVALID",
            message=f"Invalid YouTube channel ID format: '{raw}'.",
        )

    # 3. URL form: must be https://, host in ALLOWED_HOSTS, no userinfo
    if "://" in raw or raw.startswith("http"):
        try:
            parsed = urlsplit(raw)
        except Exception as err:
            raise AppException(
                status_code=422,
                code="CHANNEL_IDENTIFIER_INVALID",
                message="Malformed URL identifier.",
            ) from err

        # Must be https only (http is refused)
        if parsed.scheme != "https":
            raise AppException(
                status_code=422,
                code="CHANNEL_IDENTIFIER_INVALID",
                message="Only HTTPS YouTube URLs are permitted.",
            )

        # Reject embedded credentials
        if parsed.username or parsed.password:
            raise AppException(
                status_code=422,
                code="CHANNEL_IDENTIFIER_INVALID",
                message="URLs with embedded credentials are not allowed.",
            )

        # Host check (case-insensitive)
        hostname = (parsed.hostname or "").lower()
        if hostname not in ALLOWED_HOSTS:
            raise AppException(
                status_code=422,
                code="CHANNEL_IDENTIFIER_INVALID",
                message=f"Host '{hostname}' is not a permitted YouTube host.",
            )

        path = parsed.path.rstrip("/")

        # https://youtube.com/@handle
        if path.startswith("/@"):
            handle_part = path[1:]  # includes '@'
            if HANDLE_REGEX.match(handle_part):
                return "handle", handle_part
            raise AppException(
                status_code=422,
                code="CHANNEL_IDENTIFIER_INVALID",
                message=f"Invalid handle in URL: '{handle_part}'.",
            )

        # https://youtube.com/channel/UC...
        if path.startswith("/channel/"):
            channel_part = path[len("/channel/") :]
            if CHANNEL_ID_REGEX.match(channel_part):
                return "channel_id", channel_part
            raise AppException(
                status_code=422,
                code="CHANNEL_IDENTIFIER_INVALID",
                message=f"Invalid channel ID in URL: '{channel_part}'.",
            )

        # Reject all other paths (/c/, /user/, etc.)
        raise AppException(
            status_code=422,
            code="CHANNEL_IDENTIFIER_INVALID",
            message="Only /@handle and /channel/<ID> URLs are supported.",
        )

    # Any other pattern is invalid
    raise AppException(
        status_code=422,
        code="CHANNEL_IDENTIFIER_INVALID",
        message=f"Identifier '{raw}' is not a valid YouTube handle, channel ID, or URL.",
    )


async def resolve_channel(
    identifier: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Resolves channel identifier using YouTube Data API if configured (UT-35).

    Returns:
        dict matching ChannelResolveResponse shape.
    """
    id_type, id_value = parse_channel_identifier(identifier)

    # 1. Check if public YouTube API key is configured
    api_key = settings.youtube_api_key
    if not api_key:
        return {
            "resolved": False,
            "reason": "API_KEY_NOT_CONFIGURED",
            "parsed": {"type": id_type, "value": id_value},
        }

    # 2. Call YouTube Data API to resolve
    url = "https://www.googleapis.com/youtube/v3/channels"
    params: dict[str, str] = {
        "part": "snippet",
        "key": api_key,
    }

    if id_type == "channel_id":
        params["id"] = id_value
    else:
        # Handle lookup via forHandle parameter
        params["forHandle"] = id_value.lstrip("@")

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
        close_client = True

    try:
        resp = await client.get(url, params=params)
        if resp.status_code == 404:
            raise AppException(
                status_code=404,
                code="CHANNEL_NOT_FOUND",
                message=f"Channel '{identifier}' not found on YouTube.",
            )

        if resp.status_code != 200:
            return {
                "resolved": False,
                "reason": "LOOKUP_FAILED",
                "parsed": {"type": id_type, "value": id_value},
            }

        data = resp.json()
        items = data.get("items", [])
        if not items:
            raise AppException(
                status_code=404,
                code="CHANNEL_NOT_FOUND",
                message=f"Channel '{identifier}' not found on YouTube.",
            )

        channel_item = items[0]
        channel_id = channel_item.get("id")
        title = channel_item.get("snippet", {}).get("title", "")

        return {
            "resolved": True,
            "channel_id": channel_id,
            "title": title,
            "parsed": {"type": id_type, "value": id_value},
        }
    except AppException:
        raise
    except Exception:
        return {
            "resolved": False,
            "reason": "LOOKUP_FAILED",
            "parsed": {"type": id_type, "value": id_value},
        }
    finally:
        if close_client:
            await client.aclose()
