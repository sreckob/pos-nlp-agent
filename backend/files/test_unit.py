"""
Unit tests for core agent logic — no DB or LLM calls required.

Run from backend/files/:
    pip install pytest
    pytest test_unit.py -v
"""

import json
import sys
import os

import pytest

# ── Make imports work without a running app ───────────────────
sys.path.insert(0, os.path.dirname(__file__))

from executor import is_safe_sql
from agent import (
    parse_json_response,
    safe_parse,
    is_switch_confirmation,
    is_menu_request,
    _is_short_reply,
)


# ── is_safe_sql ───────────────────────────────────────────────

class TestIsSafeSql:
    def test_select_is_safe(self):
        assert is_safe_sql("SELECT * FROM transactions WHERE status = 'APPROVED'")

    def test_select_with_join_is_safe(self):
        assert is_safe_sql(
            "SELECT t1.transaction_id FROM transactions t1 "
            "JOIN transactions t2 ON t1.pan_masked = t2.pan_masked"
        )

    def test_delete_is_blocked(self):
        assert not is_safe_sql("DELETE FROM transactions WHERE 1=1")

    def test_drop_is_blocked(self):
        assert not is_safe_sql("DROP TABLE transactions")

    def test_update_is_blocked(self):
        assert not is_safe_sql("UPDATE transactions SET status='APPROVED' WHERE 1=1")

    def test_insert_is_blocked(self):
        assert not is_safe_sql("INSERT INTO transactions (transaction_id) VALUES ('fake')")

    def test_truncate_is_blocked(self):
        assert not is_safe_sql("TRUNCATE TABLE loyalty_accounts")

    def test_inline_injection_is_blocked(self):
        # SQL injection appended after a semicolon
        assert not is_safe_sql(
            "SELECT * FROM transactions WHERE status='APPROVED'; DROP TABLE transactions;"
        )

    def test_case_insensitive_block(self):
        assert not is_safe_sql("delete from transactions where 1=1")

    def test_alter_is_blocked(self):
        assert not is_safe_sql("ALTER TABLE transactions ADD COLUMN malicious TEXT")


# ── parse_json_response ───────────────────────────────────────

class TestParseJsonResponse:
    def test_plain_json(self):
        raw = '{"sql": "SELECT 1", "answer": "done"}'
        result = parse_json_response(raw)
        assert result["sql"] == "SELECT 1"
        assert result["answer"] == "done"

    def test_json_with_leading_prose(self):
        raw = 'Here is your answer: {"sql": "SELECT 1", "answer": "done"}'
        result = parse_json_response(raw)
        assert result["sql"] == "SELECT 1"

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"sql": "SELECT 1", "answer": "done"}\n```'
        result = parse_json_response(raw)
        assert result["sql"] == "SELECT 1"

    def test_no_json_raises(self):
        with pytest.raises((ValueError, Exception)):
            parse_json_response("This has no JSON object at all.")

    def test_nested_json(self):
        raw = '{"sql": "SELECT * FROM t WHERE x = 1", "answer": "ok", "export_requested": false}'
        result = parse_json_response(raw)
        assert result["export_requested"] is False


# ── safe_parse ────────────────────────────────────────────────

class TestSafeParse:
    def test_valid_json_returns_parsed(self):
        raw = '{"sql": "SELECT 1", "answer": "Here are your results"}'
        parsed, answer, err = safe_parse(raw)
        assert parsed is not None
        assert answer == "Here are your results"
        assert err is None

    def test_invalid_json_returns_none_parsed(self):
        raw = "Sorry, I cannot help with that."
        parsed, answer, err = safe_parse(raw)
        assert parsed is None
        assert err == "no_sql"

    def test_sql_leaking_as_plain_text_is_replaced(self):
        # If Claude returns raw SQL outside JSON, safe_parse should NOT pass it through
        raw = "SELECT * FROM transactions WHERE status = 'APPROVED'"
        parsed, answer, err = safe_parse(raw)
        assert "SELECT" not in answer
        assert err == "no_sql"

    def test_empty_response_gives_fallback(self):
        parsed, answer, err = safe_parse("")
        assert parsed is None
        assert len(answer) > 0  # should give a fallback message
        assert err == "no_sql"


# ── is_switch_confirmation ────────────────────────────────────

class TestIsSwitchConfirmation:
    def test_yes_confirms(self):
        assert is_switch_confirmation("yes")

    def test_da_confirms(self):
        assert is_switch_confirmation("da")

    def test_ok_confirms(self):
        assert is_switch_confirmation("ok")

    def test_no_does_not_confirm(self):
        assert not is_switch_confirmation("no")

    def test_random_text_does_not_confirm(self):
        assert not is_switch_confirmation("show me my transactions")

    def test_case_insensitive(self):
        assert is_switch_confirmation("YES")
        assert is_switch_confirmation("Da")


# ── is_menu_request ───────────────────────────────────────────

class TestIsMenuRequest:
    def test_menu_triggers_reset(self):
        assert is_menu_request("menu")

    def test_meni_triggers_reset(self):
        assert is_menu_request("meni")

    def test_back_triggers_reset(self):
        assert is_menu_request("back")

    def test_normal_message_does_not_trigger(self):
        assert not is_menu_request("show my transactions")


# ── _is_short_reply ───────────────────────────────────────────

class TestIsShortReply:
    def test_card_digits_are_short_reply(self):
        assert _is_short_reply("4242")

    def test_yes_is_short_reply(self):
        assert _is_short_reply("yes")

    def test_da_is_short_reply(self):
        assert _is_short_reply("da")

    def test_long_message_is_not_short_reply(self):
        assert not _is_short_reply("Show me all my declined transactions from last month")

    def test_amount_is_short_reply(self):
        assert _is_short_reply("3240.50")

    def test_normal_query_is_not_short_reply(self):
        assert not _is_short_reply("Why was my payment declined at Maxi yesterday?")
