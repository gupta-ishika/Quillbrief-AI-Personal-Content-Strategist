from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_allowed_host_and_origin_succeeds() -> None:
    # GET route with proper Host
    res_get = client.get("/health", headers={"Host": f"localhost:{settings.backend_port}"})
    assert res_get.status_code == 200

    # OPTIONS request (CORS preflight)
    res_options = client.options(
        "/api/v1/runs",
        headers={
            "Host": f"localhost:{settings.backend_port}",
            "Origin": settings.frontend_origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res_options.status_code == 200
    assert res_options.headers.get("access-control-allow-origin") == settings.frontend_origin
    # Verify no wildcard origin and no credentials
    assert res_options.headers.get("access-control-allow-origin") != "*"
    assert res_options.headers.get("access-control-allow-credentials") is None


def test_host_header_dns_rebinding_protection() -> None:
    # 1. Foreign host is refused (UT-27)
    res_evil = client.get("/health", headers={"Host": "evil.com"})
    assert res_evil.status_code == 400
    assert res_evil.json()["error"]["code"] == "INVALID_HOST"

    # 2. Correct name with missing port is refused (UT-27)
    if settings.backend_port not in (80, 443):
        res_no_port = client.get("/health", headers={"Host": "localhost"})
        assert res_no_port.status_code == 400
        assert res_no_port.json()["error"]["code"] == "INVALID_HOST"

    # 3. Correct name with wrong port is refused (UT-27)
    res_wrong_port = client.get("/health", headers={"Host": "localhost:9999"})
    assert res_wrong_port.status_code == 400
    assert res_wrong_port.json()["error"]["code"] == "INVALID_HOST"


def test_origin_header_state_changing_requests() -> None:
    # 1. Foreign Origin returns 403 ORIGIN_NOT_ALLOWED (UT-27)
    res_foreign = client.post(
        "/api/v1/runs",
        headers={
            "Host": f"localhost:{settings.backend_port}",
            "Origin": "http://evil-attacker.com",
            "Content-Type": "application/json",
        },
        json={"goal_text": "test"},
    )
    assert res_foreign.status_code == 403
    assert res_foreign.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"

    # 2. Missing Origin returns 403 ORIGIN_NOT_ALLOWED (UT-27)
    res_missing = client.post(
        "/api/v1/runs",
        headers={
            "Host": f"localhost:{settings.backend_port}",
            "Content-Type": "application/json",
        },
        json={"goal_text": "test"},
    )
    assert res_missing.status_code == 403
    assert res_missing.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"


def test_json_only_content_type_rule() -> None:
    # Non-JSON content type returns 400 INVALID_CONTENT_TYPE (UT-27)
    res_text = client.post(
        "/api/v1/runs",
        headers={
            "Host": f"localhost:{settings.backend_port}",
            "Origin": settings.frontend_origin,
            "Content-Type": "text/plain",
        },
        content="plain text body",
    )
    assert res_text.status_code == 400
    assert res_text.json()["error"]["code"] == "INVALID_CONTENT_TYPE"
