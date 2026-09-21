from __future__ import annotations

from hwpx.document import HwpxDocument


def test_table_treat_as_char_is_explicit_and_persists() -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(2, 1)
        assert table.treat_as_char is True
        original_height = table.height
        table.set_treat_as_char(False)
        assert table.treat_as_char is False
        reopened = HwpxDocument.open(document.to_bytes())
        try:
            assert reopened.tables.all[0].treat_as_char is False
            assert reopened.tables.all[0].height == original_height
        finally:
            reopened.close()
