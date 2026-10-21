"""
Prometheus & Structured Metrics Collector for PosiPulse Pipeline
Tracks latency, throughput, error rates, DPDP delistings, and costs.
"""

from collections import defaultdict
from datetime import datetime, timezone
import threading
from typing import Any, Dict, List


class MetricsCollector:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MetricsCollector, cls).__new__(cls)
                cls._instance._init_metrics()
            return cls._instance

    def _init_metrics(self):
        self._counters = defaultdict(float)
        self._gauges = defaultdict(float)
        self._stage_latencies = defaultdict(list)
        self._stage_counts = defaultdict(int)

    def record_stage_execution(self, stage: str, duration_sec: float, status: str = "success"):
        """Record duration and outcome of a pipeline stage."""
        with self._lock:
            self._stage_latencies[stage].append(duration_sec)
            self._stage_counts[f"{stage}_{status}"] += 1
            self._counters[f"posipulse_pipeline_stage_total_{stage}_{status}"] += 1

    def increment_counter(self, name: str, value: float = 1.0, **labels):
        """Increment a named metric counter."""
        with self._lock:
            label_suffix = "_".join(f"{k}_{v}" for k, v in sorted(labels.items()))
            key = f"{name}_{label_suffix}" if label_suffix else name
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, **labels):
        """Set a named gauge value."""
        with self._lock:
            label_suffix = "_".join(f"{k}_{v}" for k, v in sorted(labels.items()))
            key = f"{name}_{label_suffix}" if label_suffix else name
            self._gauges[key] = value

    def get_summary(self) -> Dict[str, Any]:
        """Return structured JSON summary of metrics."""
        with self._lock:
            avg_latencies = {}
            for stage, lats in self._stage_latencies.items():
                avg_latencies[stage] = round(sum(lats) / len(lats), 4) if lats else 0.0

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "average_stage_latencies_sec": avg_latencies,
                "stage_executions": dict(self._stage_counts),
            }

    def export_prometheus_text(self) -> str:
        """Export metrics in standard Prometheus text exposition format."""
        with self._lock:
            lines = [
                "# HELP posipulse_pipeline_stage_total Total pipeline stage executions",
                "# TYPE posipulse_pipeline_stage_total counter"
            ]
            for key, val in self._counters.items():
                lines.append(f"{key} {float(val)}")

            lines.append("# HELP posipulse_gauge Active system gauge metrics")
            lines.append("# TYPE posipulse_gauge gauge")
            for key, val in self._gauges.items():
                lines.append(f"{key} {float(val)}")

            for stage, lats in self._stage_latencies.items():
                avg = sum(lats) / len(lats) if lats else 0.0
                lines.append(f'posipulse_stage_latency_seconds_average{{stage="{stage}"}} {round(avg, 5)}')

            return "\n".join(lines) + "\n"

    def reset_for_testing(self):
        """Reset internal metrics for test suites."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._stage_latencies.clear()
            self._stage_counts.clear()


metrics_collector = MetricsCollector()
