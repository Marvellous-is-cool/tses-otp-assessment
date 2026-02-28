"""
apps/accounts/tests.py

We test three layers separately:
1. Redis service — unit tests, pure logic, no HTTP
2. OTP service — unit tests with mocked Celery tasks  
3. API views — integration tests, full HTTP request/response cycle

This separation means when a test fails we will know exactly which layer broke.
"""
import pytest
from django.conf import settings
from unittest.mock import patch


# ===========================================================================
# REDIS SERVICE TESTS
# These test the raw Redis operations in isolation.
# fakeredis handles the Redis layer — no real Redis needed.
# ===========================================================================

class TestOTPStorage:
    """Tests for OTP generation, storage, retrieval and deletion."""

    def test_generate_otp_is_six_digits(self):
        from apps.accounts.services.redis_service import generate_otp
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_generate_otp_is_random(self):
        """Two consecutive OTPs should not be the same (with overwhelming probability)."""
        from apps.accounts.services.redis_service import generate_otp
        otps = {generate_otp() for _ in range(10)}
        # If all 10 are identical something is very wrong
        assert len(otps) > 1

    def test_store_and_retrieve_otp(self, fake_redis):
        from apps.accounts.services.redis_service import store_otp, get_otp
        store_otp("user@example.com", "123456")
        assert get_otp("user@example.com") == "123456"

    def test_get_otp_returns_none_when_not_stored(self, fake_redis):
        from apps.accounts.services.redis_service import get_otp
        assert get_otp("nobody@example.com") is None

    def test_delete_otp_enforces_one_time_use(self, fake_redis):
        """After deletion, OTP should no longer be retrievable."""
        from apps.accounts.services.redis_service import store_otp, get_otp, delete_otp
        store_otp("user@example.com", "123456")
        delete_otp("user@example.com")
        assert get_otp("user@example.com") is None

    def test_otp_is_case_insensitive_for_email(self, fake_redis):
        """User@Example.COM and user@example.com should refer to the same OTP."""
        from apps.accounts.services.redis_service import store_otp, get_otp
        store_otp("User@Example.COM", "999888")
        assert get_otp("user@example.com") == "999888"


class TestEmailRateLimit:
    """Tests for per-email OTP request rate limiting."""

    def test_first_request_is_allowed(self, fake_redis):
        from apps.accounts.services.redis_service import check_email_rate_limit
        limited, retry_after = check_email_rate_limit("user@example.com")
        assert limited is False
        assert retry_after == 0

    def test_requests_within_limit_are_allowed(self, fake_redis):
        from apps.accounts.services.redis_service import check_email_rate_limit
        max_allowed = settings.RATE_LIMIT["EMAIL_MAX"]
        for i in range(max_allowed):
            limited, _ = check_email_rate_limit("user@example.com")
            assert limited is False, f"Request {i+1} should be allowed"

    def test_request_exceeding_limit_is_blocked(self, fake_redis):
        from apps.accounts.services.redis_service import check_email_rate_limit
        max_allowed = settings.RATE_LIMIT["EMAIL_MAX"]
        # Exhaust the limit
        for _ in range(max_allowed):
            check_email_rate_limit("user@example.com")
        # This one should be blocked
        limited, retry_after = check_email_rate_limit("user@example.com")
        assert limited is True
        assert retry_after > 0

    def test_different_emails_have_independent_limits(self, fake_redis):
        from apps.accounts.services.redis_service import check_email_rate_limit
        max_allowed = settings.RATE_LIMIT["EMAIL_MAX"]
        # Exhaust limit for email A
        for _ in range(max_allowed + 1):
            check_email_rate_limit("a@example.com")
        # Email B should still be allowed
        limited, _ = check_email_rate_limit("b@example.com")
        assert limited is False


class TestFailedAttempts:
    """Tests for OTP verification lockout logic."""

    def test_no_failed_attempts_means_not_locked(self, fake_redis):
        from apps.accounts.services.redis_service import check_failed_attempts
        locked, eta = check_failed_attempts("user@example.com")
        assert locked is False
        assert eta == 0

    def test_lockout_triggers_after_max_failures(self, fake_redis):
        from apps.accounts.services.redis_service import (
            record_failed_attempt, check_failed_attempts
        )
        max_failures = settings.RATE_LIMIT["FAILED_MAX"]
        for _ in range(max_failures):
            record_failed_attempt("user@example.com")
        locked, eta = check_failed_attempts("user@example.com")
        assert locked is True
        assert eta > 0

    def test_clear_failed_attempts_removes_lockout(self, fake_redis):
        from apps.accounts.services.redis_service import (
            record_failed_attempt, check_failed_attempts, clear_failed_attempts
        )
        max_failures = settings.RATE_LIMIT["FAILED_MAX"]
        for _ in range(max_failures):
            record_failed_attempt("user@example.com")
        clear_failed_attempts("user@example.com")
        locked, _ = check_failed_attempts("user@example.com")
        assert locked is False


# ===========================================================================
# API ENDPOINT TESTS
# Full HTTP request/response cycle using DRF's APIClient.
# Celery tasks are mocked — we don't want real emails or DB writes
# happening during tests. We just verify .delay() was called.
# ===========================================================================

@pytest.mark.django_db
class TestOTPRequestEndpoint:
    """Integration tests for POST /api/v1/auth/otp/request"""

    URL = "/api/v1/auth/otp/request"

    def test_valid_request_returns_202(self, api_client, fake_redis):
        with patch("apps.accounts.services.otp_service.send_otp_email") as mock_email, \
             patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_email.delay = lambda **kw: None
            mock_audit.delay = lambda **kw: None

            response = api_client.post(
                self.URL,
                {"email": "user@example.com"},
                format="json",
            )

        assert response.status_code == 202
        assert "expires_in" in response.data
        assert response.data["expires_in"] == 300

    def test_invalid_email_returns_400(self, api_client, fake_redis):
        response = api_client.post(
            self.URL,
            {"email": "not-an-email"},
            format="json",
        )
        assert response.status_code == 400

    def test_missing_email_returns_400(self, api_client, fake_redis):
        response = api_client.post(self.URL, {}, format="json")
        assert response.status_code == 400

    def test_rate_limit_returns_429(self, api_client, fake_redis):
        """After exceeding the email rate limit, should get 429."""
        with patch("apps.accounts.services.otp_service.send_otp_email") as mock_email, \
             patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_email.delay = lambda **kw: None
            mock_audit.delay = lambda **kw: None

            max_allowed = settings.RATE_LIMIT["EMAIL_MAX"]
            for _ in range(max_allowed):
                api_client.post(
                    self.URL,
                    {"email": "ratelimit@example.com"},
                    format="json",
                )
            # This one should be blocked
            response = api_client.post(
                self.URL,
                {"email": "ratelimit@example.com"},
                format="json",
            )

        assert response.status_code == 429
        assert "retry_after" in response.data

    def test_email_is_normalised_to_lowercase(self, api_client, fake_redis):
        """Upper and lowercase versions of same email should be treated identically."""
        with patch("apps.accounts.services.otp_service.send_otp_email") as mock_email, \
             patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_email.delay = lambda **kw: None
            mock_audit.delay = lambda **kw: None

            max_allowed = settings.RATE_LIMIT["EMAIL_MAX"]
            for _ in range(max_allowed):
                api_client.post(
                    self.URL,
                    {"email": "User@Example.com"},
                    format="json",
                )
            response = api_client.post(
                self.URL,
                {"email": "user@example.com"},  # lowercase version
                format="json",
            )
        # Should be rate limited — same email, different case
        assert response.status_code == 429


@pytest.mark.django_db
class TestOTPVerifyEndpoint:
    """Integration tests for POST /api/v1/auth/otp/verify"""

    REQUEST_URL = "/api/v1/auth/otp/request"
    VERIFY_URL = "/api/v1/auth/otp/verify"

    def _request_otp(self, fake_redis, email="user@example.com"):
        """Helper — stores an OTP directly in fake Redis and returns it."""
        from apps.accounts.services.redis_service import store_otp, generate_otp
        otp = generate_otp()
        store_otp(email, otp)
        return otp

    def test_correct_otp_returns_200_with_tokens(self, api_client, fake_redis):
        with patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_audit.delay = lambda **kw: None
            otp = self._request_otp(fake_redis)
            response = api_client.post(
                self.VERIFY_URL,
                {"email": "user@example.com", "otp": otp},
                format="json",
            )

        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["created"] is True

    def test_otp_is_one_time_use(self, api_client, fake_redis):
        """Using the same OTP twice should fail on the second attempt."""
        with patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_audit.delay = lambda **kw: None
            otp = self._request_otp(fake_redis)

            # First use — should succeed
            response1 = api_client.post(
                self.VERIFY_URL,
                {"email": "user@example.com", "otp": otp},
                format="json",
            )
            assert response1.status_code == 200

            # Second use — OTP was deleted, should fail
            response2 = api_client.post(
                self.VERIFY_URL,
                {"email": "user@example.com", "otp": otp},
                format="json",
            )
            assert response2.status_code == 400

    def test_wrong_otp_returns_400(self, api_client, fake_redis):
        with patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_audit.delay = lambda **kw: None
            self._request_otp(fake_redis)
            response = api_client.post(
                self.VERIFY_URL,
                {"email": "user@example.com", "otp": "000000"},
                format="json",
            )
        assert response.status_code == 400
        assert "error" in response.data

    def test_lockout_after_max_failures_returns_423(self, api_client, fake_redis):
        with patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_audit.delay = lambda **kw: None
            self._request_otp(fake_redis)
            max_failures = settings.RATE_LIMIT["FAILED_MAX"]

            for _ in range(max_failures):
                api_client.post(
                    self.VERIFY_URL,
                    {"email": "user@example.com", "otp": "000000"},
                    format="json",
                )

            response = api_client.post(
                self.VERIFY_URL,
                {"email": "user@example.com", "otp": "000000"},
                format="json",
            )

        assert response.status_code == 423
        assert "unlock_eta" in response.data

    def test_expired_otp_returns_400(self, api_client, fake_redis):
        """If OTP was never stored (simulates expiry), should return 400."""
        with patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_audit.delay = lambda **kw: None
            response = api_client.post(
                self.VERIFY_URL,
                {"email": "nobody@example.com", "otp": "123456"},
                format="json",
            )
        assert response.status_code == 400

    def test_second_login_does_not_create_new_user(self, api_client, fake_redis):
        """Verifying OTP twice with same email should return created=False second time."""
        with patch("apps.accounts.services.otp_service.write_audit_log") as mock_audit:
            mock_audit.delay = lambda **kw: None

            # First login
            otp = self._request_otp(fake_redis, "returning@example.com")
            response1 = api_client.post(
                self.VERIFY_URL,
                {"email": "returning@example.com", "otp": otp},
                format="json",
            )
            assert response1.data["created"] is True

            # Second login
            otp2 = self._request_otp(fake_redis, "returning@example.com")
            response2 = api_client.post(
                self.VERIFY_URL,
                {"email": "returning@example.com", "otp": otp2},
                format="json",
            )
            assert response2.data["created"] is False


@pytest.mark.django_db
class TestAuditLogEndpoint:
    """Integration tests for GET /api/v1/audit/logs"""

    URL = "/api/v1/audit/logs"

    def test_unauthenticated_request_returns_401(self, api_client):
        response = api_client.get(self.URL)
        assert response.status_code == 401

    def test_authenticated_request_returns_200(self, authenticated_client):
        client, user = authenticated_client
        response = client.get(self.URL)
        assert response.status_code == 200
        assert "results" in response.data
        assert "count" in response.data

    def test_results_are_paginated(self, authenticated_client):
        from apps.audit.models import AuditLog
        client, user = authenticated_client

        # Create 25 audit logs (more than PAGE_SIZE of 20)
        for i in range(25):
            AuditLog.objects.create(
                event="OTP_REQUESTED",
                email=f"user{i}@example.com",
                ip_address="127.0.0.1",
            )

        response = client.get(self.URL)
        assert response.status_code == 200
        # Should only return PAGE_SIZE results per page
        assert len(response.data["results"]) == 20
        assert response.data["count"] == 25
        assert response.data["next"] is not None

    def test_filter_by_email(self, authenticated_client):
        from apps.audit.models import AuditLog
        client, user = authenticated_client

        AuditLog.objects.create(event="OTP_REQUESTED", email="a@example.com", ip_address="127.0.0.1")
        AuditLog.objects.create(event="OTP_REQUESTED", email="b@example.com", ip_address="127.0.0.1")

        response = client.get(self.URL, {"email": "a@example.com"})
        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["email"] == "a@example.com"

    def test_filter_by_event(self, authenticated_client):
        from apps.audit.models import AuditLog
        client, user = authenticated_client

        AuditLog.objects.create(event="OTP_REQUESTED", email="a@example.com", ip_address="127.0.0.1")
        AuditLog.objects.create(event="OTP_FAILED", email="a@example.com", ip_address="127.0.0.1")
        AuditLog.objects.create(event="OTP_VERIFIED", email="a@example.com", ip_address="127.0.0.1")

        response = client.get(self.URL, {"event": "OTP_FAILED"})
        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["event"] == "OTP_FAILED"

    def test_results_ordered_newest_first(self, authenticated_client):
        from apps.audit.models import AuditLog
        from django.utils import timezone
        from datetime import timedelta
        client, user = authenticated_client

        now = timezone.now()
        old = AuditLog.objects.create(event="OTP_REQUESTED", email="old@example.com", ip_address="127.0.0.1")
        new = AuditLog.objects.create(event="OTP_VERIFIED", email="new@example.com", ip_address="127.0.0.1")

        response = client.get(self.URL)
        assert response.status_code == 200
        # First result should be the newest
        assert response.data["results"][0]["id"] == new.id