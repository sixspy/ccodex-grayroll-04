"""grayroll-04：每个用例独立单文件库，避免既有 data/app.db 互相污染。

单文件库路径沿用 db.DB_PATH（sqlite 单文件），仅在本测试会话内改指向临时目录。
"""
from __future__ import annotations

import pytest

import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(db, "DATA", tmp_path)
    db.init_db()
    yield
