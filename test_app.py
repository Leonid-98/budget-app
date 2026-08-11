import pytest

from app import app


@pytest.fixture
def client():
    return app.test_client()


def test_index_serves_calculator_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Calculator" in response.text


@pytest.mark.parametrize(
    ("a", "b", "operator", "expected"),
    [
        (10, 5, "+", 15),
        (10, 5, "-", 5),
        (10, 5, "*", 50),
        (10, 4, "/", 2.5),
        (0.1, 0.2, "+", pytest.approx(0.3)),
        (-3, 7, "*", -21),
    ],
)
def test_calculate_success(client, a, b, operator, expected):
    response = client.post("/api/calculate", json={"a": a, "b": b, "operator": operator})

    assert response.status_code == 200
    assert response.json["result"] == expected


def test_division_by_zero_returns_400(client):
    response = client.post("/api/calculate", json={"a": 1, "b": 0, "operator": "/"})

    assert response.status_code == 400
    assert "zero" in response.json["error"].lower()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"a": 1, "b": 2},
        {"a": 1, "b": 2, "operator": "%"},
        {"a": "ten", "b": 2, "operator": "+"},
        {"a": None, "b": 2, "operator": "+"},
        {"a": True, "b": 2, "operator": "+"},
        {"b": 2, "operator": "+"},
        [1, 2, "+"],
    ],
)
def test_invalid_payload_returns_400(client, payload):
    response = client.post("/api/calculate", json=payload)

    assert response.status_code == 400
    assert "error" in response.json


def test_non_json_body_returns_400(client):
    response = client.post("/api/calculate", data="a=1&b=2", content_type="application/x-www-form-urlencoded")

    assert response.status_code == 400
    assert "error" in response.json
