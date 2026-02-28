import pytest
import fakeredis
from collections import defaultdict
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model


# ---------------------------------------------------------------------------
# _atomic_increment patch
#
# fakeredis does not support EVALSHA (used by redis-py's register_script).
# Rather than touching production code, we patch _atomic_increment with a
# pure in-memory counter that also writes the result back into the shared
# fakeredis instance — so functions like check_failed_attempts() that call
# client.get(key) directly can still read the current count.
# ---------------------------------------------------------------------------

class _InMemoryCounter:
    """
    In-memory replacement for _atomic_increment.
    Mimics the Lua script: increments a counter, sets TTL on first call,
    and writes the count back into the shared fakeredis so that plain
    client.get() calls (e.g. check_failed_attempts) can read it.
    """

    def __init__(self):
        self._counts = defaultdict(int)
        self._windows = {}
        self._redis = None  # injected by the fixture

    def __call__(self, key, window_seconds):
        self._counts[key] += 1
        count = self._counts[key]
        if count == 1:
            self._windows[key] = int(window_seconds)
        ttl = self._windows.get(key, int(window_seconds))

        # Mirror the count into fakeredis so client.get(key) readers work
        if self._redis is not None:
            self._redis.setex(key, ttl, str(count).encode())

        return count, ttl

    def reset(self):
        self._counts.clear()
        self._windows.clear()


_counter = _InMemoryCounter()


@pytest.fixture(autouse=True)
def fake_redis(mocker):
    """
    Patch both get_redis_client (for setex/get/delete OTP ops via fakeredis)
    AND _atomic_increment (to bypass the Lua/EVALSHA path unsupported by fakeredis).
    """
    _counter.reset()

    fake = fakeredis.FakeRedis(decode_responses=False)

    # Give the counter access to fakeredis so it can mirror counts back
    _counter._redis = fake

    mocker.patch(
        "apps.accounts.services.redis_service._atomic_increment",
        side_effect=_counter,
    )
    mocker.patch(
        "apps.accounts.services.redis_service.get_redis_client",
        return_value=fake,
    )

    return fake


@pytest.fixture
def api_client():
    """DRF test client."""
    return APIClient()


@pytest.fixture
def authenticated_client(db):
    """An APIClient already authenticated with a JWT access token."""
    from rest_framework_simplejwt.tokens import RefreshToken

    User = get_user_model()
    user = User.objects.create_user(
        username="test@example.com", email="test@example.com", password="pw"
    )
    refresh = RefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client, user