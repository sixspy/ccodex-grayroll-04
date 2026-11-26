"""grayroll-04 争用失败测：两路会话抢同主体人群锁，无锁双成（须先见红）。

以同主体人群锁被另一会话持有模拟并发抢写：
第二路写口必须 409、只记争用痕，败方零正式改（成员行/人数均不变）。
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

import db
from app import app


def _h(client):
    t = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def test_subject_cohort_lock_contention_loser_zero_official():
    subject = "s-race"
    key = f"cohort-subject:{subject}"
    with TestClient(app) as client:
        h = _h(client)
        with db.connect() as conn:
            now = time.time()
            conn.execute(
                "INSERT INTO row_locks(lock_key, holder, expires_at) VALUES(?,?,?)",
                (key, "session-b", now + 60),
            )
            before_members = conn.execute(
                "SELECT COUNT(*) c FROM cohort_members WHERE subject_key=?", (subject,)
            ).fetchone()["c"]
            before_count = conn.execute("SELECT member_count FROM cohorts WHERE id=4").fetchone()[
                "member_count"
            ]
            conn.commit()

        r = client.post("/api/cohorts/4/members", headers=h, json={"subject_key": subject})
        assert r.status_code == 409, r.text

        with db.connect() as conn:
            after_members = conn.execute(
                "SELECT COUNT(*) c FROM cohort_members WHERE subject_key=?", (subject,)
            ).fetchone()["c"]
            after_count = conn.execute("SELECT member_count FROM cohorts WHERE id=4").fetchone()[
                "member_count"
            ]
            mark = conn.execute(
                "SELECT * FROM contention_marks WHERE lock_key=? ORDER BY id DESC", (key,)
            ).fetchone()
            live = conn.execute("SELECT * FROM row_locks WHERE lock_key=?", (key,)).fetchone()
        # 败方零正式改
        assert after_members == before_members
        assert after_count == before_count
        assert live is not None and live["holder"] == "session-b"
        # 败方只记争用痕
        assert mark is not None, "未记争用痕"
        assert mark["loser"] == "admin"
        assert mark["winner"] == "session-b"
