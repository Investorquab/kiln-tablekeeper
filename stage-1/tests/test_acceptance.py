"""Spec-only Stage 1 black-box regressions.

Start the Stage 1 service at localhost:8080, then run:
    python -m pytest stage-1/tests/test_acceptance.py
Set TABLEKEEPER_BASE_URL to override the URL. Tests use HTTP only.
"""
import datetime as dt
import json
import os
import urllib.error
import urllib.request

import pytest

BASE = os.environ.get("TABLEKEEPER_BASE_URL", "http://localhost:8080").rstrip("/")
DATE = (dt.date.today() + dt.timedelta(days=14)).isoformat()
KEY = "acceptance-key-01"


def call(method, path, *, body=None, token=None, key=None, raw=None):
    headers = {"Accept": "application/json"}
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key is not None:
        headers["Idempotency-Key"] = key
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        resp = exc
    raw_body = resp.read()
    return resp.status, json.loads(raw_body) if raw_body else None


def seed(email="ada@example.com", uid="u_ada", rid="r_acceptance"):
    return {
        "users": [{"id": uid, "email": email, "password": "correct horse",
                   "display_name": "Ada"}],
        "restaurants": [{
            "id": rid, "name": "Acceptance", "timezone": "Europe/Berlin",
            "slot_minutes": 30, "reservation_duration_minutes": 90,
            "cancellation_cutoff_minutes": 120,
            "opening_hours": [
                {"weekday": d, "opens": "00:00", "closes": "23:59"}
                for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            ],
            "tables": [
                {"id": "t_1", "label": "1", "capacity": 2},
                {"id": "t_2", "label": "2", "capacity": 4},
                {"id": "t_3", "label": "3", "capacity": 6},
            ],
        }],
        "reservations": [],
    }


@pytest.fixture
def world():
    fixture = seed()
    assert call("POST", "/_test/reset", body=fixture)[0] == 204
    status, login = call("POST", "/auth/login", body={
        "email": "ada@example.com", "password": "correct horse"})
    assert status == 200
    return {"fixture": fixture, "token": login["token"]}


def booking(table="t_2", at="20:00", party=4, restaurant="r_acceptance"):
    return {"restaurant_id": restaurant, "table_id": table,
            "starts_at_local": f"{DATE}T{at}", "party_size": party}


def create(world, key, **kwargs):
    return call("POST", "/reservations", body=booking(**kwargs),
                token=world["token"], key=key)


def expect_error(response, status, code):
    assert response[0] == status, response[1]
    assert response[1]["error"]["code"] == code
    assert isinstance(response[1]["error"]["message"], str)


def get_reservation(world, ref):
    return call("GET", f"/reservations/{ref}", token=world["token"])


def test_failed_create_key_is_reusable(world):
    expect_error(create(world, KEY, table="unknown"), 404, "not_found")
    created = create(world, KEY)
    assert created[0] == 201, created[1]
    rows = call("GET", "/reservations", token=world["token"])
    assert [r["reference"] for r in rows[1]["reservations"]] == [
        created[1]["reference"]]


def test_replay_is_resolved_before_validation_and_survives_cancel(world):
    original = create(world, KEY)
    assert original[0] == 201, original[1]
    invalid_reuse = call("POST", "/reservations", body=booking(party=0),
                         token=world["token"], key=KEY)
    expect_error(invalid_reuse, 409, "idempotency_key_reuse")

    ref = original[1]["reference"]
    cancelled = call("POST", f"/reservations/{ref}/cancel", token=world["token"])
    assert cancelled[0] == 200 and cancelled[1]["status"] == "cancelled"
    replay = create(world, KEY)
    assert replay[0] == 200 and replay[1] == original[1]


def test_failed_batch_rolls_back_and_keeps_key_reusable(world):
    a = create(world, "create-a", table="t_2", at="18:00")
    b = create(world, "create-b", table="t_3", at="19:30")
    assert a[0] == b[0] == 201
    refs = [a[1]["reference"], b[1]["reference"]]
    before = [get_reservation(world, ref)[1] for ref in refs]

    failed = call("POST", "/reservation-moves", body={"moves": [
        {"reference": refs[0], "table_id": "t_1"},
        {"reference": refs[1], "party_size": 0},
    ]}, token=world["token"], key=KEY)
    expect_error(failed, 422, "validation_failed")
    assert [get_reservation(world, ref)[1] for ref in refs] == before

    retried = call("POST", "/reservation-moves", body={"moves": [
        {"reference": refs[0], "table_id": "t_1"},
        {"reference": refs[1]},
    ]}, token=world["token"], key=KEY)
    assert retried[0] == 201, retried[1]
    after = [get_reservation(world, ref)[1] for ref in refs]
    assert after[0]["table_id"] == "t_1"
    assert after[1] == before[1]
    assert [r["reference"] for r in retried[1]["reservations"]] == refs


def test_import_replaces_state_preserving_create_receipt_and_invalid_import_is_atomic(world):
    original = create(world, KEY)
    assert original[0] == 201, original[1]
    status, snapshot = call("GET", "/_test/export")
    assert status == 200
    assert snapshot["track"] == "tablekeeper" and snapshot["format_version"] == 1

    destination = seed(email="dest@example.com", uid="u_dest", rid="r_dest")
    assert call("POST", "/_test/reset", body=destination)[0] == 204
    assert call("POST", "/_test/import", body=snapshot)[0] == 204
    login_status, login = call("POST", "/auth/login", body={
        "email": "ada@example.com", "password": "correct horse"})
    assert login_status == 200
    restored = call("GET", f"/reservations/{original[1]['reference']}",
                    token=login["token"])
    assert restored == (200, original[1])
    replay = call("POST", "/reservations", body=booking(),
                  token=world["token"], key=KEY)
    assert replay == (200, original[1])
    expect_error(call("POST", "/auth/login", body={
        "email": "dest@example.com", "password": "correct horse"}),
        401, "unauthenticated")

    for invalid in (
        {"track": "wrong", "format_version": 1, "state": snapshot["state"]},
        {"track": "tablekeeper", "format_version": 99, "state": snapshot["state"]},
        {"track": "tablekeeper", "format_version": 1, "state": None},
        {},
    ):
        expect_error(call("POST", "/_test/import", body=invalid),
                     422, "validation_failed")
        current = call("GET", "/reservations", token=login["token"])
        assert current[0] == 200 and current[1]["reservations"] == [original[1]]
    expect_error(call("POST", "/_test/import", raw=b"{"),
                 400, "malformed_request")
    current = call("GET", "/reservations", token=login["token"])
    assert current[0] == 200 and current[1]["reservations"] == [original[1]]



