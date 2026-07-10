import pytest
from service import SLIService


def test_standard_streaming_trace():
    """Validates metrics derivation for a normal, successful streaming generation trace."""
    raw_obs = {
        "id": "obs-1",
        "traceId": "trace-1",
        "type": "GENERATION",
        "startTime": "2026-01-15T09:14:22.341Z",
        "completionStartTime": "2026-01-15T09:14:22.749Z",
        "endTime": "2026-01-15T09:14:24.108Z",
        "level": "DEFAULT",
        "traceMetadata": {"team": "AdvisorChat"},
        "providedModelName": "claude-sonnet-4-6",
        "usageDetails": {"input": 612, "output": 248},
        "costDetails": {"total": 0.005556},
        "traceTags": ["streaming"],
    }

    service = SLIService(completion_length_anomaly_threshold=300)
    metrics = service.process_observation(raw_obs)

    assert metrics.status == "SUCCESS"
    assert metrics.team == "AdvisorChat"
    assert metrics.model == "claude-sonnet-4-6"
    # Latency: 22.341 to 24.108 is 1767.0 milliseconds
    assert pytest.approx(metrics.latency_ms, 0.1) == 1767.0
    # TTFT: 22.341 to 22.749 is 408.0 milliseconds
    assert pytest.approx(metrics.time_to_first_token_ms, 0.1) == 408.0
    assert metrics.cost_usd == 0.005556
    assert metrics.is_cached is False
    assert metrics.is_completion_length_anomaly is False


def test_cached_generation_trace():
    """Validates accurate handling of prompt caching tokens and cost values."""
    raw_obs = {
        "id": "obs-2",
        "traceId": "trace-2",
        "type": "GENERATION",
        "startTime": "2026-01-15T09:18:45.117Z",
        "endTime": "2026-01-15T09:18:46.984Z",
        "traceMetadata": {"team": "AdvisorChat"},
        "providedModelName": "claude-sonnet-4-6",
        "usageDetails": {
            "input": 402,
            "cache_read_input_tokens": 3812,
            "output": 284,
        },
        "costDetails": {"total": 0.006610},
        "traceTags": ["streaming", "cached"],
    }

    service = SLIService()
    metrics = service.process_observation(raw_obs)

    assert metrics.is_cached is True
    assert metrics.cache_read_tokens == 3812
    assert metrics.cost_usd == 0.006610


def test_error_and_throttling_trace():
    """Ensures error traces with missing usage/cost fields are parsed safely without crashing."""
    raw_obs = {
        "id": "obs-3",
        "traceId": "trace-3",
        "type": "GENERATION",
        "startTime": "2026-01-15T10:22:11.508Z",
        "endTime": "2026-01-15T10:22:11.873Z",
        "level": "ERROR",
        "statusMessage": "throttling_exception: Rate exceeded for model anthropic.claude-sonnet-4 in region eu-central-1",
        "traceMetadata": {"team": "AdvisorChat"},
        "usageDetails": {},  # Empty on failures
        "costDetails": {},
    }

    service = SLIService()
    metrics = service.process_observation(raw_obs)

    assert metrics.status == "ERROR"
    assert "throttling_exception" in metrics.error_message
    assert metrics.latency_ms == 365.0
    assert metrics.time_to_first_token_ms is None
    assert metrics.input_tokens == 0
    assert metrics.cost_usd == 0.0


def test_anomaly_length_detection():
    """Validates that output token limits trigger completion length anomalies correctly."""
    raw_obs = {
        "id": "obs-4",
        "traceId": "trace-4",
        "type": "GENERATION",
        "usageDetails": {"output": 500},
    }

    # Set threshold low to force a positive assertion
    service = SLIService(completion_length_anomaly_threshold=400)
    metrics = service.process_observation(raw_obs)
    assert metrics.is_completion_length_anomaly is True
