"""Tests for _validate_query_static and _add_limit_zero."""

import sys
from pathlib import Path

# Allow importing gateway package from the tests directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.mcp_server import _add_limit_zero, _validate_query_static


# ---------------------------------------------------------------------------
# _validate_query_static
# ---------------------------------------------------------------------------

class TestValidateQueryStatic:

    def test_empty_query(self):
        valid, errors, warnings = _validate_query_static("")
        assert not valid
        assert any("пуст" in e.lower() for e in errors)

    def test_whitespace_only(self):
        valid, errors, _ = _validate_query_static("   \n\t  ")
        assert not valid

    def test_missing_select(self):
        valid, errors, _ = _validate_query_static("ИЗ Справочник.Контрагенты")
        assert not valid
        assert any("ВЫБРАТЬ" in e for e in errors)

    def test_valid_simple_query(self):
        q = "ВЫБРАТЬ Ссылка ИЗ Справочник.Контрагенты"
        valid, errors, warnings = _validate_query_static(q)
        assert valid
        assert errors == []

    def test_unbalanced_open_paren(self):
        q = "ВЫБРАТЬ Ссылка ИЗ Справочник.Контрагенты ГДЕ (Ссылка = &Ссылка"
        valid, errors, _ = _validate_query_static(q)
        assert not valid
        assert any("незакрытых" in e.lower() or "скобк" in e.lower() for e in errors)

    def test_unbalanced_close_paren(self):
        q = "ВЫБРАТЬ Ссылка ИЗ Справочник.Контрагенты ГДЕ Ссылка = &Ссылка)"
        valid, errors, _ = _validate_query_static(q)
        assert not valid
        assert any("закрывающая" in e.lower() for e in errors)

    def test_balanced_parens(self):
        q = "ВЫБРАТЬ Ссылка ИЗ Справочник.Контрагенты ГДЕ (Ссылка В (ВЫБРАТЬ Ссылка ИЗ Справочник.Контрагенты))"
        valid, errors, _ = _validate_query_static(q)
        assert valid

    def test_parens_in_quotes_ignored(self):
        q = 'ВЫБРАТЬ "(((" КАК Поле ИЗ Справочник.Контрагенты'
        valid, errors, _ = _validate_query_static(q)
        assert valid

    def test_select_star_warning(self):
        q = "ВЫБРАТЬ * ИЗ Справочник.Контрагенты"
        valid, errors, warnings = _validate_query_static(q)
        assert valid
        assert any("*" in w for w in warnings)

    def test_select_distinct_star_warning(self):
        q = "ВЫБРАТЬ РАЗЛИЧНЫЕ * ИЗ Справочник.Контрагенты"
        valid, errors, warnings = _validate_query_static(q)
        assert valid
        assert any("*" in w for w in warnings)

    def test_virtual_table_where_warning(self):
        q = (
            "ВЫБРАТЬ Остатки.Номенклатура "
            "ИЗ РегистрНакопления.ТоварыНаСкладах.Остатки) КАК Остатки "
            "ГДЕ Остатки.Склад = &Склад"
        )
        valid, errors, warnings = _validate_query_static(q)
        assert any("виртуальн" in w.lower() for w in warnings)

    def test_comment_stripped(self):
        q = "// Комментарий\nВЫБРАТЬ Ссылка ИЗ Справочник.Контрагенты"
        valid, errors, _ = _validate_query_static(q)
        assert valid

    def test_batch_query(self):
        q = (
            "ВЫБРАТЬ Ссылка ПОМЕСТИТЬ вт ИЗ Справочник.Контрагенты;\n"
            "ВЫБРАТЬ * ИЗ вт"
        )
        valid, errors, warnings = _validate_query_static(q)
        assert valid


# ---------------------------------------------------------------------------
# _add_limit_zero
# ---------------------------------------------------------------------------

class TestAddLimitZero:

    def test_simple_select(self):
        q = "ВЫБРАТЬ Код, Наименование ИЗ Справочник.Контрагенты"
        result = _add_limit_zero(q)
        assert "ПЕРВЫЕ 0" in result
        assert "Код" in result

    def test_already_has_top(self):
        q = "ВЫБРАТЬ ПЕРВЫЕ 100 Код ИЗ Справочник.Контрагенты"
        result = _add_limit_zero(q)
        assert "ПЕРВЫЕ 0" in result
        assert "ПЕРВЫЕ 100" not in result

    def test_distinct(self):
        q = "ВЫБРАТЬ РАЗЛИЧНЫЕ Контрагент ИЗ Документ.Реализация"
        result = _add_limit_zero(q)
        assert "РАЗЛИЧНЫЕ" in result
        assert "ПЕРВЫЕ 0" in result
        # ПЕРВЫЕ 0 should come after РАЗЛИЧНЫЕ
        idx_distinct = result.upper().index("РАЗЛИЧНЫЕ")
        idx_top = result.upper().index("ПЕРВЫЕ 0")
        assert idx_top > idx_distinct

    def test_distinct_with_top(self):
        q = "ВЫБРАТЬ РАЗЛИЧНЫЕ ПЕРВЫЕ 50 Контрагент ИЗ Документ.Реализация"
        result = _add_limit_zero(q)
        assert "РАЗЛИЧНЫЕ" in result
        assert "ПЕРВЫЕ 0" in result
        assert "ПЕРВЫЕ 50" not in result

    def test_no_select_returns_unchanged(self):
        q = "ИЗ Справочник.Контрагенты"
        result = _add_limit_zero(q)
        assert result == q

    def test_multiline(self):
        q = "ВЫБРАТЬ\n\tКод,\n\tНаименование\nИЗ\n\tСправочник.Контрагенты"
        result = _add_limit_zero(q)
        assert "ПЕРВЫЕ 0" in result

    def test_preserves_fields(self):
        q = "ВЫБРАТЬ Код, Наименование, Артикул ИЗ Справочник.Номенклатура"
        result = _add_limit_zero(q)
        assert "Код" in result
        assert "Наименование" in result
        assert "Артикул" in result

    def test_case_insensitive(self):
        q = "Выбрать Код Из Справочник.Контрагенты"
        result = _add_limit_zero(q)
        assert "ПЕРВЫЕ 0" in result
