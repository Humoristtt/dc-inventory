from app.main import app


def test_access_request_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/access-requests" in paths
    assert "/api/access-requests/me" in paths
