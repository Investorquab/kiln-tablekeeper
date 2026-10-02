"""Independent Stage 2 black-box acceptance regressions.

Run from dark-factory-wearedevs with harness dependencies installed and both services
running: Stage 2 at 127.0.0.1:8080 and its Stage 1 export source at 127.0.0.1:8081.
See the handoff for the exact pytest invocation. This suite imports only harness fixtures
and observes the API/browser from the outside.
"""
from __future__ import annotations

import datetime as dt
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from harness.concurrent import burst, no_5xx, tally
from harness.http import assert_error, new_key

pytestmark = pytest.mark.stage(2)

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ADA = {"id": "u_ada", "email": "ada@example.com",
       "password": "correct horse", "display_name": "Ada"}
BOB = {"id": "u_bob", "email": "bob@example.com",
       "password": "correct horse", "display_name": "Bob"}


def local_date(days=7):
    today = dt.datetime.now(ZoneInfo("Europe/Berlin")).date()
    return (today + dt.timedelta(days=days)).isoformat()


def fixture(*, combinations=True, users=None, rid="r_anker"):
    restaurant = {
        "id": rid, "name": "Zum Anker", "timezone": "Europe/Berlin",
        "slot_minutes": 30, "reservation_duration_minutes": 90,
        "cancellation_cutoff_minutes": 120,
        "opening_hours": [
            {"weekday": day, "opens": "18:00", "closes": "23:00"}
            for day in WEEKDAYS
        ],
        "tables": [
            {"id": "t_1", "label": "1", "capacity": 2},
            {"id": "t_2", "label": "2", "capacity": 4},
            {"id": "t_3", "label": "3", "capacity": 6},
        ],
    }
    if combinations:
        restaurant["combinable"] = [["t_1", "t_2"], ["t_2", "t_3"]]
    return {
        "users": [ADA, BOB] if users is None else users,
        "restaurants": [restaurant],
        "reservations": [],
    }


@pytest.fixture
def world(reset, api):
    state = fixture()
    reset(state)
    ada = api().authenticate(ADA["email"], ADA["password"])
    bob = api().authenticate(BOB["email"], BOB["password"])
    restaurant = state["restaurants"][0]
    return SimpleNamespace(
        fixture=state, restaurant=restaurant, rid=restaurant["id"],
        date=local_date(), ada=ada, bob=bob,
    )


def slot(client, rid, date, party_size):
    response = client.get("/availability", params={
        "restaurant_id": rid, "date": date, "party_size": party_size,
    })
    assert response.status_code == 200, response.text
    found = next(s for s in response.json()["slots"]
                 if s["starts_at_local"].endswith("19:00"))
    return found


def booking_body(date, *, table_id=None, table_ids=None, at="19:00", party=4):
    body = {"restaurant_id": "r_anker", "starts_at_local": f"{date}T{at}",
            "party_size": party}
    if table_ids is not None:
        body["table_ids"] = table_ids
    else:
        body["table_id"] = table_id or "t_2"
    return body


def create(client, date, *, key=None, **kwargs):
    return client.post(
        "/reservations", json=booking_body(date, **kwargs),
        idempotency_key=key or new_key(),
    )


def get_reservation(client, reference):
    response = client.get(f"/reservations/{reference}")
    assert response.status_code == 200, response.text
    return response.json()


def sel(tid, name):
    return tid(name)


def sign_in(page, tid, *, email=None):
    page.goto("/login")
    page.fill(sel(tid, "login-email"), email or ADA["email"])
    page.fill(sel(tid, "login-password"), ADA["password"])
    page.click(sel(tid, "login-submit"))
    page.wait_for_selector(sel(tid, "current-user"))


def search_controls(page, tid, date, party_size=4):
    page.select_option(sel(tid, "restaurant-select"), "r_anker")
    page.fill(sel(tid, "date-input"), date)
    page.fill(sel(tid, "party-size-input"), str(party_size))
    page.click(sel(tid, "search-button"))


def test_direct_routes_auth_signup_and_logout_contract(page, tid, world):
    for route, anchor in (("/", "search-button"), ("/signup", "signup-submit"),
                        ("/login", "login-submit"), ("/lookup", "lookup-submit")):
        page.goto(route)
        page.wait_for_selector(sel(tid, anchor))
    page.goto("/signup")
    page.fill(sel(tid, "signup-email"), "stage2-diner@example.test")
    page.fill(sel(tid, "signup-password"), "correct horse")
    page.fill(sel(tid, "signup-display-name"), "New Diner")
    page.click(sel(tid, "signup-submit"))
    page.wait_for_selector(sel(tid, "current-user"))
    assert "New Diner" in page.text_content(sel(tid, "current-user"))
    for route in ("/", "/signup", "/login", "/lookup"):
        page.goto(route)
        page.wait_for_selector(sel(tid, "current-user"))
        assert "New Diner" in page.text_content(sel(tid, "current-user"))
    page.click(sel(tid, "logout-button"))
    page.wait_for_selector(sel(tid, "current-user"), state="detached")
    page.goto("/login")
    page.fill(sel(tid, "login-email"), "stage2-diner@example.test")
    page.fill(sel(tid, "login-password"), "wrong password")
    page.click(sel(tid, "login-submit"))
    page.wait_for_selector(sel(tid, "auth-error"))
    assert page.text_content(sel(tid, "auth-error")).strip()


def test_stage1_single_table_contract_and_half_open_intervals_survive_stage2(world):
    first_key = new_key()
    first = create(world.ada, world.date, key=first_key,
                   table_id="t_2", at="19:00", party=4)
    assert first.status_code == 201, first.text
    receipt = first.json()
    assert receipt["table_id"] == "t_2"
    assert receipt["table_ids"] == ["t_2"]

    replay = create(world.ada, world.date, key=first_key,
                    table_id="t_2", at="19:00", party=4)
    assert replay.status_code == 200 and replay.json() == receipt

    # Stage 1's [start, start + 90m) contract still permits adjacency.
    adjacent = create(world.ada, world.date, table_id="t_2",
                      at="20:30", party=4)
    assert adjacent.status_code == 201, adjacent.text
    cancelled = world.ada.post(f"/reservations/{receipt['reference']}/cancel")
    assert cancelled.status_code == 200
    assert get_reservation(world.ada, receipt["reference"])["status"] == "cancelled"
    restored_slot = slot(world.ada, world.rid, world.date, 4)
    assert "t_2" in restored_slot["available_table_ids"]


def test_declared_pairs_keep_order_and_are_not_transitive_or_overstated(world):
    options = slot(world.ada, world.rid, world.date, 6)["available_options"]
    assert options == [
        {"table_ids": ["t_3"], "capacity": 6},
        {"table_ids": ["t_1", "t_2"], "capacity": 6},
        {"table_ids": ["t_2", "t_3"], "capacity": 10},
    ]
    assert slot(world.ada, world.rid, world.date, 6)["available_table_ids"] == ["t_3"]
    assert all(option["table_ids"] != ["t_1", "t_3"] for option in options)

    not_declared = create(world.ada, world.date, table_ids=["t_1", "t_3"], party=4)
    assert_error(not_declared, 422, "combination_not_allowed")
    too_many = create(world.ada, world.date,
                      table_ids=["t_1", "t_2", "t_3"], party=4)
    assert_error(too_many, 422, "combination_not_allowed")
    duplicate = create(world.ada, world.date, table_ids=["t_1", "t_1"], party=2)
    assert_error(duplicate, 422, "validation_failed")
    both_fields = booking_body(world.date, table_id="t_2", party=4)
    both_fields["table_ids"] = ["t_2"]
    rejected_both = world.ada.post("/reservations", json=both_fields,
                                  idempotency_key=new_key())
    assert_error(rejected_both, 422, "validation_failed")
    over_capacity = create(world.ada, world.date,
                           table_ids=["t_1", "t_2"], party=7)
    assert_error(over_capacity, 422, "party_exceeds_capacity")


def test_combined_occupancy_blocks_both_members_and_cancel_releases_both(world):
    created = create(world.ada, world.date, table_ids=["t_1", "t_2"],
                     party=6, at="19:00")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["table_ids"] == ["t_1", "t_2"]
    assert "table_id" not in body

    overlapping = slot(world.ada, world.rid, world.date, 2)
    assert "t_1" not in overlapping["available_table_ids"]
    assert "t_2" not in overlapping["available_table_ids"]
    assert overlapping["available_options"] == [
        {"table_ids": ["t_3"], "capacity": 6},
    ]

    # The first interval ends at 20:30; the slot starting then is adjacent.
    adjacent = world.ada.get("/availability", params={
        "restaurant_id": world.rid, "date": world.date, "party_size": 2,
    }).json()["slots"]
    at_2030 = next(s for s in adjacent if s["starts_at_local"].endswith("20:30"))
    assert ["t_1", "t_2"] in [o["table_ids"] for o in at_2030["available_options"]]

    cancelled = world.ada.post(f"/reservations/{body['reference']}/cancel")
    assert cancelled.status_code == 200
    freed = slot(world.ada, world.rid, world.date, 2)
    assert freed["available_table_ids"] == ["t_1", "t_2", "t_3"]
    assert ["t_1", "t_2"] in [o["table_ids"] for o in freed["available_options"]]


def test_overlapping_combinations_racing_for_shared_table_have_one_winner(world):
    clients = [world.ada, world.bob]
    pair_sets = [["t_1", "t_2"], ["t_2", "t_3"]]
    results = burst(lambda i: create(clients[i], world.date,
                                 table_ids=pair_sets[i], at="19:00", party=4),
                    len(clients))
    no_5xx(results)
    assert tally(results) == {201: 1, 409: 1}
    loser = next(resp for resp in results if resp.status_code == 409)
    assert_error(loser, 409, "table_unavailable")
    confirmed = []
    for client in clients:
        confirmed.extend(r for r in client.get("/reservations").json()["reservations"]
                         if r["status"] == "confirmed")
    assert len(confirmed) == 1
    remaining = slot(world.ada, world.rid, world.date, 2)["available_options"]
    assert all("t_2" not in option["table_ids"] for option in remaining)


def test_combined_move_failure_is_atomic_then_success_and_cancellation_frees_pair(world):
    first = create(world.ada, world.date, table_id="t_1", at="18:00", party=2)
    second = create(world.ada, world.date, table_id="t_3", at="21:00", party=4)
    assert first.status_code == second.status_code == 201
    refs = [first.json()["reference"], second.json()["reference"]]
    before = [get_reservation(world.ada, ref) for ref in refs]
    key = new_key()

    failed = world.ada.post("/reservation-moves", json={"moves": [
        {"reference": refs[0], "table_ids": ["t_1", "t_2"]},
        {"reference": refs[1], "party_size": 0},
    ]}, idempotency_key=key)
    assert_error(failed, 422, "validation_failed")
    assert [get_reservation(world.ada, ref) for ref in refs] == before
    assert "t_2" in slot(world.ada, world.rid, world.date, 2)["available_table_ids"]

    moved = world.ada.post("/reservation-moves", json={"moves": [
        {"reference": refs[0], "table_ids": ["t_1", "t_2"]},
        {"reference": refs[1]},
    ]}, idempotency_key=key)
    assert moved.status_code == 201, moved.text
    assert [r["reference"] for r in moved.json()["reservations"]] == refs
    after = [get_reservation(world.ada, ref) for ref in refs]
    assert after[0]["table_ids"] == ["t_1", "t_2"]
    assert after[0]["reservation_id"] == before[0]["reservation_id"]
    assert after[1] == before[1]

    cancelled = world.ada.post(f"/reservations/{refs[0]}/cancel")
    assert cancelled.status_code == 200
    free = slot(world.ada, world.rid, world.date, 2)
    assert free["available_table_ids"] == ["t_1", "t_2", "t_3"]


def test_search_b_results_survive_a_late_response_from_search_a(page, tid, world):
    """A starts first (party 6); B completes first (party 2) and remains displayed."""
    page.goto("/")
    page.wait_for_selector(sel(tid, "restaurant-select"))
    held = []
    first_url = {}

    def defer_party_six(route):
        query = parse_qs(urlsplit(route.request.url).query)
        if query.get("party_size") == ["6"] and not held:
            held.append(route)
            first_url["url"] = route.request.url
        else:
            route.continue_()

    page.route("**/availability*", defer_party_six)
    with page.expect_request(lambda req: urlsplit(req.url).path == "/availability"
                             and parse_qs(urlsplit(req.url).query).get("party_size") == ["6"]):
        search_controls(page, tid, world.date, party_size=6)
    assert held, "search A was not held at the availability boundary"

    with page.expect_response(lambda resp: urlsplit(resp.url).path == "/availability"
                              and parse_qs(urlsplit(resp.url).query).get("party_size") == ["2"]):
        search_controls(page, tid, world.date, party_size=2)
    assert page.get_attribute(sel(tid, "slot-t_1-19:00"), "data-available") == "true"

    with page.expect_response(lambda resp: urlsplit(resp.url).path == "/availability"
                              and parse_qs(urlsplit(resp.url).query).get("party_size") == ["6"]):
        held[0].continue_()
    assert page.get_attribute(sel(tid, "slot-t_1-19:00"), "data-available") == "true", \
        "the late A response must not replace B's displayed results"


def test_table_taken_after_form_open_preserves_selection_and_refreshes_grid(page, tid, world):
    sign_in(page, tid)
    search_controls(page, tid, world.date, party_size=4)
    page.click(sel(tid, "slot-t_2-19:00"))
    page.wait_for_selector(sel(tid, "booking-form"))
    summary_before = page.text_content(sel(tid, "booking-summary"))
    party_before = page.input_value(sel(tid, "booking-party-size"))

    taken = create(world.bob, world.date, table_id="t_2", party=4)
    assert taken.status_code == 201, taken.text

    with page.expect_response(lambda resp: urlsplit(resp.url).path == "/availability"):
        page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "booking-error"))
    assert page.query_selector(sel(tid, "confirmation")) is None
    assert page.query_selector(sel(tid, "booking-form")) is not None
    assert page.text_content(sel(tid, "booking-summary")) == summary_before
    assert page.input_value(sel(tid, "booking-party-size")) == party_before
    assert page.get_attribute(sel(tid, "slot-t_2-19:00"), "data-available") == "false"

    # The diner can change the choice and submit a new request using the refreshed grid.
    page.click(sel(tid, "slot-t_3-19:00"))
    assert "3" in page.text_content(sel(tid, "booking-summary"))
    page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "confirmation"))


def test_lost_create_response_is_uncertain_and_retry_reuses_body_and_key(page, tid, world):
    sign_in(page, tid)
    search_controls(page, tid, world.date, party_size=4)
    page.click(sel(tid, "slot-t_2-19:00"))
    page.wait_for_selector(sel(tid, "booking-form"))
    attempts = []

    def lose_first_response(route):
        req = route.request
        if req.method == "POST":
            attempt = {
                "body": req.post_data_json,
                "key": req.headers.get("idempotency-key"),
            }
            attempts.append(attempt)
            if len(attempts) == 1:
                committed = route.fetch()
                attempt["status"] = committed.status
                attempt["receipt"] = committed.json()
                route.abort("failed")
                return
        route.continue_()

    page.route("**/reservations", lose_first_response)
    page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "booking-uncertain"))
    assert page.text_content(sel(tid, "booking-uncertain")).strip()
    assert page.query_selector(sel(tid, "booking-error")) is None
    assert page.query_selector(sel(tid, "confirmation")) is None
    assert attempts[0]["status"] == 201

    with page.expect_response(lambda resp: urlsplit(resp.url).path == "/reservations"
                              and resp.request.method == "POST"):
        page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "confirmation"))
    assert len(attempts) == 2
    assert attempts[1]["body"] == attempts[0]["body"]
    assert attempts[1]["key"] == attempts[0]["key"] and attempts[0]["key"]
    assert page.query_selector(sel(tid, "booking-uncertain")) is None
    assert page.query_selector(sel(tid, "booking-error")) is None
    assert page.text_content(sel(tid, "confirmation-reference")).strip() == \
        attempts[0]["receipt"]["reference"]
    confirmed = [r for r in world.ada.get("/reservations").json()["reservations"]
                 if r["status"] == "confirmed"]
    assert len(confirmed) == 1


def test_stage1_export_import_keeps_open_browser_token_reference_and_pending_receipt(
        page, tid, world, previous_api, api):
    """Import occurs while the page/form stay alive; no reload repairs browser state."""
    previous_state = fixture(combinations=False)
    assert previous_api.post("/_test/reset", json=previous_state).status_code == 204
    legacy = previous_api.authenticate(ADA["email"], ADA["password"])
    old_booking = legacy.post("/reservations", json=booking_body(
        world.date, table_id="t_1", at="18:00", party=2),
        idempotency_key=new_key())
    assert old_booking.status_code == 201, old_booking.text

    # The page is served by Stage 2, but its pre-upgrade session and first booking request
    # use Stage 1. The request commits there and its response is dropped.
    def use_legacy_login(route):
        path = urlsplit(route.request.url)
        route.continue_(url=previous_api.base_url + path.path +
                        (("?" + path.query) if path.query else ""))

    page.route("**/auth/login", use_legacy_login)
    page.goto("/login")
    page.fill(sel(tid, "login-email"), ADA["email"])
    page.fill(sel(tid, "login-password"), ADA["password"])
    page.click(sel(tid, "login-submit"))
    page.wait_for_selector(sel(tid, "current-user"))

    page.route("**/reservations", lambda route: route.continue_())
    first_attempt = []

    def commit_on_legacy_then_drop(route):
        if route.request.method == "POST":
            req = route.request
            response = route.fetch(url=previous_api.base_url + urlsplit(req.url).path)
            first_attempt.append({
                "body": req.post_data_json,
                "key": req.headers.get("idempotency-key"),
                "status": response.status,
                "receipt": response.json(),
            })
            route.abort("failed")
        else:
            route.continue_()

    page.unroute("**/reservations")
    page.route("**/reservations", commit_on_legacy_then_drop)
    search_controls(page, tid, world.date, party_size=4)
    page.click(sel(tid, "slot-t_2-19:00"))
    page.wait_for_selector(sel(tid, "booking-form"))
    page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "booking-uncertain"))
    assert first_attempt and first_attempt[0]["status"] == 201, \
        "single-table form submission must still be accepted by the Stage 1 API"

    export = previous_api.get("/_test/export")
    assert export.status_code == 200
    imported = api().post("/_test/import", json=export.json(), token=None)
    assert imported.status_code == 204

    # Upgrade completed between requests. Keep the current page, token and pending form.
    page.unroute("**/reservations", commit_on_legacy_then_drop)
    assert page.query_selector(sel(tid, "booking-error")) is None
    assert page.query_selector(sel(tid, "confirmation")) is None
    retry_attempts = []
    def capture_retry(route):
        req = route.request
        if req.method == "POST":
            retry_attempts.append({
                "body": req.post_data_json,
                "key": req.headers.get("idempotency-key"),
            })
        route.continue_()
    page.route("**/reservations", capture_retry)
    with page.expect_response(lambda resp: urlsplit(resp.url).path == "/reservations"
                              and resp.request.method == "POST"):
        page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "confirmation"))
    assert page.text_content(sel(tid, "confirmation-reference")).strip() == \
        first_attempt[0]["receipt"]["reference"]
    assert len(retry_attempts) == 1
    assert retry_attempts[0]["body"] == first_attempt[0]["body"]
    assert retry_attempts[0]["key"] == first_attempt[0]["key"]
    assert page.query_selector(sel(tid, "booking-uncertain")) is None
    assert page.query_selector(sel(tid, "auth-error")) is None

    # The same pre-upgrade token can still use a retained Stage 1 reference in lookup.
    page.goto("/lookup")
    page.fill(sel(tid, "lookup-reference-input"), old_booking.json()["reference"])
    page.click(sel(tid, "lookup-submit"))
    page.wait_for_selector(sel(tid, "reservation-detail"))
    assert page.text_content(sel(tid, "reservation-status")).strip() == "confirmed"


def test_combination_cells_name_both_tables_and_single_cells_remain_compatible(
        page, tid, world):
    sign_in(page, tid)
    page.goto("/")
    page.wait_for_selector(sel(tid, "restaurant-select"))
    search_controls(page, tid, world.date, party_size=6)
    for name in ("slot-t_3-19:00", "slot-t_1+t_2-19:00", "slot-t_2+t_3-19:00"):
        assert page.query_selector(sel(tid, name)) is not None, f"missing {name}"
    assert page.query_selector(sel(tid, "slot-t_1+t_3-19:00")) is None

    page.click(sel(tid, "slot-t_1+t_2-19:00"))
    page.wait_for_selector(sel(tid, "booking-form"))
    summary = page.text_content(sel(tid, "booking-summary"))
    assert "1" in summary and "2" in summary and "19:00" in summary
    page.click(sel(tid, "booking-submit"))
    page.wait_for_selector(sel(tid, "confirmation"))
    selected = page.text_content(sel(tid, "confirmation-tables"))
    assert "1" in selected and "2" in selected

    reference = page.text_content(sel(tid, "confirmation-reference")).strip()
    page.goto("/lookup")
    page.fill(sel(tid, "lookup-reference-input"), reference)
    page.click(sel(tid, "lookup-submit"))
    page.wait_for_selector(sel(tid, "reservation-detail"))
    assert "1" in page.text_content(sel(tid, "reservation-tables"))
    assert "2" in page.text_content(sel(tid, "reservation-tables"))


def _rgb(value):
    found = re.search(r"rgba?\(([^)]+)\)", value)
    assert found, f"computed color was not rgb(): {value}"
    channels = re.split(r"[, /]+", found.group(1).strip())
    return [round(float(channel[:-1]) * 2.55) if channel.endswith("%") else int(float(channel)) for channel in channels[:3]]


def _contrast(a, b):
    def luminance(rgb):
        channels = [v / 255 for v in rgb]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_375px_layout_has_no_horizontal_scroll_and_visible_keyboard_focus_contrast(
        page, tid, world):
    page.set_viewport_size({"width": 375, "height": 812})
    sign_in(page, tid)
    page.goto("/")
    page.wait_for_selector(sel(tid, "search-button"))
    search_controls(page, tid, world.date, party_size=6)
    page.click(sel(tid, "slot-t_1+t_2-19:00"))
    page.wait_for_selector(sel(tid, "booking-form"))

    overflow = page.evaluate(
        "() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) "
        "> window.innerWidth"
    )
    assert not overflow, "the page must fit a 375 CSS-pixel viewport"

    page.keyboard.press("Tab")
    focus = page.evaluate("""() => {
      const e = document.activeElement, s = getComputedStyle(e);
      return {visible: !!(e.getClientRects().length),
              keyboard: e.matches(':focus-visible'),
              outlineStyle: s.outlineStyle, outlineWidth: s.outlineWidth,
              boxShadow: s.boxShadow};
    }""")
    assert focus["visible"] and focus["keyboard"]
    assert ((focus["outlineStyle"] != "none" and focus["outlineWidth"] != "0px")
            or focus["boxShadow"] != "none"), "keyboard focus needs a visible indicator"

    colors = page.locator(sel(tid, "search-button")).evaluate("""e => {
      const s = getComputedStyle(e), body = getComputedStyle(document.body);
      const bg = s.backgroundColor === 'rgba(0, 0, 0, 0)' ? body.backgroundColor : s.backgroundColor;
      return {foreground: s.color, background: bg};
    }""")
    assert _contrast(_rgb(colors["foreground"]), _rgb(colors["background"])) >= 4.5, \
        "primary action text must meet 4.5:1 contrast"









