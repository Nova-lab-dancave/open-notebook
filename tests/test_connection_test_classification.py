"""
Tests for connection-test error classification (open_notebook/ai/connection_tester.py).

Two semantics share one auth/network classifier:
- The *provider* test asks only "do these credentials reach a working
  provider?" — so a missing/retired/unsupported test model is SUCCESS (the
  #970 durability fix): a hard-coded test model going away must never be
  misreported as a broken connection.
- The *individual model* test validates one specific registered model, so a
  missing model there IS a failure.
"""

import pytest

from open_notebook.ai.connection_tester import (
    _connection_failure_reason,
    _is_rate_limit,
    _normalize_error_message,
    classify_provider_test_error,
)

# Realistic provider error strings.
GOOGLE_RETIRED_MODEL_404 = (
    "404 models/gemini-2.0-flash is not found for API version v1beta, "
    "or is not supported for generateContent."
)
ANTHROPIC_RETIRED_HAIKU_404 = (
    "Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', "
    "'message': 'model: claude-3-haiku-20240307'}, 'request_id': 'req_test'}"
)
# A retired/missing model whose random Anthropic request id embeds a bare
# "403" — the classifier must not read the id as a permission failure.
ANTHROPIC_404_WITH_403_IN_REQUEST_ID = (
    "Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', "
    "'message': 'model: claude-haiku-4-5-20251001'}, "
    "'request_id': 'req_011Cga403VtXy92ABc'}"
)
# A genuine permission failure whose request id ALSO embeds "403" — must
# still be classified as a connection failure (via the HTTP status, not the id).
ANTHROPIC_PERM_403_WITH_REQUEST_ID = (
    "Error code: 403 - {'type': 'error', 'error': {'type': 'permission_error', "
    "'message': 'Your API key does not have permission to use the specified resource.'}, "
    "'request_id': 'req_011Cga403VtXy92ABc'}"
)
GOOGLE_DEPRECATED = "400 Model gemini-1.5-pro has been deprecated."
GOOGLE_BAD_KEY_401 = "401 API key not valid. Please pass a valid API key."
GOOGLE_PERM_403 = "403 Permission denied on resource project."
GOOGLE_QUOTA_429 = "429 Resource has been exhausted (e.g. check quota)."
DNS_FAILURE = (
    "Connection error: [Errno -2] Name or service not known (getaddrinfo failed)"
)
TIMEOUT = "Request timed out after 10s"


class TestConnectionFailureReason:
    """Only auth/permission/network are true connection failures."""

    @pytest.mark.parametrize(
        "msg,expected_fragment",
        [
            (GOOGLE_BAD_KEY_401, "Invalid API key"),
            (GOOGLE_PERM_403, "lacks required permissions"),
            (DNS_FAILURE, "Connection error"),
            (TIMEOUT, "timed out"),
        ],
    )
    def test_real_failures_return_a_reason(self, msg, expected_fragment):
        reason = _connection_failure_reason(msg)
        assert reason is not None
        assert expected_fragment in reason

    @pytest.mark.parametrize(
        "msg",
        [
            GOOGLE_RETIRED_MODEL_404,
            GOOGLE_DEPRECATED,
            GOOGLE_QUOTA_429,
            ANTHROPIC_RETIRED_HAIKU_404,
        ],
    )
    def test_provider_reached_returns_none(self, msg):
        # A model/quota problem came back FROM the provider — not a failure.
        assert _connection_failure_reason(msg) is None

    def test_model_id_date_suffix_is_not_a_403(self):
        # Regression for #1282: "20240307" contains the digits 403 but is not
        # an HTTP 403 permission failure.
        assert _connection_failure_reason(ANTHROPIC_RETIRED_HAIKU_404) is None
        assert _connection_failure_reason(GOOGLE_PERM_403) is not None

    def test_request_id_digits_are_not_a_403(self):
        # A random provider request id can embed a bare "403"; a missing
        # model carrying such an id must not be a connection failure.
        assert _connection_failure_reason(ANTHROPIC_404_WITH_403_IN_REQUEST_ID) is None

    def test_real_403_with_request_id_still_fails(self):
        # Stripping request ids must not hide a genuine permission failure.
        reason = _connection_failure_reason(ANTHROPIC_PERM_403_WITH_REQUEST_ID)
        assert reason is not None
        assert "lacks required permissions" in reason


class TestRateLimitDetection:
    @pytest.mark.parametrize(
        "msg",
        [
            "429 Too Many Requests",
            "Resource has been exhausted (e.g. check quota).",
            "You have hit your rate limit",
            "quota exceeded for this project",
        ],
    )
    def test_detects_throttling_phrasings(self, msg):
        assert _is_rate_limit(msg) is True

    def test_plain_model_error_is_not_rate_limit(self):
        assert _is_rate_limit(GOOGLE_RETIRED_MODEL_404) is False


class TestClassifyProviderTestError:
    """Provider test: only bad creds / unreachable endpoint fail."""

    def test_retired_test_model_is_success(self):
        # The core #970 regression: a shut-down test model must report the
        # key as valid, not the connection as broken.
        success, message = classify_provider_test_error(GOOGLE_RETIRED_MODEL_404)
        assert success is True
        assert "test model unavailable" in message

    def test_anthropic_retired_haiku_with_403_date_suffix_is_success(self):
        # #1282: Anthropic's not_found_error for claude-3-haiku-20240307 must
        # not be misclassified as "lacks required permissions" because the
        # model id embeds the digit sequence 403.
        success, message = classify_provider_test_error(ANTHROPIC_RETIRED_HAIKU_404)
        assert success is True
        assert "test model unavailable" in message
        assert "permissions" not in message

    def test_deprecated_model_is_success(self):
        success, _ = classify_provider_test_error(GOOGLE_DEPRECATED)
        assert success is True

    def test_rate_limit_is_success(self):
        success, message = classify_provider_test_error(GOOGLE_QUOTA_429)
        assert success is True
        assert "connection works" in message

    @pytest.mark.parametrize(
        "msg,expected_fragment",
        [
            (GOOGLE_BAD_KEY_401, "Invalid API key"),
            (GOOGLE_PERM_403, "lacks required permissions"),
            (DNS_FAILURE, "Connection error"),
            (TIMEOUT, "timed out"),
        ],
    )
    def test_auth_and_network_still_fail(self, msg, expected_fragment):
        success, message = classify_provider_test_error(msg)
        assert success is False
        assert expected_fragment in message

    def test_unrecognized_error_stays_a_failure(self):
        # A construction/config error we can't attribute to the provider is
        # surfaced, not silently reported as success.
        success, message = classify_provider_test_error(
            "TypeError: create_language() missing required config 'base_url'"
        )
        assert success is False
        assert "Error:" in message


class TestIndividualModelSemanticsDiffer:
    """The SAME model-not-found string is failure for the individual-model
    test but success for the provider test — the intended difference."""

    def test_model_not_found_is_failure_for_individual_test(self):
        success, message = _normalize_error_message(GOOGLE_RETIRED_MODEL_404)
        assert success is False
        assert "Model not found" in message

    def test_same_string_is_success_for_provider_test(self):
        success, _ = classify_provider_test_error(GOOGLE_RETIRED_MODEL_404)
        assert success is True

    def test_individual_test_shares_auth_classification(self):
        success, message = _normalize_error_message(GOOGLE_BAD_KEY_401)
        assert success is False
        assert "Invalid API key" in message
