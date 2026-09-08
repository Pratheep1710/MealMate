"""Phase 9 (MP-092/093/094): the HTTP layer in app/routes.py.

These are thin-controller tests — auth, profile lookup, response shape — with the real work
(run_generation_engine, dispatch_week_ready, build_instant_fallback) monkeypatched out, since
those are each already covered by their own test modules. The one thing that must be proven here
and nowhere else is MP-094's idempotency AC: a same-evening sweep call racing the endpoint's own
background trigger for the identical (user_id, week_start) must not double-run — see
test_a_near_simultaneous_sweep_and_endpoint_trigger_only_generate_once below, which exercises the
real run_generation_engine/MP-033 claim against a live throwaway Postgres connection per thread,
not a mock.
"""

from __future__ import annotations

import datetime
import threading
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import DictRow, dict_row

from app import routes
from app.auth import get_current_user_id
from app.config import AppConfig, ExpoConfig, OpenAIConfig, RenderConfig, SupabaseConfig
from app.deps import get_config, get_db
from app.main import app
from app.models import UserProfile
from app.services.generation_engine import run_generation_engine
from app.services.openai_generation import GenerationProviderError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    yield
    app.dependency_overrides.clear()


def _profile(**overrides: object) -> UserProfile:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "dietary_restrictions": [],
        "grocery_day": "saturday",
        "planning_mode": "suggestion",
    }
    defaults.update(overrides)
    return UserProfile.model_construct(**defaults)


def _configured_app_config() -> AppConfig:
    """A real, fully-populated AppConfig (jwt_secret set) — for the two real-auth-rejection tests
    below, which exercise app.auth.get_current_user_id itself rather than overriding it, so
    get_config's override must satisfy that function's own `config.supabase.jwt_secret` access.
    """
    return AppConfig(
        supabase=SupabaseConfig(
            url="https://example.supabase.co",
            anon_key="anon",
            service_role_key="service",
            db_host="db.example.supabase.co",
            db_password="password",
            jwt_secret="test-jwt-secret-that-is-long-enough-for-hs256",
        ),
        openai=OpenAIConfig(api_key="sk-test", model="gpt-test"),
        expo=ExpoConfig(),
        render=RenderConfig(),
    )


def test_trigger_generation_requires_auth(client: TestClient) -> None:
    app.dependency_overrides[get_config] = _configured_app_config

    response = client.post("/generation/trigger")

    assert response.status_code == 401


def test_trigger_generation_returns_404_when_no_profile_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_config] = lambda: object()
    monkeypatch.setattr(routes.profiles_repo, "get_profile", lambda *args: None)

    response = client.post("/generation/trigger")

    assert response.status_code == 404


def test_trigger_generation_schedules_the_background_task_and_returns_202(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = uuid.uuid4()
    today = datetime.date(2026, 9, 10)  # a Thursday
    profile = _profile(grocery_day="saturday", planning_mode="suggestion")

    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_config] = lambda: object()
    monkeypatch.setattr(routes.profiles_repo, "get_profile", lambda *args: profile)
    monkeypatch.setattr(routes, "_today_ist", lambda: today)

    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        routes, "_run_and_notify", lambda *args: calls.append(args)
    )

    response = client.post("/generation/trigger")

    assert response.status_code == 202
    # suggestion mode triggers grocery_day - 1 = Friday; Thursday is one day before that Friday.
    assert response.json() == {"week_start": "2026-09-07"}
    assert len(calls) == 1
    _, called_user_id, called_first_plan_start = calls[0]
    assert called_user_id == user_id
    assert called_first_plan_start == datetime.date(2026, 9, 11)


def test_instant_fallback_requires_auth(client: TestClient) -> None:
    app.dependency_overrides[get_config] = _configured_app_config

    response = client.get("/plan/instant-fallback")

    assert response.status_code == 401


def test_instant_fallback_returns_the_fallback_items_as_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = uuid.uuid4()
    dish_id = uuid.uuid4()
    day = datetime.date(2026, 9, 10)

    from app.models import Dish
    from app.services.generation_models import PlannedItem
    from app.services.instant_fallback import InstantFallback

    dish = Dish(
        id=dish_id,
        name="Idli",
        item_type="breakfast",
        veg_or_nonveg="veg",
        region_style="Tamil Nadu",
        prep_minutes=15,
        track_variety=False,
        dietary_flags=[],
    )
    fallback = InstantFallback(
        items=(
            PlannedItem(day=day, slot="morning", item_type="breakfast", dish_id=dish_id),
            PlannedItem(
                day=day, slot="night", item_type="dinner", dish_id=None, status="needs_manual_pick"
            ),
        ),
        dishes_by_id={dish_id: dish},
    )

    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(routes, "build_instant_fallback", lambda *args, **kwargs: fallback)

    response = client.get("/plan/instant-fallback")

    assert response.status_code == 200
    assert response.json() == [
        {
            "day": "2026-09-10",
            "slot": "morning",
            "item_type": "breakfast",
            "dish_id": str(dish_id),
            "dish_name": "Idli",
        },
        {
            "day": "2026-09-10",
            "slot": "night",
            "item_type": "dinner",
            "dish_id": None,
            "dish_name": None,
        },
    ]


class _FixedMenuGenerator:
    """A stand-in WeeklyMenuGenerator that always fails validation-through-provider-error, so
    run_generation_engine falls through to build_fallback_plan — the zero-LLM path, with no
    OpenAI credentials needed for this race test.
    """

    def generate(self, messages: object) -> None:
        raise GenerationProviderError("no live provider needed for this test")


def _make_user_with_profile(conn: psycopg.Connection[DictRow], user_id: uuid.UUID) -> None:
    conn.execute("insert into auth.users (id) values (%s)", (user_id,))
    conn.execute(
        "insert into user_profiles (id, dietary_restrictions, grocery_day, planning_mode) "
        "values (%s, %s, %s, %s)",
        (user_id, [], "monday", "suggestion"),
    )


def test_a_near_simultaneous_sweep_and_endpoint_trigger_only_generate_once(
    pg_dsn: dict[str, str | int],
) -> None:
    """MP-094's actual DoD: the endpoint's onboarding-triggered call (start_date=a concrete,
    possibly-mid-week date) and the scheduled sweep's call (start_date=None) for the identical
    (user_id, week_start) must not both run generation, even when fired at the same instant from
    two independent connections/threads — the MP-033 atomic claim, unchanged, is what's supposed
    to guarantee this.
    """
    user_id = uuid.uuid4()
    week_start = datetime.date(2026, 8, 24)  # a Monday
    first_plan_start = datetime.date(2026, 8, 26)  # mid-week, as the endpoint would pass

    with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as setup_conn:
        _make_user_with_profile(setup_conn, user_id)

    results: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def _sweep_call(index: int, start_date: datetime.date | None) -> None:
        with psycopg.connect(**pg_dsn, row_factory=dict_row) as race_conn:
            barrier.wait()
            results[index] = run_generation_engine(
                race_conn, user_id, week_start, _FixedMenuGenerator(), start_date=start_date
            )

    threads = [
        threading.Thread(target=_sweep_call, args=(0, first_plan_start)),
        threading.Thread(target=_sweep_call, args=(1, None)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    try:
        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        assert winners[0].plan.source == "fallback"
    finally:
        # autocommit/explicit-commit connections bypass the `conn` fixture's rollback teardown;
        # deleting auth.users cascades through user_profiles to meal_plans/plan_items/
        # generation_jobs/notification_log, so this run's writes don't linger for the rest of the
        # (session-scoped) pytest run — same pattern as test_repositories.py's race test cleanup.
        with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as cleanup_conn:
            cleanup_conn.execute("delete from auth.users where id = %s", (user_id,))
