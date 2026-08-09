"""Kiểm kho ký ức cá nhân hoá."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent.persona import PersonaStore  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    with PersonaStore(tmp_path / "certus.sqlite3") as persona:
        yield persona


# ─────────────────────────── vòng đời ───────────────────────────


def test_creates_the_database_file_and_its_parent_directory(tmp_path):
    path = tmp_path / "var" / "nested" / "certus.sqlite3"
    with PersonaStore(path):
        pass
    assert path.is_file()


def test_reopening_the_same_file_keeps_what_was_written(tmp_path):
    path = tmp_path / "certus.sqlite3"
    with PersonaStore(path) as first:
        first.record_lesson("u1", "shopcart", "thiếu test cho nhánh hết hạn")
    with PersonaStore(path) as second:
        assert second.lessons_for("u1", "shopcart") == ["thiếu test cho nhánh hết hạn"]


# ─────────────────────────── thói quen ───────────────────────────


def test_habits_are_scoped_to_the_user(store):
    store.record_habit("u1", "hay bỏ nhánh lỗi của hàm parse")
    store.record_habit("u2", "viết test rất dài, ít assertion độc lập")

    assert store.habits_for("u1") == ["hay bỏ nhánh lỗi của hàm parse"]
    assert store.habits_for("u2") == ["viết test rất dài, ít assertion độc lập"]


def test_habits_for_an_unknown_user_is_empty(store):
    assert store.habits_for("chua-ton-tai") == []


# ─────────────────────────── bài học ───────────────────────────


def test_lessons_are_scoped_to_the_user(store):
    store.record_lesson("u1", "acme-billing", "apply_discount thiếu test coupon hết hạn")
    store.record_lesson("u2", "shopcart", "hàm merge_cart chưa có test cho giỏ rỗng")

    assert store.lessons_for("u1", "acme-billing") == ["apply_discount thiếu test coupon hết hạn"]
    assert store.lessons_for("u2", "shopcart") == ["hàm merge_cart chưa có test cho giỏ rỗng"]


def test_lessons_come_back_newest_first(store):
    store.record_lesson("u1", "p", "bài học cũ")
    store.record_lesson("u1", "p", "bài học mới")
    assert store.lessons_for("u1", "p") == ["bài học mới", "bài học cũ"]


def test_lessons_respect_the_limit(store):
    for index in range(5):
        store.record_lesson("u1", "p", f"bài học {index}")
    assert len(store.lessons_for("u1", "p", limit=2)) == 2


def test_lessons_for_an_unknown_user_is_empty(store):
    assert store.lessons_for("chua-ton-tai", "p") == []


# ─────────────────────────── khối chữ cho prompt ───────────────────────────


def test_persona_block_is_empty_when_there_is_nothing_to_say(store):
    assert store.persona_block("u1", "shopcart") == ""


def test_persona_block_lists_habits_and_lessons(store):
    store.record_habit("u1", "hay bỏ nhánh lỗi")
    store.record_lesson("u1", "shopcart", "merge_cart chưa có test giỏ rỗng")

    block = store.persona_block("u1", "shopcart")

    assert "hay bỏ nhánh lỗi" in block
    assert "merge_cart chưa có test giỏ rỗng" in block
    assert block.startswith("Thói quen")


def test_persona_block_of_one_user_does_not_contain_another_users_memory(store):
    store.record_habit("u1", "thói quen của u1")
    store.record_lesson("u1", "p1", "bài học của u1")

    block = store.persona_block("u2")

    assert "u1" not in block
    assert block == ""
