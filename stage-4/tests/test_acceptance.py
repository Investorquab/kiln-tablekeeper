"""Stage 4 spec-derived checks through HTTP and the existing browser surface.

The shipped sample checks basic pair/single options, a simple amendment, and an
empty closure preview. This suite concentrates on deterministic planning,
revision and atomicity guarantees, migration, and user-visible applied plans.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from harness.concurrent import burst, no_5xx, tally
from harness.http import assert_error, assert_status, new_key

pytestmark = pytest.mark.stage(4)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ADA = {"id": "u_ada", "email": "ada@example.com", "password": "correct horse", "display_name": "Ada"}
BOB = {"id": "u_bob", "email": "bob@example.com", "password": "correct horse", "display_name": "Bob"}
PAIRS = [["t_1", "t_2"], ["t_2", "t_3"]]


def all_week(opens="18:00", closes="23:00"):
    return [{"weekday": d, "opens": opens, "closes": closes} for d in WEEKDAYS]


def restaurant(rid="r_anker", *, slot_minutes=30, duration=90, cutoff=120,
               opening_hours=None, tables=None, pairs=True, manager=True):
    value = {"id": rid, "name": "Zum Anker", "timezone": "Europe/Berlin",
             "slot_minutes": slot_minutes, "reservation_duration_minutes": duration,
             "cancellation_cutoff_minutes": cutoff,
             "opening_hours": all_week() if opening_hours is None else opening_hours,
             "tables": tables if tables is not None else [
                 {"id": "t_1", "label": "1", "capacity": 2},
                 {"id": "t_2", "label": "2", "capacity": 4},
                 {"id": "t_3", "label": "3", "capacity": 6}]}
    if pairs:
        value["combinable"] = PAIRS
    if manager:
        value["manager_user_ids"] = [ADA["id"]]
    return value


def fixture(*, users=None, restaurants=None, reservations=None):
    return {"users": [ADA, BOB] if users is None else users,
            "restaurants": [restaurant()] if restaurants is None else restaurants,
            "reservations": reservations or []}


def booking_date(lead=7):
    return (dt.datetime.now(ZoneInfo("Europe/Berlin")).date() + dt.timedelta(days=lead)).isoformat()


def local(date, time="19:00"):
    return f"{date}T{time}"


def instant(date, time):
    return dt.datetime.fromisoformat(local(date, time)).replace(
        tzinfo=ZoneInfo("Europe/Berlin")).isoformat()


def policy(date, **overrides):
    return (dict(effective_from=date, slot_minutes=30,
                 reservation_duration_minutes=90, cancellation_cutoff_minutes=120,
                 opening_hours=all_week(),
                 capacities={"t_1": 2, "t_2": 4, "t_3": 6}) | overrides)


def booking_body(date, *, table_id="t_2", table_ids=None, at="19:00", party=4):
    body = {"restaurant_id": "r_anker", "starts_at_local": local(date, at), "party_size": party}
    if table_ids is None:
        body["table_id"] = table_id
    else:
        body["table_ids"] = table_ids
    return body


def create(client, date, *, key=None, **fields):
    return client.post("/reservations", json=booking_body(date, **fields),
                       idempotency_key=key or new_key())


def publish(client, date, *, key=None, **fields):
    return client.post("/restaurants/r_anker/policies", json=policy(date, **fields),
                       idempotency_key=key or new_key())


def replan(client, date, table_id, start, end, *, key=None):
    return client.post("/restaurants/r_anker/replans", json={
        "table_id": table_id, "from": instant(date, start), "to": instant(date, end)},
        idempotency_key=key or new_key())


def apply(client, plan_id, *, key=None):
    return client.post(f"/restaurants/r_anker/replans/{plan_id}/apply", json={},
                       idempotency_key=key or new_key())


def rev_probe(client, date):
    return assert_status(replan(client, date, "t_1", "22:30", "22:31"), 201).json()["restaurant_revision"]


def spring_gap_sunday():
    today = dt.datetime.now(ZoneInfo("Europe/Berlin")).date()
    for year in range(today.year, today.year + 4):
        day = dt.date(year, 3, 31)
        while day.weekday() != 6:
            day -= dt.timedelta(days=1)
        if day > today:
            return day
    raise AssertionError("no future spring clock change found")


def fall_back_sunday():
    today = dt.datetime.now(ZoneInfo("Europe/Berlin")).date()
    for year in range(today.year, today.year + 4):
        day = dt.date(year, 10, 31)
        while day.weekday() != 6:
            day -= dt.timedelta(days=1)
        if day > today:
            return day
    raise AssertionError("no future fall clock change found")


@pytest.fixture
def world(reset, api):
    state = fixture()
    reset(state)
    return SimpleNamespace(fixture=state, restaurant=state["restaurants"][0], rid="r_anker",
        date=booking_date(), ada=api().authenticate(ADA["email"], ADA["password"]),
        bob=api().authenticate(BOB["email"], BOB["password"]))


def test_preview_objective_tiers_are_deterministic_and_read_only(reset, api):
    tables = [{"id": f"t_{i}", "label": str(i), "capacity": 4} for i in (1, 2, 3)]
    reset(fixture(restaurants=[restaurant(tables=tables, slot_minutes=60, duration=60, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    d0 = booking_date()
    d1 = (dt.date.fromisoformat(d0) + dt.timedelta(days=7)).isoformat()
    assert_status(publish(ada, d0, slot_minutes=60, reservation_duration_minutes=60,
        cancellation_cutoff_minutes=0, capacities={"t_1": 4, "t_2": 4, "t_3": 4}), 201)
    stay = assert_status(create(ada, d0, table_id="t_1", party=2), 201).json()
    move = assert_status(create(ada, d0, table_id="t_2", party=2), 201).json()
    tie = assert_status(create(ada, d1, table_id="t_2", party=2), 201).json()
    refs = [stay["reference"], move["reference"], tie["reference"]]
    before = {ref: ada.get(f"/reservations/{ref}").json() for ref in refs}
    histories = {ref: ada.get(f"/reservations/{ref}/history").json() for ref in refs}
    revision = rev_probe(ada, d0)

    key = new_key()
    first = assert_status(replan(ada, d0, "t_2", "19:00", "20:00", key=key), 201).json()
    assert assert_status(replan(ada, d0, "t_2", "19:00", "20:00", key=key), 200).json() == first
    items = {a["reference"]: a for a in first["assignments"]}
    assert [a["reference"] for a in first["assignments"]] == sorted([stay["reference"], move["reference"]])
    assert items[stay["reference"]] == {"reference": stay["reference"], "table_ids": ["t_1"], "changed": False}
    assert items[move["reference"]] == {"reference": move["reference"], "table_ids": ["t_3"], "changed": True}
    assert first["moved_count"] == 1 and first["unused_seats"] == 4

    second = assert_status(replan(ada, d1, "t_2", "19:00", "20:00"), 201).json()
    assert second["assignments"] == [{"reference": tie["reference"], "table_ids": ["t_1"], "changed": True}]
    assert second["moved_count"] == 1 and second["unused_seats"] == 2
    assert first["restaurant_revision"] == second["restaurant_revision"] == revision
    for ref in refs:
        assert ada.get(f"/reservations/{ref}").json() == before[ref]
        assert ada.get(f"/reservations/{ref}/history").json() == histories[ref]


def test_replan_authorization_interval_and_unknown_target_validation(reset, api, anon):
    reset(fixture(restaurants=[restaurant()]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    bob = api().authenticate(BOB["email"], BOB["password"])
    date = booking_date()
    body = {"table_id": "t_2", "from": instant(date, "19:00"), "to": instant(date, "20:00")}
    assert_error(anon.post("/restaurants/r_anker/replans", json=body, idempotency_key=new_key()),
                 401, "unauthenticated")
    assert_error(bob.post("/restaurants/r_anker/replans", json=body, idempotency_key=new_key()),
                 403, "forbidden")
    assert_error(ada.post("/restaurants/missing/replans", json=body, idempotency_key=new_key()),
                 404, "not_found")
    assert_error(ada.post("/restaurants/r_anker/replans", json={**body, "table_id": "t_missing"},
                          idempotency_key=new_key()), 404, "not_found")
    assert_error(ada.post("/restaurants/r_anker/replans/no-plan/apply", json={},
                          idempotency_key=new_key()), 404, "not_found")
    for invalid in ({**body, "from": local(date)},
                    {**body, "to": instant(date, "19:00")},
                    {**body, "from": instant(date, "20:00"), "to": instant(date, "19:00")}):
        response = ada.post("/restaurants/r_anker/replans", json=invalid, idempotency_key=new_key())
        assert_error(response, 422, "validation_failed")
        assert response.status_code < 500


def test_seventh_considered_booking_is_planned_or_cleanly_limited(reset, api):
    tables = [{"id": f"t_{i}", "label": str(i), "capacity": 2} for i in range(1, 7)]
    reset(fixture(restaurants=[restaurant(tables=tables, pairs=False, slot_minutes=30,
                                           duration=30, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    bookings = []
    for minutes in range(0, 210, 30):
        at = (dt.datetime.combine(dt.date.fromisoformat(date), dt.time(18))
              + dt.timedelta(minutes=minutes)).strftime("%H:%M")
        bookings.append(assert_status(create(ada, date, table_id="t_6", at=at, party=2), 201).json())
    before = [ada.get(f"/reservations/{b['reference']}").json() for b in bookings]
    response = replan(ada, date, "t_6", "18:00", "22:00")
    no_5xx([response])
    if response.status_code == 422:
        assert_error(response, 422, "planning_limit")
    else:
        accepted = assert_status(response, 201).json()
        assert sorted(a["reference"] for a in accepted["assignments"]) == sorted(
            b["reference"] for b in bookings)
    assert [ada.get(f"/reservations/{b['reference']}").json() for b in bookings] == before


def test_no_feasible_plan_leaves_confirmed_bookings_and_histories_unchanged(reset, api):
    tables = [{"id": "t_1", "label": "1", "capacity": 2},
              {"id": "t_2", "label": "2", "capacity": 2}]
    reset(fixture(restaurants=[restaurant(tables=tables, pairs=False, duration=60, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    a = assert_status(create(ada, date, table_id="t_1", party=2), 201).json()
    b = assert_status(create(ada, date, table_id="t_2", party=2), 201).json()
    before = [ada.get(f"/reservations/{ref}").json() for ref in (a["reference"], b["reference"])]
    assert_error(replan(ada, date, "t_2", "19:00", "20:00"), 409, "no_feasible_plan")
    assert [ada.get(f"/reservations/{ref}").json() for ref in (a["reference"], b["reference"])] == before
    assert all(len(ada.get(f"/reservations/{ref}/history").json()["entries"]) == 1
               for ref in (a["reference"], b["reference"]))


def test_apply_preserves_terms_history_series_and_closure_boundary(reset, api, anon):
    reset(fixture(restaurants=[restaurant(slot_minutes=60, duration=60, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    assert_status(publish(ada, date, slot_minutes=60, reservation_duration_minutes=60,
                          cancellation_cutoff_minutes=0), 201)
    anchor = assert_status(create(ada, date, table_id="t_2", at="19:00", party=4), 201).json()
    boundary = assert_status(create(ada, date, table_id="t_2", at="20:00", party=4), 201).json()
    made = assert_status(ada.post("/series", json={"anchor_reference": anchor["reference"],
        "count": 2, "interval_weeks": 1}, idempotency_key=new_key()), 201).json()
    terms, start = anchor["accepted_terms"], anchor["starts_at_local"]
    revision = rev_probe(ada, date)
    preview = assert_status(replan(ada, date, "t_2", "19:00", "20:00"), 201).json()
    assert preview["assignments"] == [{"reference": anchor["reference"],
        "table_ids": ["t_3"], "changed": True}]
    key = new_key()
    committed = assert_status(apply(ada, preview["plan_id"], key=key), 201).json()
    assert committed["restaurant_revision"] == revision + 1
    moved = committed["reservations"][0]
    assert moved["reference"] == anchor["reference"]
    assert moved["table_ids"] == ["t_3"] and moved["revision"] == 2
    assert moved["starts_at_local"] == start and moved["accepted_terms"] == terms
    assert ada.get(f"/reservations/{boundary['reference']}").json()["revision"] == 1
    hist = ada.get(f"/reservations/{anchor['reference']}/history").json()["entries"]
    assert [e["event"] for e in hist] == ["created", "reassigned"]
    assert hist[-1]["plan_id"] == preview["plan_id"]
    assert hist[-1]["changes"] == [{"field": "table_ids", "from": ["t_2"], "to": ["t_3"]}]
    current_series = ada.get(f"/series/{made['series_id']}").json()
    assert current_series["revision"] == 2
    assert [o["exception"] for o in current_series["occurrences"]] == [False, False]

    assert assert_status(apply(ada, preview["plan_id"], key=key), 200).json() == committed
    assert_error(apply(ada, preview["plan_id"]), 409, "plan_already_applied")
    slot = next(s for s in anon.get("/availability", params={"restaurant_id": "r_anker",
        "date": date, "party_size": 4, "explain": "true"}).json()["slots"]
        if s["starts_at_local"].endswith("19:00"))
    t2 = next(e for e in slot["explain"] if e["table_id"] == "t_2")
    assert t2["rules"][1]["holds"] is False and "t_2" not in slot["available_table_ids"]
    assert_error(create(ada, date, table_id="t_2", at="19:00", party=4),
                 409, "table_unavailable")

    # The booking beginning exactly at the closure end was not moved. Cancel it
    # to expose the closure's half-open end in the availability explanation.
    assert_status(ada.post(f"/reservations/{boundary['reference']}/cancel"), 200)
    exact_end = assert_status(create(ada, date, table_id="t_2", at="20:00", party=4), 201).json()
    assert_status(ada.post(f"/reservations/{exact_end['reference']}/cancel"), 200)
    end = next(s for s in anon.get("/availability", params={"restaurant_id": "r_anker",
        "date": date, "party_size": 4, "explain": "true"}).json()["slots"]
        if s["starts_at_local"].endswith("20:00"))
    t2_end = next(e for e in end["explain"] if e["table_id"] == "t_2")
    assert t2_end["rules"][1]["holds"] is True and "t_2" in end["available_table_ids"]


def test_stale_plan_after_intervening_write_has_no_partial_effect(reset, api):
    reset(fixture(restaurants=[restaurant(cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    booking = assert_status(create(ada, date, table_id="t_2", party=4), 201).json()
    preview = assert_status(replan(ada, date, "t_2", "19:00", "20:00"), 201).json()
    other = assert_status(create(ada, date, table_id="t_1", at="21:00", party=2), 201).json()
    assert_error(apply(ada, preview["plan_id"]), 409, "stale_plan")
    after = ada.get(f"/reservations/{booking['reference']}").json()
    assert after["table_ids"] == ["t_2"] and after["revision"] == 1
    assert len(ada.get(f"/reservations/{booking['reference']}/history").json()["entries"]) == 1
    assert ada.get(f"/reservations/{other['reference']}").json()["revision"] == 1
    slots = ada.get("/availability", params={"restaurant_id": "r_anker", "date": date,
                                               "party_size": 4}).json()["slots"]
    at_seven = next(s for s in slots if s["starts_at_local"].endswith("19:00"))
    assert "t_2" not in at_seven["available_table_ids"]
    assert "t_3" in at_seven["available_table_ids"]


def test_concurrent_apply_with_same_key_commits_once_and_has_no_partial_rows(reset, api):
    reset(fixture(restaurants=[restaurant(cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    booking = assert_status(create(ada, date, table_id="t_2", party=4), 201).json()
    preview = assert_status(replan(ada, date, "t_2", "19:00", "20:00"), 201).json()
    clients = [api(token=ada.token) for _ in range(6)]
    key = new_key()
    results = burst(lambda i: apply(clients[i], preview["plan_id"], key=key), 6)
    no_5xx(results)
    assert tally(results) == {200: 5, 201: 1}
    assert all(resp.json() == results[0].json() for resp in results)
    current = ada.get(f"/reservations/{booking['reference']}").json()
    assert current["table_ids"] == ["t_3"] and current["revision"] == 2
    events = ada.get(f"/reservations/{booking['reference']}/history").json()["entries"]
    assert [e["event"] for e in events] == ["created", "reassigned"]
    assert_error(apply(ada, preview["plan_id"]), 409, "plan_already_applied")


def test_stage2_single_pair_and_nontransitive_contract_survives(reset, api):
    reset(fixture())
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    single = assert_status(create(ada, date, table_id="t_3", at="19:00", party=4), 201).json()
    assert single["table_id"] == "t_3" and single["table_ids"] == ["t_3"]
    pair = assert_status(create(ada, date, table_ids=["t_2", "t_1"],
                                at="21:00", party=6), 201).json()
    assert pair["table_ids"] == ["t_1", "t_2"] and "table_id" not in pair
    assert_error(create(ada, date, table_ids=["t_1", "t_3"], at="19:00", party=8),
                 422, "combination_not_allowed")

def test_series_amend_validates_revision_skips_exceptions_and_is_noop_safe(reset, api, anon):
    reset(fixture(restaurants=[restaurant(cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    bob = api().authenticate(BOB["email"], BOB["password"])
    date = booking_date()
    anchor = assert_status(create(ada, date, party=4), 201).json()
    series = assert_status(ada.post("/series", json={"anchor_reference": anchor["reference"],
        "count": 4, "interval_weeks": 1}, idempotency_key=new_key()), 201).json()
    sid = series["series_id"]
    refs = [o["reference"] for o in series["occurrences"]]
    body = {"expected_revision": 1, "from_index": 0, "local_time": "20:00"}
    assert_error(anon.post(f"/series/{sid}/amend", json=body, idempotency_key=new_key()),
                 401, "unauthenticated")
    assert_error(bob.post(f"/series/{sid}/amend", json=body, idempotency_key=new_key()),
                 404, "not_found")
    assert_status(ada.patch(f"/reservations/{refs[1]}", json={
        "table_id": "t_3", "expected_revision": 1}), 200)
    assert_status(ada.post(f"/reservations/{refs[2]}/cancel"), 200)
    before = ada.get(f"/series/{sid}").json()
    assert before["revision"] == 3
    assert [o["exception"] for o in before["occurrences"]] == [False, True, False, False]
    assert before["occurrences"][2]["reservation"]["status"] == "cancelled"

    for invalid in (
        {"expected_revision": True, "from_index": 0, "local_time": "20:00"},
        {"expected_revision": 3, "from_index": True, "local_time": "20:00"},
        {"expected_revision": 3, "from_index": 4, "local_time": "20:00"},
        {"expected_revision": 3, "from_index": 0, "local_time": "9:00"},
        {"expected_revision": 3, "from_index": 0, "local_time": "24:00"},
    ):
        assert_error(ada.post(f"/series/{sid}/amend", json=invalid,
                              idempotency_key=new_key()), 422, "validation_failed")
    assert_error(ada.post(f"/series/{sid}/amend", json={
        "expected_revision": 2, "from_index": 0, "local_time": "17:00"},
        idempotency_key=new_key()), 409, "stale_revision")

    revision = rev_probe(ada, date)
    key = new_key()
    amended = assert_status(ada.post(f"/series/{sid}/amend", json={
        "expected_revision": 3, "from_index": 0, "local_time": "20:00"},
        idempotency_key=key), 201).json()
    assert amended["revision"] == 4
    assert [o["reference"] for o in amended["occurrences"]] == refs
    assert [o["reservation"]["starts_at_local"][-5:] for o in amended["occurrences"]] == [
        "20:00", "19:00", "19:00", "20:00"]
    assert [o["exception"] for o in amended["occurrences"]] == [False, True, False, False]
    assert amended["occurrences"][2]["reservation"]["status"] == "cancelled"
    for index in (0, 3):
        row = amended["occurrences"][index]["reservation"]
        assert row["revision"] == 2
        entries = ada.get(f"/reservations/{refs[index]}/history").json()["entries"]
        assert len(entries) == 2 and entries[-1]["revision"] == 2
        scheduled = (dt.date.fromisoformat(date) + dt.timedelta(days=index * 7)).isoformat()
        assert entries[-1]["changes"] == [{"field": "starts_at_local",
            "from": local(scheduled, "19:00"), "to": local(scheduled, "20:00")}]
    assert rev_probe(ada, date) == revision + 1

    no_op = assert_status(ada.post(f"/series/{sid}/amend", json={
        "expected_revision": 4, "from_index": 0, "local_time": "20:00"},
        idempotency_key=new_key()), 201).json()
    assert no_op["revision"] == 4
    assert rev_probe(ada, date) == revision + 1
    assert_status(ada.post(f"/reservations/{refs[3]}/cancel"), 200)
    after_cancel = rev_probe(ada, date)
    empty = assert_status(ada.post(f"/series/{sid}/amend", json={
        "expected_revision": 5, "from_index": 1, "local_time": "22:00"},
        idempotency_key=new_key()), 201).json()
    assert empty["revision"] == 5
    assert rev_probe(ada, date) == after_cancel


def test_series_amend_policy_and_closure_failures_are_atomic_and_ordered(reset, api):
    reset(fixture(restaurants=[restaurant(slot_minutes=30, duration=30, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date0 = booking_date()
    date1 = (dt.date.fromisoformat(date0) + dt.timedelta(days=7)).isoformat()
    date2 = (dt.date.fromisoformat(date0) + dt.timedelta(days=14)).isoformat()
    assert_status(publish(ada, date0, slot_minutes=30, reservation_duration_minutes=30,
                          cancellation_cutoff_minutes=0), 201)
    anchor = assert_status(create(ada, date0, party=4), 201).json()
    series = assert_status(ada.post("/series", json={"anchor_reference": anchor["reference"],
        "count": 3, "interval_weeks": 1}, idempotency_key=new_key()), 201).json()
    sid = series["series_id"]
    refs = [o["reference"] for o in series["occurrences"]]
    low = assert_status(publish(ada, date1, slot_minutes=30, reservation_duration_minutes=30,
        cancellation_cutoff_minutes=0, capacities={"t_1": 2, "t_2": 2, "t_3": 6}), 201).json()
    close = assert_status(replan(ada, date2, "t_2", "20:00", "20:30"), 201).json()
    assert close["assignments"] == []
    assert_status(apply(ada, close["plan_id"]), 201)
    before = ada.get(f"/series/{sid}").json()
    key = new_key()
    body = {"expected_revision": 1, "from_index": 0, "local_time": "20:00"}

    # Index 1's capacity error is a non-occupancy error and takes precedence over
    # index 2's closure conflict. No occurrence may commit on this failed request.
    assert_error(ada.post(f"/series/{sid}/amend", json=body, idempotency_key=key),
                 422, "party_exceeds_capacity")
    assert ada.get(f"/series/{sid}").json() == before
    assert all(len(ada.get(f"/reservations/{ref}/history").json()["entries"]) == 1
               for ref in refs)

    raised = assert_status(publish(ada, date1, slot_minutes=30,
        reservation_duration_minutes=30, cancellation_cutoff_minutes=0,
        capacities={"t_1": 2, "t_2": 4, "t_3": 6}), 201).json()
    assert raised["policy_version"] > low["policy_version"]
    assert_error(ada.post(f"/series/{sid}/amend", json=body, idempotency_key=key),
                 409, "table_unavailable")
    assert ada.get(f"/series/{sid}").json() == before
    assert all(len(ada.get(f"/reservations/{ref}/history").json()["entries"]) == 1
               for ref in refs)

    revision = rev_probe(ada, date0)
    successful = assert_status(ada.post(f"/series/{sid}/amend", json={
        "expected_revision": 1, "from_index": 0, "local_time": "21:00"},
        idempotency_key=key), 201).json()
    assert successful["revision"] == 2
    assert [o["reservation"]["revision"] for o in successful["occurrences"]] == [2, 2, 2]
    assert [o["reservation"]["starts_at_local"][-5:] for o in successful["occurrences"]] == [
        "21:00", "21:00", "21:00"]
    assert [o["reservation"]["accepted_terms"]["policy_version"] for o in successful["occurrences"]] == [
        1, raised["policy_version"], raised["policy_version"]]
    assert [o["exception"] for o in successful["occurrences"]] == [False, False, False]
    assert rev_probe(ada, date0) == revision + 1

def test_series_amend_spring_DST_gap_rolls_back_and_failed_key_is_reusable(reset, api):
    reset(fixture(restaurants=[restaurant(slot_minutes=30, duration=30, cutoff=0,
                                          opening_hours=all_week("01:00", "05:00"))]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    gap = spring_gap_sunday()
    date = (gap - dt.timedelta(days=7)).isoformat()
    anchor = assert_status(create(ada, date, table_id="t_2", at="01:30", party=4), 201).json()
    series = assert_status(ada.post("/series", json={"anchor_reference": anchor["reference"],
        "count": 2, "interval_weeks": 1}, idempotency_key=new_key()), 201).json()
    sid = series["series_id"]
    refs = [o["reference"] for o in series["occurrences"]]
    before = ada.get(f"/series/{sid}").json()
    key = new_key()
    assert_error(ada.post(f"/series/{sid}/amend", json={"expected_revision": 1,
        "from_index": 0, "local_time": "02:30"}, idempotency_key=key), 422, "invalid_local_time")
    assert ada.get(f"/series/{sid}").json() == before
    assert all(len(ada.get(f"/reservations/{ref}/history").json()["entries"]) == 1
               for ref in refs)
    changed = assert_status(ada.post(f"/series/{sid}/amend", json={
        "expected_revision": 1, "from_index": 0, "local_time": "03:30"},
        idempotency_key=key), 201).json()
    assert changed["revision"] == 2
    assert [o["reservation"]["starts_at_local"][-5:] for o in changed["occurrences"]] == ["03:30", "03:30"]
    assert [o["reference"] for o in changed["occurrences"]] == refs


def test_series_amend_fall_DST_ambiguity_uses_first_offset(reset, api):
    reset(fixture(restaurants=[restaurant(slot_minutes=30, duration=30, cutoff=0,
                                          opening_hours=all_week("02:00", "05:00"))]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    fallback = fall_back_sunday()
    date = (fallback - dt.timedelta(days=7)).isoformat()
    anchor = assert_status(create(ada, date, table_id="t_2", at="02:00", party=4), 201).json()
    series = assert_status(ada.post("/series", json={"anchor_reference": anchor["reference"],
        "count": 2, "interval_weeks": 1}, idempotency_key=new_key()), 201).json()
    changed = assert_status(ada.post(f"/series/{series['series_id']}/amend", json={
        "expected_revision": 1, "from_index": 0, "local_time": "02:30"},
        idempotency_key=new_key()), 201).json()
    occurrence = changed["occurrences"][1]["reservation"]
    assert occurrence["starts_at_local"] == f"{fallback.isoformat()}T02:30"
    assert dt.datetime.fromisoformat(occurrence["starts_at"]).utcoffset() == dt.timedelta(hours=2)


def test_concurrent_series_amendments_from_one_revision_only_one_changes(reset, api):
    reset(fixture(restaurants=[restaurant(cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    anchor = assert_status(create(ada, date, party=4), 201).json()
    series = assert_status(ada.post("/series", json={"anchor_reference": anchor["reference"],
        "count": 2, "interval_weeks": 1}, idempotency_key=new_key()), 201).json()
    clients = [api(token=ada.token) for _ in range(2)]
    body = {"expected_revision": 1, "from_index": 0, "local_time": "20:00"}
    keys = [new_key(), new_key()]
    responses = burst(lambda i: clients[i].post(f"/series/{series['series_id']}/amend",
        json=body, idempotency_key=keys[i]), 2)
    no_5xx(responses)
    assert tally(responses) == {201: 1, 409: 1}
    loser = next(r for r in responses if r.status_code == 409)
    assert_error(loser, 409, "stale_revision")
    current = ada.get(f"/series/{series['series_id']}").json()
    assert current["revision"] == 2
    assert [o["reservation"]["revision"] for o in current["occurrences"]] == [2, 2]
    assert all(len(ada.get(f"/reservations/{o['reference']}/history").json()["entries"]) == 2
               for o in current["occurrences"])

def test_stage3_rich_import_preserves_history_series_policy_token_and_replays(
        world, previous_api, api):
    source = fixture(restaurants=[restaurant()])
    assert_status(previous_api.post("/_test/reset", json=source), 204)
    old = previous_api.authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    assert_status(publish(old, date, slot_minutes=30, reservation_duration_minutes=30,
                          cancellation_cutoff_minutes=0), 201)
    create_key = new_key()
    body = booking_body(date, table_id="t_2", party=4)
    original = assert_status(old.post("/reservations", json=body,
                                      idempotency_key=create_key), 201).json()
    assert_status(old.patch(f"/reservations/{original['reference']}", json={
        "table_id": "t_3", "expected_revision": 1}), 200)
    series_body = {"anchor_reference": original["reference"], "count": 2, "interval_weeks": 1}
    series_key = new_key()
    original_series = assert_status(old.post("/series", json=series_body,
        idempotency_key=series_key), 201).json()
    cancelled_ref = original_series["occurrences"][1]["reference"]
    assert_status(old.post(f"/reservations/{cancelled_ref}/cancel"), 200)
    exported = assert_status(old.get("/_test/export"), 200).json()

    restored = api(token=old.token)
    before = assert_status(restored.get("/_test/export"), 200).json()
    invalid = {**exported, "state": {**exported["state"], "series": []}}
    assert_error(restored.post("/_test/import", json=invalid, token=None),
                 422, "validation_failed")
    assert restored.get("/_test/export").json() == before
    assert_status(restored.post("/_test/import", json=exported, token=None), 204)
    current = assert_status(restored.get(f"/reservations/{original['reference']}"), 200).json()
    assert current["revision"] == 2 and current["table_ids"] == ["t_3"]
    assert current["accepted_terms"]["policy_version"] == 1
    history = restored.get(f"/reservations/{original['reference']}/history").json()["entries"]
    assert [e["event"] for e in history] == ["created", "changed"]
    assert history[0]["accepted_terms"]["policy_version"] == 1
    assert history[1]["revision"] == 2
    assert restored.get(f"/reservations/{original['reference']}/decision").json()["revision"] == 2
    assert assert_status(restored.post("/reservations", json=body,
        idempotency_key=create_key), 200).json() == original
    current_series = restored.get(f"/series/{original_series['series_id']}").json()
    assert current_series["revision"] == 2
    assert current_series["occurrences"][1]["reservation"]["status"] == "cancelled"
    assert assert_status(restored.post("/series", json=series_body,
        idempotency_key=series_key), 200).json() == original_series


def test_existing_stage2_browser_lookup_and_grid_show_applied_seating_at_375px(
        reset, api, page):
    reset(fixture(restaurants=[restaurant(slot_minutes=60, duration=60, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    assert_status(publish(ada, date, slot_minutes=60, reservation_duration_minutes=60,
                          cancellation_cutoff_minutes=0), 201)
    booking = assert_status(create(ada, date, table_id="t_2", at="19:00", party=4), 201).json()
    preview = assert_status(replan(ada, date, "t_2", "19:00", "20:00"), 201).json()
    assert_status(apply(ada, preview["plan_id"]), 201)

    sel = lambda name: f"[data-testid='{name}']"
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto("/login")
    page.fill(sel("login-email"), ADA["email"])
    page.fill(sel("login-password"), ADA["password"])
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("current-user"))
    page.goto("/")
    page.select_option(sel("restaurant-select"), "r_anker")
    page.fill(sel("date-input"), date)
    page.fill(sel("party-size-input"), "4")
    page.click(sel("search-button"))
    page.wait_for_selector(sel("availability-grid"))
    assert page.get_attribute(sel("slot-t_2-19:00"), "data-available") == "false"
    assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
    page.goto("/lookup")
    page.fill(sel("lookup-reference-input"), booking["reference"])
    page.click(sel("lookup-submit"))
    page.wait_for_selector(sel("reservation-detail"))
    assert page.text_content(sel("reservation-tables")).strip() == "3"
    assert page.text_content(sel("reservation-status")).strip() == "confirmed"


def test_booking_confirmation_refreshes_after_concurrent_seating_replan(reset, api, page):
    reset(fixture(restaurants=[restaurant(slot_minutes=60, duration=60, cutoff=0)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date()
    assert_status(publish(ada, date, slot_minutes=60, reservation_duration_minutes=60,
                          cancellation_cutoff_minutes=0), 201)

    sel = lambda name: f"[data-testid='{name}']"
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto("/login")
    page.fill(sel("login-email"), ADA["email"])
    page.fill(sel("login-password"), ADA["password"])
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("current-user"))
    page.goto("/")
    page.select_option(sel("restaurant-select"), "r_anker")
    page.fill(sel("date-input"), date)
    page.fill(sel("party-size-input"), "4")
    page.click(sel("search-button"))
    page.wait_for_selector(sel("slot-t_2-19:00"))
    page.click(sel("slot-t_2-19:00"))
    page.fill(sel("booking-party-size"), "4")

    def replan_before_refresh(route):
        if route.request.method != "GET":
            route.continue_()
            return
        reference = route.request.url.split("?", 1)[0].rsplit("/", 1)[-1]
        preview = assert_status(replan(ada, date, "t_2", "19:00", "20:00"), 201).json()
        assert preview["assignments"] == [{
            "reference": reference, "table_ids": ["t_3"], "changed": True}]
        assert_status(apply(ada, preview["plan_id"]), 201)
        route.continue_()

    page.route("**/reservations/*", replan_before_refresh)
    booking_keys = []
    page.on("request", lambda request: booking_keys.append(
        request.headers.get("idempotency-key"))
        if request.method == "POST" and request.url.endswith("/reservations") else None)
    page.click(sel("booking-submit"))
    page.wait_for_selector(sel("confirmation-tables"))
    assert page.text_content(sel("confirmation-tables")).strip() == "Table 3"
    assert len(booking_keys) == 1 and booking_keys[0]

    # The POST receipt remains the original booking result; only the display refreshes.
    original = assert_status(ada.post("/reservations", json=booking_body(
        date, table_id="t_2", party=4), idempotency_key=booking_keys[0]), 200).json()
    assert original["table_ids"] == ["t_2"]
    assert ada.get(f"/reservations/{original['reference']}").json()["table_ids"] == ["t_3"]


def test_planning_may_reject_inputs_over_table_or_pair_bounds_without_5xx(reset, api):
    date = booking_date()
    seven_tables = [{"id": f"t_{i}", "label": str(i), "capacity": 2} for i in range(1, 8)]
    six_tables = seven_tables[:6]
    five_pairs = [[f"t_{i}", f"t_{i + 1}"] for i in range(1, 6)]
    candidates = [restaurant(tables=seven_tables, pairs=False),
                  {**restaurant(tables=six_tables, pairs=False), "combinable": five_pairs}]
    for candidate in candidates:
        reset(fixture(restaurants=[candidate]))
        ada = api().authenticate(ADA["email"], ADA["password"])
        response = replan(ada, date, "t_2", "19:00", "20:00")
        no_5xx([response])
        if response.status_code == 422:
            assert_error(response, 422, "planning_limit")
        else:
            assert_status(response, 201)
            assert response.json()["assignments"] == []


def test_replan_keeps_nonconsidered_fixed_booking_and_ignores_diner_cutoff(reset, api):
    tables = [{"id": "t_1", "label": "1", "capacity": 2},
              {"id": "t_2", "label": "2", "capacity": 4},
              {"id": "t_3", "label": "3", "capacity": 6},
              {"id": "t_4", "label": "4", "capacity": 4}]
    reset(fixture(restaurants=[restaurant(tables=tables, slot_minutes=30,
        duration=90, cutoff=10080)]))
    ada = api().authenticate(ADA["email"], ADA["password"])
    date = booking_date(lead=6)
    assert_status(publish(ada, date, slot_minutes=30, reservation_duration_minutes=90,
        cancellation_cutoff_minutes=10080,
        capacities={"t_1": 2, "t_2": 4, "t_3": 6, "t_4": 4}), 201)
    affected = assert_status(create(ada, date, table_id="t_2", at="19:00", party=4), 201).json()
    fixed = assert_status(create(ada, date, table_id="t_3", at="20:00", party=4), 201).json()
    assert affected["accepted_terms"]["cancellation_cutoff_minutes"] == 10080
    before_fixed = ada.get(f"/reservations/{fixed['reference']}").json()
    before_fixed_history = ada.get(f"/reservations/{fixed['reference']}/history").json()

    preview = assert_status(replan(ada, date, "t_2", "19:00", "19:30"), 201).json()
    assert preview["assignments"] == [{"reference": affected["reference"],
        "table_ids": ["t_4"], "changed": True}]
    moved = assert_status(apply(ada, preview["plan_id"]), 201).json()["reservations"][0]
    assert moved["table_ids"] == ["t_4"]
    assert moved["accepted_terms"] == affected["accepted_terms"]
    assert ada.get(f"/reservations/{fixed['reference']}").json() == before_fixed
    assert ada.get(f"/reservations/{fixed['reference']}/history").json() == before_fixed_history
