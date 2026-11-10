import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_request_id_is_returned_in_response_header():
    request_id = str(uuid.uuid4())

    response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_request_id_is_generated_when_missing():
    response = client.get("/health")

    assert response.status_code == 200
    generated_id = response.headers["X-Request-ID"]
    assert str(uuid.UUID(generated_id)) == generated_id


def test_invalid_request_id_is_replaced():
    response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})

    assert response.status_code == 200
    generated_id = response.headers["X-Request-ID"]
    assert str(uuid.UUID(generated_id)) == generated_id
    assert generated_id != "not-a-uuid"


def test_validation_error_uses_standard_error_format():
    response = client.post("/auth/login", json={})

    if response.status_code == 422:
        body = response.json()
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["request_id"] == response.headers["X-Request-ID"]
        assert isinstance(body["error"]["details"], list)
