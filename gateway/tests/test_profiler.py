"""Tests for QueryProfiler: record, get_stats, analyze_query, format_profiling_result."""

import json
import sys
from pathlib import Path

# Allow importing gateway package from the tests directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.profiler import QueryProfiler, QueryRecord


# ---------------------------------------------------------------------------
# QueryRecord dataclass
# ---------------------------------------------------------------------------

class TestQueryRecord:

    def test_defaults(self):
        rec = QueryRecord(query="SELECT 1", duration_ms=10.0, success=True)
        assert rec.query == "SELECT 1"
        assert rec.duration_ms == 10.0
        assert rec.success is True
        assert rec.row_count == 0
        assert rec.timestamp > 0

    def test_custom_row_count(self):
        rec = QueryRecord(query="q", duration_ms=5.0, success=False, row_count=42)
        assert rec.row_count == 42
        assert rec.success is False


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------

class TestRecord:

    def test_record_appends_to_history(self):
        p = QueryProfiler()
        p.record("q1", 100.0, True)
        p.record("q2", 200.0, False, row_count=5)
        assert len(p._history) == 2
        assert p._history[0].query == "q1"
        assert p._history[1].query == "q2"
        assert p._history[1].row_count == 5

    def test_record_respects_enabled_flag(self):
        p = QueryProfiler()
        p.enabled = False
        p.record("q1", 100.0, True)
        assert len(p._history) == 0

    def test_record_respects_history_size(self):
        p = QueryProfiler(history_size=3)
        for i in range(5):
            p.record(f"q{i}", float(i), True)
        assert len(p._history) == 3
        # oldest entries evicted
        assert p._history[0].query == "q2"
        assert p._history[1].query == "q3"
        assert p._history[2].query == "q4"

    def test_record_stores_success_flag(self):
        p = QueryProfiler()
        p.record("ok", 10.0, True)
        p.record("fail", 20.0, False)
        assert p._history[0].success is True
        assert p._history[1].success is False


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------

class TestGetStats:

    def test_empty_stats(self):
        p = QueryProfiler()
        stats = p.get_stats()
        assert stats["total_queries"] == 0
        assert "message" in stats

    def test_single_record(self):
        p = QueryProfiler()
        p.record("q", 123.4, True, row_count=10)
        stats = p.get_stats()
        assert stats["total_queries"] == 1
        assert stats["avg_ms"] == 123.4
        assert stats["max_ms"] == 123.4
        assert stats["min_ms"] == 123.4
        assert stats["slow_queries_over_5s"] == 0
        assert stats["error_count"] == 0

    def test_multiple_records(self):
        p = QueryProfiler()
        p.record("q1", 100.0, True)
        p.record("q2", 200.0, True)
        p.record("q3", 300.0, True)
        stats = p.get_stats()
        assert stats["total_queries"] == 3
        assert stats["avg_ms"] == 200.0
        assert stats["max_ms"] == 300.0
        assert stats["min_ms"] == 100.0

    def test_slow_queries_threshold(self):
        p = QueryProfiler()
        p.record("fast", 1000.0, True)
        p.record("slow1", 5001.0, True)
        p.record("slow2", 10000.0, True)
        stats = p.get_stats()
        assert stats["slow_queries_over_5s"] == 2

    def test_exactly_5000ms_not_slow(self):
        p = QueryProfiler()
        p.record("borderline", 5000.0, True)
        stats = p.get_stats()
        assert stats["slow_queries_over_5s"] == 0

    def test_error_count(self):
        p = QueryProfiler()
        p.record("ok1", 10.0, True)
        p.record("fail1", 20.0, False)
        p.record("ok2", 30.0, True)
        p.record("fail2", 40.0, False)
        p.record("fail3", 50.0, False)
        stats = p.get_stats()
        assert stats["error_count"] == 3

    def test_rounding(self):
        p = QueryProfiler()
        p.record("q1", 10.123, True)
        p.record("q2", 20.456, True)
        p.record("q3", 30.789, True)
        stats = p.get_stats()
        # avg = (10.123 + 20.456 + 30.789) / 3 = 20.456
        assert stats["avg_ms"] == 20.5
        assert stats["max_ms"] == 30.8
        assert stats["min_ms"] == 10.1


# ---------------------------------------------------------------------------
# analyze_query()
# ---------------------------------------------------------------------------

class TestAnalyzeQuery:

    def setup_method(self):
        self.p = QueryProfiler()

    # -- Slow query hint --

    def test_slow_query_hint(self):
        hints = self.p.analyze_query("ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 15000.0)
        assert any("15.0с" in h for h in hints)

    def test_no_slow_hint_under_threshold(self):
        hints = self.p.analyze_query("ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 9999.0)
        assert not any("оптимизац" in h.lower() for h in hints)

    def test_exactly_10000ms_not_slow(self):
        hints = self.p.analyze_query("ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 10000.0)
        assert not any("оптимизац" in h.lower() for h in hints)

    # -- SELECT * hint --

    def test_select_star_english(self):
        hints = self.p.analyze_query("SELECT * FROM Table WHERE x = 1", 100.0)
        assert any("SELECT *" in h for h in hints)

    def test_select_star_russian(self):
        hints = self.p.analyze_query("ВЫБРАТЬ * ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 100.0)
        assert any("SELECT *" in h for h in hints)

    def test_select_star_russian_with_whitespace(self):
        hints = self.p.analyze_query("ВЫБРАТЬ   * ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 100.0)
        assert any("SELECT *" in h for h in hints)

    def test_no_select_star_hint_for_named_fields(self):
        hints = self.p.analyze_query("ВЫБРАТЬ Ссылка, Наименование ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 100.0)
        assert not any("SELECT *" in h for h in hints)

    # -- LIKE/ПОДОБНО with leading % --

    def test_like_leading_percent(self):
        hints = self.p.analyze_query('ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Наименование ПОДОБНО "%тест"', 100.0)
        assert any("ПОДОБНО" in h for h in hints)

    def test_like_english_leading_percent(self):
        hints = self.p.analyze_query('SELECT Name FROM Items WHERE Name LIKE "%test"', 100.0)
        assert any("ПОДОБНО" in h for h in hints)

    def test_like_no_leading_percent(self):
        hints = self.p.analyze_query('ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Наименование ПОДОБНО "тест%"', 100.0)
        assert not any("ПОДОБНО" in h for h in hints)

    # -- Many LEFT JOINs --

    def test_many_left_joins_russian(self):
        query = """ВЫБРАТЬ А.Ссылка ИЗ Таблица КАК А
            ЛЕВОЕ СОЕДИНЕНИЕ Таблица2 ПО А.Ссылка = Таблица2.Ссылка
            ЛЕВОЕ СОЕДИНЕНИЕ Таблица3 ПО А.Ссылка = Таблица3.Ссылка
            ЛЕВОЕ СОЕДИНЕНИЕ Таблица4 ПО А.Ссылка = Таблица4.Ссылка
            ЛЕВОЕ СОЕДИНЕНИЕ Таблица5 ПО А.Ссылка = Таблица5.Ссылка
            ГДЕ А.Ссылка = &Ссылка"""
        hints = self.p.analyze_query(query, 100.0)
        assert any("LEFT JOIN" in h for h in hints)

    def test_many_left_joins_english(self):
        query = """SELECT A.Ref FROM T AS A
            LEFT JOIN T2 ON A.Ref = T2.Ref
            LEFT JOIN T3 ON A.Ref = T3.Ref
            LEFT JOIN T4 ON A.Ref = T4.Ref
            LEFT JOIN T5 ON A.Ref = T5.Ref
            WHERE A.Ref = &Ref"""
        hints = self.p.analyze_query(query, 100.0)
        assert any("LEFT JOIN" in h for h in hints)

    def test_few_left_joins_no_hint(self):
        query = """ВЫБРАТЬ А.Ссылка ИЗ Таблица КАК А
            ЛЕВОЕ СОЕДИНЕНИЕ Таблица2 ПО А.Ссылка = Таблица2.Ссылка
            ЛЕВОЕ СОЕДИНЕНИЕ Таблица3 ПО А.Ссылка = Таблица3.Ссылка
            ГДЕ А.Ссылка = &Ссылка"""
        hints = self.p.analyze_query(query, 100.0)
        assert not any("LEFT JOIN" in h for h in hints)

    def test_exactly_3_left_joins_no_hint(self):
        query = """ВЫБРАТЬ А.Ссылка ИЗ Таблица КАК А
            ЛЕВОЕ СОЕДИНЕНИЕ Т2 ПО 1=1
            ЛЕВОЕ СОЕДИНЕНИЕ Т3 ПО 1=1
            ЛЕВОЕ СОЕДИНЕНИЕ Т4 ПО 1=1
            ГДЕ А.Ссылка = &Ссылка"""
        hints = self.p.analyze_query(query, 100.0)
        assert not any("LEFT JOIN" in h for h in hints)

    # -- No WHERE and no TOP/ПЕРВЫЕ --

    def test_no_where_no_top_hint(self):
        hints = self.p.analyze_query("ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура", 100.0)
        assert any("WHERE" in h for h in hints)

    def test_no_where_no_top_english(self):
        hints = self.p.analyze_query("SELECT Ref FROM Catalog.Items", 100.0)
        assert any("WHERE" in h for h in hints)

    def test_where_present_no_hint(self):
        hints = self.p.analyze_query("ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка", 100.0)
        assert not any("WHERE" in h for h in hints)

    def test_where_english_present_no_hint(self):
        hints = self.p.analyze_query("SELECT Ref FROM Catalog.Items WHERE Ref = &Ref", 100.0)
        assert not any("WHERE" in h for h in hints)

    def test_top_suppresses_no_where_hint(self):
        hints = self.p.analyze_query("ВЫБРАТЬ ПЕРВЫЕ 10 Ссылка ИЗ Справочник.Номенклатура", 100.0)
        assert not any("WHERE" in h for h in hints)

    def test_top_english_suppresses_no_where_hint(self):
        hints = self.p.analyze_query("SELECT TOP 10 Ref FROM Catalog.Items", 100.0)
        assert not any("WHERE" in h for h in hints)

    # -- Clean query produces no hints --

    def test_clean_query_no_hints(self):
        query = "ВЫБРАТЬ Ссылка, Наименование ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        hints = self.p.analyze_query(query, 100.0)
        assert hints == []

    # -- Multiple hints at once --

    def test_multiple_hints_combined(self):
        query = 'ВЫБРАТЬ * ИЗ Справочник.Номенклатура'
        hints = self.p.analyze_query(query, 15000.0)
        # Should get: slow query, SELECT *, no WHERE
        assert len(hints) >= 3
        assert any("15.0с" in h for h in hints)
        assert any("SELECT *" in h for h in hints)
        assert any("WHERE" in h for h in hints)


# ---------------------------------------------------------------------------
# format_profiling_result()
# ---------------------------------------------------------------------------

class TestFormatProfilingResult:

    def setup_method(self):
        self.p = QueryProfiler()

    def test_valid_json_response_with_data(self):
        response = json.dumps({"data": [{"id": 1}, {"id": 2}]})
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 50.0, response)
        parsed = json.loads(result)
        assert "_profiling" in parsed
        assert parsed["_profiling"]["duration_ms"] == 50.0
        assert parsed["_profiling"]["rows_returned"] == 2

    def test_valid_json_no_data_key(self):
        response = json.dumps({"status": "ok"})
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 30.0, response)
        parsed = json.loads(result)
        assert parsed["_profiling"]["rows_returned"] == 0

    def test_valid_json_data_not_list(self):
        response = json.dumps({"data": "not_a_list"})
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 30.0, response)
        parsed = json.loads(result)
        assert parsed["_profiling"]["rows_returned"] == 0

    def test_empty_data_list(self):
        response = json.dumps({"data": []})
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 30.0, response)
        parsed = json.loads(result)
        assert parsed["_profiling"]["rows_returned"] == 0

    def test_no_hints_when_query_clean(self):
        response = json.dumps({"data": [{"id": 1}]})
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 50.0, response)
        parsed = json.loads(result)
        assert "optimization_hints" not in parsed["_profiling"]

    def test_hints_included_when_present(self):
        response = json.dumps({"data": []})
        query = "ВЫБРАТЬ * ИЗ Справочник.Номенклатура"
        result = self.p.format_profiling_result(query, 50.0, response)
        parsed = json.loads(result)
        assert "optimization_hints" in parsed["_profiling"]
        assert len(parsed["_profiling"]["optimization_hints"]) > 0

    def test_duration_rounding(self):
        response = json.dumps({"data": []})
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 123.456, response)
        parsed = json.loads(result)
        assert parsed["_profiling"]["duration_ms"] == 123.5

    def test_invalid_json_response(self):
        response = "plain text response, not json"
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 50.0, response)
        assert result.startswith("plain text response, not json")
        assert "_profiling:" in result

    def test_invalid_json_profiling_appended(self):
        response = "error happened"
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        result = self.p.format_profiling_result(query, 99.9, response)
        # The profiling info is appended as a JSON string after "\n\n_profiling: "
        profiling_str = result.split("_profiling: ", 1)[1]
        profiling = json.loads(profiling_str)
        assert profiling["duration_ms"] == 99.9
        assert profiling["rows_returned"] == 0

    def test_invalid_json_with_hints(self):
        response = "error happened"
        query = "ВЫБРАТЬ * ИЗ Справочник.Номенклатура"
        result = self.p.format_profiling_result(query, 50.0, response)
        profiling_str = result.split("_profiling: ", 1)[1]
        profiling = json.loads(profiling_str)
        assert "optimization_hints" in profiling

    def test_none_response_raises(self):
        """None response triggers TypeError in the fallback branch (None + str)."""
        query = "ВЫБРАТЬ Ссылка ИЗ Справочник.Номенклатура ГДЕ Ссылка = &Ссылка"
        # json.loads(None) raises TypeError which is caught, but then
        # response_text + "..." fails because NoneType + str is not supported.
        import pytest
        with pytest.raises(TypeError):
            self.p.format_profiling_result(query, 50.0, None)


# ---------------------------------------------------------------------------
# Integration: record + get_stats
# ---------------------------------------------------------------------------

class TestRecordAndStats:

    def test_stats_reflect_recorded_data(self):
        p = QueryProfiler()
        p.record("q1", 100.0, True)
        p.record("q2", 6000.0, False)
        p.record("q3", 200.0, True)
        stats = p.get_stats()
        assert stats["total_queries"] == 3
        assert stats["error_count"] == 1
        assert stats["slow_queries_over_5s"] == 1
        assert stats["max_ms"] == 6000.0
        assert stats["min_ms"] == 100.0

    def test_stats_after_history_overflow(self):
        p = QueryProfiler(history_size=2)
        p.record("q1", 100.0, True)
        p.record("q2", 200.0, True)
        p.record("q3", 300.0, True)
        stats = p.get_stats()
        # Only q2 and q3 remain
        assert stats["total_queries"] == 2
        assert stats["min_ms"] == 200.0
        assert stats["max_ms"] == 300.0

    def test_disabled_profiler_empty_stats(self):
        p = QueryProfiler()
        p.enabled = False
        p.record("q1", 100.0, True)
        p.record("q2", 200.0, False)
        stats = p.get_stats()
        assert stats["total_queries"] == 0

    def test_re_enable_profiler(self):
        p = QueryProfiler()
        p.enabled = False
        p.record("ignored", 100.0, True)
        p.enabled = True
        p.record("counted", 200.0, True)
        stats = p.get_stats()
        assert stats["total_queries"] == 1
        assert stats["avg_ms"] == 200.0
