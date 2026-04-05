"""Tests for BSL search index."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.bsl_search import BslSearchIndex


def _create_bsl_tree(tmp_path: Path) -> None:
    """Create a minimal BSL file structure for testing."""
    module_dir = tmp_path / "CommonModules" / "ОбщегоНазначения" / "Ext"
    module_dir.mkdir(parents=True)
    (module_dir / "Module.bsl").write_text(
        '// Получает значения реквизитов объекта\n'
        '// Параметры:\n'
        '//   Ссылка - ЛюбаяСсылка\n'
        'Функция ЗначенияРеквизитовОбъекта(Ссылка, Реквизиты) Экспорт\n'
        '    Возврат Неопределено;\n'
        'КонецФункции\n'
        '\n'
        'Процедура СообщитьПользователю(Текст, Объект) Экспорт\n'
        'КонецПроцедуры\n'
        '\n'
        'Функция ВнутренняяФункция()\n'
        '    Возврат 1;\n'
        'КонецФункции\n',
        encoding="utf-8-sig",
    )

    doc_dir = tmp_path / "Documents" / "Реализация" / "Ext"
    doc_dir.mkdir(parents=True)
    (doc_dir / "ObjectModule.bsl").write_text(
        'Процедура ПередЗаписью(Отказ) Экспорт\n'
        'КонецПроцедуры\n',
        encoding="utf-8-sig",
    )


def test_build_index(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    result = idx.build_index(str(tmp_path))
    assert "4" in result  # 4 symbols
    assert idx.indexed
    assert idx.symbol_count == 4


def test_search_by_name(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("ЗначенияРеквизитовОбъекта")
    assert len(results) >= 1
    assert results[0]["name"] == "ЗначенияРеквизитовОбъекта"
    assert results[0]["export"] is True


def test_search_by_module(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("ОбщегоНазначения")
    assert len(results) >= 2  # Functions from that module


def test_search_export_only(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("Функция", export_only=True)
    # ВнутренняяФункция is NOT exported
    names = [r["name"] for r in results]
    assert "ВнутренняяФункция" not in names


def test_search_no_results(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("НесуществующаяФункция")
    assert results == []


def test_search_empty_index():
    idx = BslSearchIndex()
    assert idx.search("anything") == []


def test_module_name_derivation(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("ПередЗаписью")
    assert len(results) >= 1
    assert "Документ.Реализация" in results[0]["module"]
