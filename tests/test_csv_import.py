"""
Unit tests for CSV import utilities.

Tests CSV parsing logic in isolation — no DB, no Qt required.
"""
import csv
import io


# ── Helpers that mirror the import logic in csv_import.py ─────────────────────

def parse_chats_csv(content: str) -> list[dict]:
    """Parse a chats CSV and return normalised rows."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for i, row in enumerate(reader, start=2):  # row 1 is header
        chat_id_raw = row.get("chat_id", "").strip()
        if not chat_id_raw:
            continue
        try:
            chat_id = int(chat_id_raw)
        except ValueError:
            continue
        rows.append({
            "chat_id":   chat_id,
            "chat_name": row.get("chat_name", "").strip() or None,
            "chat_type": row.get("chat_type", "").strip().lower() or "user",
            "enabled":   row.get("enabled", "true").strip().lower() not in ("false", "0", "no"),
        })
    return rows


def parse_messages_csv(content: str) -> list[dict]:
    """Parse a messages CSV and return normalised rows."""
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        title = row.get("title", "").strip()
        text  = row.get("text", "").strip()
        if not title or not text:
            continue
        rows.append({
            "title":      title,
            "text":       text,
            "media_path": row.get("media_path", "").strip() or None,
        })
    return rows


# ── Tests ──────────────────────────────────────────────────────────────────────

CHATS_CSV_VALID = """\
chat_id,chat_name,chat_type,enabled
-1001234567890,My Group,group,true
-1009876543210,My Channel,channel,true
777000,Telegram,bot,false
123456789,John Doe,user,true
"""

MESSAGES_CSV_VALID = """\
title,text,media_path
Приветствие,"Добро пожаловать!",""
Акция,"Скидка 50%!",/path/to/banner.jpg
"""


class TestChatsCsv:
    def test_parses_all_valid_rows(self) -> None:
        rows = parse_chats_csv(CHATS_CSV_VALID)
        assert len(rows) == 4

    def test_chat_id_is_int(self) -> None:
        rows = parse_chats_csv(CHATS_CSV_VALID)
        assert all(isinstance(r["chat_id"], int) for r in rows)

    def test_negative_chat_id(self) -> None:
        rows = parse_chats_csv(CHATS_CSV_VALID)
        assert rows[0]["chat_id"] == -1001234567890

    def test_enabled_false(self) -> None:
        rows = parse_chats_csv(CHATS_CSV_VALID)
        bot_row = next(r for r in rows if r["chat_type"] == "bot")
        assert bot_row["enabled"] is False

    def test_enabled_true(self) -> None:
        rows = parse_chats_csv(CHATS_CSV_VALID)
        group_row = next(r for r in rows if r["chat_type"] == "group")
        assert group_row["enabled"] is True

    def test_skips_invalid_chat_id(self) -> None:
        csv_bad = "chat_id,chat_name\nnot_a_number,Bad\n999,Good\n"
        rows = parse_chats_csv(csv_bad)
        assert len(rows) == 1
        assert rows[0]["chat_id"] == 999

    def test_skips_empty_chat_id(self) -> None:
        csv_empty = "chat_id,chat_name\n,Empty\n888,OK\n"
        rows = parse_chats_csv(csv_empty)
        assert len(rows) == 1

    def test_missing_optional_columns_defaults(self) -> None:
        csv_minimal = "chat_id\n12345\n"
        rows = parse_chats_csv(csv_minimal)
        assert len(rows) == 1
        assert rows[0]["chat_type"] == "user"
        assert rows[0]["enabled"] is True
        assert rows[0]["chat_name"] is None

    def test_empty_csv_returns_empty(self) -> None:
        assert parse_chats_csv("chat_id,chat_name\n") == []

    def test_type_normalised_lowercase(self) -> None:
        csv_upper = "chat_id,chat_type\n111,GROUP\n"
        rows = parse_chats_csv(csv_upper)
        assert rows[0]["chat_type"] == "group"


class TestMessagesCsv:
    def test_parses_all_valid_rows(self) -> None:
        rows = parse_messages_csv(MESSAGES_CSV_VALID)
        assert len(rows) == 2

    def test_title_and_text(self) -> None:
        rows = parse_messages_csv(MESSAGES_CSV_VALID)
        assert rows[0]["title"] == "Приветствие"
        assert rows[0]["text"] == "Добро пожаловать!"

    def test_empty_media_path_is_none(self) -> None:
        rows = parse_messages_csv(MESSAGES_CSV_VALID)
        assert rows[0]["media_path"] is None

    def test_non_empty_media_path(self) -> None:
        rows = parse_messages_csv(MESSAGES_CSV_VALID)
        assert rows[1]["media_path"] == "/path/to/banner.jpg"

    def test_skips_missing_title(self) -> None:
        csv_bad = "title,text\n,Some text\nGood,Content\n"
        rows = parse_messages_csv(csv_bad)
        assert len(rows) == 1
        assert rows[0]["title"] == "Good"

    def test_skips_missing_text(self) -> None:
        csv_bad = "title,text\nNo text,\nWith text,Hello\n"
        rows = parse_messages_csv(csv_bad)
        assert len(rows) == 1

    def test_unicode_content(self) -> None:
        csv_unicode = 'title,text\n"Тест 🎉","Привет мир 🌍"\n'
        rows = parse_messages_csv(csv_unicode)
        assert len(rows) == 1
        assert "🎉" in rows[0]["title"]

    def test_empty_csv_returns_empty(self) -> None:
        assert parse_messages_csv("title,text\n") == []