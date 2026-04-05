"""
Query profiling: timing for execute_query calls + optimization hints.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class QueryRecord:
    query: str
    duration_ms: float
    success: bool
    row_count: int = 0
    timestamp: float = field(default_factory=time.time)


class QueryProfiler:
    """Tracks execute_query performance and provides optimization hints."""

    def __init__(self, history_size: int = 100) -> None:
        self.enabled: bool = True
        self._history: deque[QueryRecord] = deque(maxlen=history_size)

    def record(self, query: str, duration_ms: float, success: bool, row_count: int = 0) -> None:
        if self.enabled:
            self._history.append(QueryRecord(
                query=query, duration_ms=duration_ms, success=success, row_count=row_count,
            ))

    def get_stats(self) -> dict:
        if not self._history:
            return {"total_queries": 0, "message": "No queries recorded yet."}
        durations = [r.duration_ms for r in self._history]
        slow = [r for r in self._history if r.duration_ms > 5000]
        return {
            "total_queries": len(self._history),
            "avg_ms": round(sum(durations) / len(durations), 1),
            "max_ms": round(max(durations), 1),
            "min_ms": round(min(durations), 1),
            "slow_queries_over_5s": len(slow),
            "error_count": sum(1 for r in self._history if not r.success),
        }

    def analyze_query(self, query: str, duration_ms: float) -> list[str]:
        """Return optimization hints based on query text and duration."""
        hints: list[str] = []
        upper = query.upper()

        if duration_ms > 10000:
            hints.append(f"Запрос выполнялся {duration_ms/1000:.1f}с — рассмотрите оптимизацию")
        if "SELECT *" in upper or "ВЫБРАТЬ *" in upper or re.search(r'ВЫБРАТЬ\s+\*', upper):
            hints.append("Используется SELECT * — выбирайте только нужные поля")
        if re.search(r'(ПОДОБНО|LIKE)\s+"%', upper):
            hints.append("ПОДОБНО с % в начале — индекс не используется")
        if upper.count("ЛЕВОЕ СОЕДИНЕНИЕ") + upper.count("LEFT JOIN") > 3:
            hints.append("Много LEFT JOIN — рассмотрите использование временных таблиц")
        if "ГДЕ" not in upper and "WHERE" not in upper and "ПЕРВЫЕ" not in upper and "TOP" not in upper:
            hints.append("Нет условия WHERE и ПЕРВЫЕ — запрос вернёт все записи")

        return hints

    def format_profiling_result(self, query: str, duration_ms: float, response_text: str) -> str:
        """Add profiling info to query response."""
        try:
            data = json.loads(response_text)
            row_count = len(data.get("data", [])) if isinstance(data.get("data"), list) else 0
        except (json.JSONDecodeError, TypeError):
            row_count = 0

        hints = self.analyze_query(query, duration_ms)
        profiling = {
            "duration_ms": round(duration_ms, 1),
            "rows_returned": row_count,
        }
        if hints:
            profiling["optimization_hints"] = hints

        # Inject profiling into response
        try:
            data = json.loads(response_text)
            data["_profiling"] = profiling
            return json.dumps(data, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            return response_text + f"\n\n_profiling: {json.dumps(profiling, ensure_ascii=False)}"


# Singleton
profiler = QueryProfiler()
