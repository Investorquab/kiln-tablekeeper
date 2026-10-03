"""Stage 3 spec-derived black-box regressions.

The shipped Stage 3 sample only smoke-checks policy terms, a shallow explanation,
creation history, and one recurring agreement. These checks target the deeper
contract through HTTP and the existing Stage 2 browser surface; they do not inspect
service internals.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from types import SimpleNamespace
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(3)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ADA = {"id": "u_ada", "email": "ada@example.com", "password": "correct horse", "display_name": "Ada"}
BOB = {"id": "u_bob", "email": "bob@example.com", "password": "correct horse", "display_name": "Bob"}


def all_week(opens="18:00", closes="23:00"):
    return [{"weekday": day, "opens": opens, "closes": closes} for day in WEEKDAYS]


def restaurant(rid="r_anker", *, name="Zum Anker", timezone="Europe/Berlin",
               slot_minutes=30, reservation_duration_minutes=90,
               cancellation_cutoff_minutes=120, opening_hours=None, tables=None):
    return {"id": rid, "name": name, "timezone": timezone,
            "slot_minutes": slot_minutes,
            "reservation_duration_minutes": reservation_duration_minutes,
            "cancellation_cutoff_minutes": cancellation_cutoff_minutes,
            "opening_hours": all_week() if opening_hours is None else opening_hours,
            "tables": tables if tables is not None else [
                {"id": "t_1", "label": "1", "capacity": 2},
                {"id": "t_2", "label": "2", "capacity": 4},
                {"id": "t_3", "label": "3", "capacity": 6}]}


def fixture(*, users=None, restaurants=None, reservations=None):
    return {"users": [ADA, BOB] if users is None else users,
            "restaurants": [restaurant()] if restaurants is None else restaurants,
            "reservations": reservations or []}


def booking_date(timezone="Europe/Berlin", lead=7):
    today = dt.datetime.now(ZoneInfo(timezone)).date()
    return (today + dt.timedelta(days=lead)).isoformat()


def local(date, hhmm="19:00"):
    return f"{date}T{hhmm}"


def managed_restaurant(**kwargs):
    return {**restaurant(**kwargs), "manager_user_ids": [ADA["id"]]}


def policy(date, **overrides):
    return (dict(effective_from=date, slot_minutes=30,
                 reservation_duration_minutes=90, cancellation_cutoff_minutes=120,
                 opening_hours=all_week(),
                 capacities={"t_1": 2, "t_2": 4, "t_3": 6}) | overrides)


fx = SimpleNamespace(ADA=ADA, BOB=BOB, all_week=all_week, restaurant=restaurant,
                     fixture=fixture, booking_date=booking_date, local=local,
                     managed_restaurant=managed_restaurant, policy=policy)


@pytest.fixture
def world(reset, api):
    state = fx.fixture()
    reset(state)
    restaurant_data = state["restaurants"][0]
    return SimpleNamespace(fixture=state, restaurant=restaurant_data,
        rid=restaurant_data["id"], timezone=restaurant_data["timezone"],
        date=fx.booking_date(restaurant_data["timezone"]),
        ada=api().authenticate(ADA["email"], ADA["password"]),
        bob=api().authenticate(BOB["email"], BOB["password"]))


@pytest.fixture
def book(world):
    def _book(client=None, *, table_id="t_2", at="19:00", party_size=4,
              key=None, restaurant_id=None, starts_at_local=None, **extra):
        body = {"restaurant_id": world.rid if restaurant_id is None else restaurant_id,
                "table_id": table_id,
                "starts_at_local": starts_at_local or fx.local(world.date, at),
                "party_size": party_size}
        body.update(extra)
        return (client or world.ada).post("/reservations", json=body,
            idempotency_key=new_key() if key is None else key)
    return _book


def policy_body(date, **overrides):
    return fx.policy(date, **overrides)


def publish(client, date, *, rid="r_anker", key=None, **overrides):
    return client.post(
        f"/restaurants/{rid}/policies",
        json=policy_body(date, **overrides), idempotency_key=key or new_key(),
    )


def reservation_body(date, *, table_id="t_2", table_ids=None, at="19:00", party=4):
    body = {"restaurant_id": "r_anker", "starts_at_local": fx.local(date, at),
            "party_size": party}
    if table_ids is None:
        body["table_id"] = table_id
    else:
        body["table_ids"] = table_ids
    return body


def create(client, date, *, key=None, **kwargs):
    return client.post("/reservations", json=reservation_body(date, **kwargs),
                       idempotency_key=key or new_key())


def next_berlin_fallback():
    today = dt.datetime.now(ZoneInfo("Europe/Berlin")).date()
    for year in range(today.year, today.year + 4):
        day = dt.date(year, 10, 31)
        while day.weekday() != 6:
            day -= dt.timedelta(days=1)
        if day > today:
            return day
    raise AssertionError("could not find a future Berlin fall-back date")


def test_policy_versions_follow_effective_date_and_replay_original_terms(world):
    future = (dt.date.fromisoformat(world.date) + dt.timedelta(days=14)).isoformat()
    earlier = (dt.date.fromisoformat(world.date) + dt.timedelta(days=7)).isoformat()
    key = new_key()
    first = assert_status(publish(world.ada, future, key=key,
                                  reservation_duration_minutes=60), 201).json()
    assert first["policy_version"] == 1
    assert assert_status(world.ada.post(f"/restaurants/{world.rid}/policies",
        json=policy_body(future, reservation_duration_minutes=60),
        idempotency_key=key), 200).json() == first

    second = assert_status(publish(world.ada, earlier,
                                   reservation_duration_minutes=120), 201).json()
    at_earlier_date = (dt.date.fromisoformat(world.date) + dt.timedelta(days=10)).isoformat()
    accepted_old = assert_status(create(world.ada, at_earlier_date), 201).json()
    assert accepted_old["accepted_terms"]["policy_version"] == second["policy_version"]
    assert accepted_old["accepted_terms"]["reservation_duration_minutes"] == 120

    third = assert_status(publish(world.ada, future,
                                  reservation_duration_minutes=60,
                                  cancellation_cutoff_minutes=0), 201).json()
    explained = assert_status(world.ada.get("/availability", params={
        "restaurant_id": world.rid, "date": future, "party_size": 4,
        "explain": "true"}), 200).json()["slots"]
    future_slot = next(s for s in explained if s["starts_at_local"].endswith("19:00"))
    assert all(e["policy_version"] == third["policy_version"] for e in future_slot["explain"])
    accepted_future = assert_status(create(world.ada, future), 201).json()
    assert third["policy_version"] > second["policy_version"]
    assert accepted_future["accepted_terms"]["policy_version"] == third["policy_version"]
    assert accepted_old["accepted_terms"]["policy_version"] == second["policy_version"]
    amended = assert_status(world.ada.patch(f"/reservations/{accepted_old['reference']}", json={
        "table_id": "t_3", "starts_at_local": fx.local(future, "19:00"),
        "expected_revision": 1}), 200).json()
    assert amended["revision"] == 2
    assert amended["accepted_terms"]["policy_version"] == third["policy_version"]
    amended_history = world.ada.get(
        f"/reservations/{accepted_old['reference']}/history").json()["entries"]
    assert amended_history[0]["accepted_terms"]["policy_version"] == second["policy_version"]
    assert amended_history[1]["accepted_terms"]["policy_version"] == third["policy_version"]
    assert [p["policy_version"] for p in world.ada.get(
        f"/restaurants/{world.rid}/policies").json()["policies"]] == [1, 2, 3]
    detail = world.ada.get(f"/restaurants/{world.rid}").json()
    assert detail["reservation_duration_minutes"] == 90


def test_policy_authorization_bounds_and_failed_version_allocation(reset, api, anon):
    restaurant = fx.managed_restaurant()
    reset(fx.fixture(restaurants=[restaurant]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    bob = api().authenticate(fx.BOB["email"], fx.BOB["password"])
    date = fx.booking_date()
    body = policy_body(date)

    assert_error(anon.post("/restaurants/r_anker/policies", json=body,
                           idempotency_key=new_key()), 401, "unauthenticated")
    assert_error(bob.post("/restaurants/r_anker/policies", json=body,
                          idempotency_key=new_key()), 403, "forbidden")

    invalid = [
        {**body, "slot_minutes": True},
        {**body, "reservation_duration_minutes": 1441},
        {**body, "cancellation_cutoff_minutes": 10081},
        {**body, "capacities": {"t_1": 2, "t_2": 4}},
        {**body, "capacities": {"t_1": 2, "t_2": 4, "t_3": False}},
        {**body, "effective_from": "2026-02-30"},
    ]
    responses = [ada.post("/restaurants/r_anker/policies", json=value,
                          idempotency_key=new_key()) for value in invalid]
    for response in responses:
        assert_error(response, 422, "validation_failed")
        assert response.status_code < 500

    valid = assert_status(publish(ada, date, slot_minutes=1,
                                  reservation_duration_minutes=1440,
                                  cancellation_cutoff_minutes=0), 201).json()
    assert valid["policy_version"] == 1
    assert_error(ada.post("/restaurants/not-a-restaurant/policies", json=body,
                          idempotency_key=new_key()), 404, "not_found")


def test_explanation_reports_both_rules_for_every_table_and_keeps_legacy_shape(world, book):
    created = assert_status(book(table_id="t_2", at="19:00", party_size=4), 201).json()
    params = {"restaurant_id": world.rid, "date": world.date,
              "party_size": 7, "explain": "true"}
    slots = assert_status(world.ada.get("/availability", params=params), 200).json()["slots"]
    slot = next(s for s in slots if s["starts_at_local"].endswith("19:00"))
    assert [e["table_id"] for e in slot["explain"]] == ["t_1", "t_2", "t_3"]
    assert all([r["rule"] for r in e["rules"]] == ["capacity", "no_overlap"]
               for e in slot["explain"])
    by_id = {e["table_id"]: e for e in slot["explain"]}
    assert [r["holds"] for r in by_id["t_2"]["rules"]] == [False, False]
    assert all(e["available"] is False for e in slot["explain"])
    assert slot["available_table_ids"] == []

    plain = assert_status(world.ada.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": 4}), 200).json()
    assert all("explain" not in s for s in plain["slots"])
    assert_error(world.ada.get("/availability", params={**params, "explain": "false"}),
                 422, "validation_failed")
    assert created["reference"]


def test_terms_history_noop_stale_revision_privacy_and_cancel(world, book, anon):
    key = new_key()
    created = assert_status(book(key=key, table_id="t_2", at="19:00", party_size=4), 201).json()
    ref = created["reference"]
    history_url = f"/reservations/{ref}/history"
    before = assert_status(world.ada.get(history_url), 200).json()["entries"]
    assert [e["seq"] for e in before] == [1]
    assert before[0]["accepted_terms"] == created["accepted_terms"]

    noop = assert_status(world.ada.patch(f"/reservations/{ref}", json={
        "table_id": "t_2", "expected_revision": 1}), 200).json()
    assert noop["revision"] == 1
    assert noop["accepted_terms"] == created["accepted_terms"]
    assert assert_status(world.ada.get(history_url), 200).json()["entries"] == before

    changed = assert_status(world.ada.patch(f"/reservations/{ref}", json={
        "table_id": "t_3", "expected_revision": 1}), 200).json()
    assert changed["revision"] == 2
    assert_error(world.ada.patch(f"/reservations/{ref}", json={
        "party_size": 0, "expected_revision": 1}), 409, "stale_revision")
    entries = assert_status(world.ada.get(history_url), 200).json()["entries"]
    assert [e["seq"] for e in entries] == [1, 2]
    assert entries[1]["changes"] == [
        {"field": "table_id", "from": "t_2", "to": "t_3"}]
    assert entries[1]["revision"] == 2
    decision = assert_status(world.ada.get(f"/reservations/{ref}/decision"), 200).json()
    assert decision["revision"] == 2 and decision["accepted_terms"] == changed["accepted_terms"]

    for client in (world.bob, anon):
        assert_error(client.get(history_url), 404, "not_found")
        assert_error(client.get(f"/reservations/{ref}/decision"), 404, "not_found")

    assert assert_status(world.ada.post("/reservations", json=reservation_body(
        world.date, table_id="t_2", at="19:00", party=4), idempotency_key=key), 200).json() == created
    cancelled = assert_status(world.ada.post(f"/reservations/{ref}/cancel"), 200).json()
    assert cancelled["revision"] == 3
    final = assert_status(world.ada.get(history_url), 200).json()["entries"]
    assert final[-1]["event"] == "cancelled" and final[-1]["changes"] == []


def test_declared_pair_history_uses_canonical_order_and_reversed_pair_is_noop(reset, api):
    restaurant = fx.managed_restaurant()
    restaurant["combinable"] = [["t_1", "t_2"], ["t_2", "t_3"]]
    reset(fx.fixture(restaurants=[restaurant]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    date = fx.booking_date()
    created = assert_status(create(ada, date, table_ids=["t_2", "t_1"], party=6), 201).json()
    ref = created["reference"]
    assert created["table_ids"] == ["t_1", "t_2"]
    history_url = f"/reservations/{ref}/history"
    entries = assert_status(ada.get(history_url), 200).json()["entries"]
    assert entries[0]["changes"] == [
        {"field": "table_ids", "from": None, "to": ["t_1", "t_2"]},
        {"field": "starts_at_local", "from": None, "to": fx.local(date, "19:00")},
        {"field": "party_size", "from": None, "to": 6},
    ]
    noop = assert_status(ada.patch(f"/reservations/{ref}", json={
        "table_ids": ["t_2", "t_1"]}), 200).json()
    assert noop["revision"] == 1
    assert len(ada.get(history_url).json()["entries"]) == 1
    changed = assert_status(ada.patch(f"/reservations/{ref}", json={
        "table_ids": ["t_2", "t_3"]}), 200).json()
    assert changed["revision"] == 2 and changed["table_ids"] == ["t_2", "t_3"]
    entry = ada.get(history_url).json()["entries"][-1]
    assert entry["changes"] == [
        {"field": "table_ids", "from": ["t_1", "t_2"], "to": ["t_2", "t_3"]}]


def test_recurring_policy_failure_is_all_or_none_and_failed_key_can_be_reused(world):
    anchor = assert_status(create(world.ada, world.date, table_id="t_2", party=4), 201).json()
    next_date = (dt.date.fromisoformat(world.date) + dt.timedelta(days=7)).isoformat()
    assert_status(publish(world.ada, next_date,
                          capacities={"t_1": 2, "t_2": 2, "t_3": 6}), 201)
    body = {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 1}
    key = new_key()
    assert_error(world.ada.post("/series", json=body, idempotency_key=key),
                 422, "party_exceeds_capacity")
    reservations = world.ada.get("/reservations").json()["reservations"]
    assert [r["reference"] for r in reservations] == [anchor["reference"]]
    assert_error(world.ada.get("/series/not-created"), 404, "not_found")

    invalid_series = (
        {"anchor_reference": anchor["reference"], "count": 1, "interval_weeks": 1},
        {"anchor_reference": anchor["reference"], "count": 13, "interval_weeks": 1},
        {"anchor_reference": anchor["reference"], "count": True, "interval_weeks": 1},
        {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 0},
        {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 5},
        {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": False},
    )
    for invalid in invalid_series:
        assert_error(world.ada.post("/series", json=invalid,
                                    idempotency_key=new_key()), 422, "validation_failed")

    updated = assert_status(publish(world.ada, next_date,
        capacities={"t_1": 2, "t_2": 4, "t_3": 6}), 201).json()
    adopted = assert_status(world.ada.post("/series", json=body,
                                           idempotency_key=key), 201).json()
    assert len(adopted["occurrences"]) == 2
    assert adopted["occurrences"][0]["reference"] == anchor["reference"]
    assert adopted["occurrences"][0]["reservation"]["accepted_terms"]["policy_version"] == 0
    assert adopted["occurrences"][1]["reservation"]["accepted_terms"]["policy_version"] == updated["policy_version"]
    assert adopted["occurrences"][0]["reference"] != adopted["occurrences"][1]["reference"]
    assert {r["reference"] for r in world.ada.get("/reservations").json()["reservations"]} == {
        anchor["reference"], adopted["occurrences"][1]["reference"]}




def test_recurring_fall_back_uses_first_local_occurrence_and_replay_is_frozen(reset, api):
    restaurant = fx.managed_restaurant(
        slot_minutes=30, reservation_duration_minutes=30,
        cancellation_cutoff_minutes=0,
        opening_hours=fx.all_week("02:00", "05:00"))
    reset(fx.fixture(restaurants=[restaurant]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    fallback = next_berlin_fallback()
    anchor_date = (fallback - dt.timedelta(days=7)).isoformat()
    anchor = assert_status(create(ada, anchor_date, at="02:30", table_id="t_2", party=4), 201).json()
    body = {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 1}
    key = new_key()
    adopted = assert_status(ada.post("/series", json=body, idempotency_key=key), 201).json()
    occurrence = adopted["occurrences"][1]["reservation"]
    assert occurrence["starts_at_local"] == f"{fallback.isoformat()}T02:30"
    assert dt.datetime.fromisoformat(occurrence["starts_at"]).utcoffset() == dt.timedelta(hours=2)

    changed = assert_status(ada.patch(f"/reservations/{occurrence['reference']}", json={
        "table_id": "t_3", "expected_revision": 1}), 200).json()
    assert changed["revision"] == 2
    assert_status(ada.post("/series", json=body, idempotency_key=key), 200)
    replay = ada.post("/series", json=body, idempotency_key=key).json()
    assert replay == adopted
    current = assert_status(ada.get(f"/series/{adopted['series_id']}"), 200).json()
    assert current["revision"] == 2
    assert current["occurrences"][1]["reference"] == occurrence["reference"]
    assert current["occurrences"][1]["exception"] is True
    assert current["occurrences"][1]["reservation"]["table_id"] == "t_3"
    assert_error(ada.get(f"/series/{adopted['series_id']}", token=None), 404, "not_found")


def test_collective_move_rolls_back_then_updates_revisions_history_and_series_once(reset, api):
    reset(fx.fixture(restaurants=[fx.restaurant(cancellation_cutoff_minutes=0)]))
    ada = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    date = fx.booking_date()
    anchor = assert_status(create(ada, date, table_id="t_1", party=2), 201).json()
    assert_status(create(ada, date, table_id="t_2", party=4), 201)
    series_body = {"anchor_reference": anchor["reference"], "count": 2, "interval_weeks": 1}
    series = assert_status(ada.post("/series", json=series_body,
                                    idempotency_key=new_key()), 201).json()
    refs = [item["reference"] for item in series["occurrences"]]
    move_key = new_key()
    collision = {"moves": [{"reference": ref, "table_id": "t_2",
                             "expected_revision": 1} for ref in refs]}
    assert_error(ada.post("/reservation-moves", json=collision,
                          idempotency_key=move_key), 409, "table_unavailable")
    unchanged = ada.get(f"/series/{series['series_id']}").json()
    assert unchanged["revision"] == 1
    assert [x["reservation"]["revision"] for x in unchanged["occurrences"]] == [1, 1]
    assert [x["exception"] for x in unchanged["occurrences"]] == [False, False]
    assert all(len(ada.get(f"/reservations/{ref}/history").json()["entries"]) == 1
               for ref in refs)

    success_body = {"moves": [{"reference": ref, "table_id": "t_3",
                                "expected_revision": 1} for ref in refs]}
    moved = assert_status(ada.post("/reservation-moves", json=success_body,
                                   idempotency_key=move_key), 201).json()
    assert [r["revision"] for r in moved["reservations"]] == [2, 2]
    current = ada.get(f"/series/{series['series_id']}").json()
    assert current["revision"] == 2
    assert [x["exception"] for x in current["occurrences"]] == [True, True]
    assert [x["reference"] for x in current["occurrences"]] == refs
    for ref in refs:
        entries = ada.get(f"/reservations/{ref}/history").json()["entries"]
        assert [e["seq"] for e in entries] == [1, 2]
        assert entries[-1]["revision"] == 2
        assert entries[-1]["changes"] == [
            {"field": "table_id", "from": "t_1", "to": "t_3"}]

    replay = assert_status(ada.post("/reservation-moves", json=success_body,
                                    idempotency_key=move_key), 200).json()
    assert replay == moved
    assert ada.get(f"/series/{series['series_id']}").json()["revision"] == 2


def test_stage2_export_import_keeps_login_receipt_reference_and_series_anchor(
        world, previous_api, api):
    legacy_state = fx.fixture()
    assert_status(previous_api.post("/_test/reset", json=legacy_state), 204)
    old = previous_api.authenticate(fx.ADA["email"], fx.ADA["password"])
    body = reservation_body(world.date, table_id="t_2", at="19:00", party=4)
    key = new_key()
    receipt = assert_status(old.post("/reservations", json=body,
                                     idempotency_key=key), 201).json()
    exported = assert_status(old.get("/_test/export"), 200).json()
    upgraded = api(token=old.token)
    assert_status(upgraded.post("/_test/import", json=exported, token=None), 204)

    assert_status(upgraded.get(f"/reservations/{receipt['reference']}"), 200)
    replay = assert_status(upgraded.post("/reservations", json=body,
        idempotency_key=key), 200).json()
    assert replay == receipt
    adopted = assert_status(upgraded.post("/series", json={
        "anchor_reference": receipt["reference"], "count": 2, "interval_weeks": 1},
        idempotency_key=new_key()), 201).json()
    assert adopted["occurrences"][0]["reference"] == receipt["reference"]
    assert adopted["occurrences"][0]["reservation"]["accepted_terms"]["policy_version"] == 0


def test_stage2_booking_grid_and_lookup_survive_policy_and_mobile_viewport(reset, api, page):
    restaurant = fx.managed_restaurant()
    restaurant["combinable"] = [["t_1", "t_2"], ["t_2", "t_3"]]
    reset(fx.fixture(restaurants=[restaurant]))
    manager = api().authenticate(fx.ADA["email"], fx.ADA["password"])
    date = fx.booking_date()
    assert_status(publish(manager, date, slot_minutes=60,
        reservation_duration_minutes=60, cancellation_cutoff_minutes=0,
        opening_hours=fx.all_week("19:00", "22:00"),
        capacities={"t_1": 2, "t_2": 2, "t_3": 6}), 201)

    sel = lambda name: f"[data-testid='{name}']"
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto("/login")
    page.fill(sel("login-email"), fx.ADA["email"])
    page.fill(sel("login-password"), fx.ADA["password"])
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("current-user"))
    page.goto("/")
    page.select_option(sel("restaurant-select"), "r_anker")
    page.fill(sel("date-input"), date)
    page.fill(sel("party-size-input"), "4")
    page.click(sel("search-button"))
    page.wait_for_selector(sel("availability-grid"))
    assert page.get_attribute(sel("slot-t_2-19:00"), "data-available") == "false"
    assert page.get_attribute(sel("slot-t_1+t_2-19:00"), "data-available") == "true"
    page.click(sel("slot-t_1+t_2-19:00"))
    page.wait_for_selector(sel("booking-form"))
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation"))
    ref = page.text_content(sel("confirmation-reference")).strip()
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")

    page.goto("/lookup")
    page.fill(sel("lookup-reference-input"), ref)
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-detail"))
    assert page.text_content(sel("reservation-status")).strip() == "confirmed"
