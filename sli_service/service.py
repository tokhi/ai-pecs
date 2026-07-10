import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SLIMetrics(BaseModel):
    """Data model representing derived Gateway SLIs for a single trace observation."""

    trace_id: str
    observation_id: str
    team: str
    model: str
    status: str  # e.g., "SUCCESS", "ERROR"
    error_message: Optional[str] = None
    latency_ms: float
    time_to_first_token_ms: Optional[float] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    is_cached: bool = False
    is_completion_length_anomaly: bool = False


class SLIService:
    """Service to process Langfuse trace observations and compute platform-level SLIs."""

    def __init__(self, completion_length_anomaly_threshold: int = 1500):
        # A simple static threshold for completion length anomalies.
        # In a real service, this would evaluate a Z-score or historical rolling window per route.
        self.anomaly_threshold = completion_length_anomaly_threshold

    @staticmethod
    def _parse_iso_to_ms(iso_str: Optional[str]) -> Optional[float]:
        """Convert ISO 8601 string to epoch timestamp in milliseconds."""
        if not iso_str:
            return None
        # Handle trailing Z for Python's ISO parser compatibility
        cleaned = iso_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
            return dt.timestamp() * 1000.0
        except ValueError:
            return None

    def process_observation(self, obs: Dict[str, Any]) -> SLIMetrics:
        """Parses a single Langfuse observation and derives key SLIs gracefully."""
        obs_id = obs.get("id", "unknown-obs")
        trace_id = obs.get("traceId", "unknown-trace")

        # Safely extract metadata fields
        trace_metadata = obs.get("traceMetadata") or {}
        team = trace_metadata.get("team", "unattributed")
        model = obs.get("providedModelName") or obs.get("internalModelId") or "unknown-model"

        # Safe parsing of start and end times
        start_time_ms = self._parse_iso_to_ms(obs.get("startTime"))
        end_time_ms = self._parse_iso_to_ms(obs.get("endTime"))
        completion_start_ms = self._parse_iso_to_ms(obs.get("completionStartTime"))

        # Latency calculation
        latency_ms = 0.0
        if start_time_ms is not None and end_time_ms is not None:
            latency_ms = max(0.0, end_time_ms - start_time_ms)

        # TTFT calculation (for streaming)
        ttft_ms = None
        if start_time_ms is not None and completion_start_ms is not None:
            ttft_ms = max(0.0, completion_start_ms - start_time_ms)

        # Status and error classification
        level = obs.get("level", "DEFAULT")
        status_msg = obs.get("statusMessage") or ""
        status = "SUCCESS"
        error_message = None

        if level == "ERROR" or "exception" in status_msg.lower() or "error" in status_msg.lower():
            status = "ERROR"
            error_message = status_msg or "Unknown execution error"

        # Token usage and cache parsing
        usage = obs.get("usageDetails") or {}
        input_tokens = usage.get("input", 0)
        output_tokens = usage.get("output", 0)
        cache_read_tokens = usage.get("cache_read_input_tokens", 0)

        # Cost extraction with fallback
        cost_details = obs.get("costDetails") or {}
        cost_usd = cost_details.get("total", 0.0)

        # Cache classification
        tags = obs.get("traceTags") or []
        is_cached = "cached" in tags or cache_read_tokens > 0

        # Anomaly detection: simple threshold check
        is_anomaly = output_tokens > self.anomaly_threshold

        return SLIMetrics(
            trace_id=trace_id,
            observation_id=obs_id,
            team=team,
            model=model,
            status=status,
            error_message=error_message,
            latency_ms=latency_ms,
            time_to_first_token_ms=ttft_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cost_usd=cost_usd,
            is_cached=is_cached,
            is_completion_length_anomaly=is_anomaly,
        )

    def process_file(self, filepath: str) -> List[SLIMetrics]:
        """Loads and processes an export file of Langfuse traces."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Source file not found: {filepath}")

        with open(filepath, "r") as f:
            payload = json.load(f)

        observations = payload.get("data", [])
        metrics_list = []
        for obs in observations:
            # We filter for GENERATION types since SLIs are calculated on LLM model execution chunks
            if obs.get("type") == "GENERATION":
                metrics_list.append(self.process_observation(obs))

        return metrics_list


if __name__ == "__main__":
    # Example execution pointing to the case study trace sample file
    service = SLIService(completion_length_anomaly_threshold=250)
    try:
        results = service.process_file("data/option_d_langfuse_sample_traces.json")
        print(f"Successfully processed {len(results)} generations:")
        for metric in results:
            print(
                f"- Trace: {metric.trace_id[:8]} | Team: {metric.team:11} | "
                f"Status: {metric.status:7} | Latency: {metric.latency_ms:6.1f}ms | "
                f"TTFT: {str(metric.time_to_first_token_ms or 'N/A'):7} | "
                f"Cost: ${metric.cost_usd:.6f} | Cached: {metric.is_cached} | "
                f"Anomaly: {metric.is_completion_length_anomaly}"
            )
    except Exception as e:
        print(f"Error executing parser: {e}")
