"""grayroll-04 失败测甲：已挂互斥人群 A 的主体再入 B，仍写正式成员行（须先见红）。

口径：甲路径 —— 第二互斥挂靠正式成员册零增、拒写。
夹具：fixtures 中 s-dual 已在 cohort 4（互斥组 mx-dual 甲册）。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import db
from app import app


def _h(client):
    t = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def _cohort_state(cohort_id: int):
    with db.connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT id, subject_key FROM cohort_members WHERE cohort_id=? ORDER BY id",
                (cohort_id,),
            ).fetchall()
        ]
        count = conn.execute("SELECT member_count FROM cohorts WHERE id=?", (cohort_id,)).fetchone()[
            "member_count"
        ]
    return rows, count


def test_second_mutex_cohort_rejected_with_zero_official_increment():
    with TestClient(app) as client:
        h = _h(client)
        # 前置：主体确已挂在甲册 A
        rows_a, _ = _cohort_state(4)
        assert any(r["subject_key"] == "s-dual" for r in rows_a)
        rows_b_before, count_b_before = _cohort_state(5)
        assert all(r["subject_key"] != "s-dual" for r in rows_b_before)

        # 再入互斥人群 B（乙册）：甲路径必须拒写，且正式成员册零增
        r = client.post("/api/cohorts/5/members", headers=h, json={"subject_key": "s-dual"})
        assert r.status_code == 409, r.text
        assert "互斥" in r.text

        rows_b_after, count_b_after = _cohort_state(5)
        assert all(row["subject_key"] != "s-dual" for row in rows_b_after)
        assert count_b_after == count_b_before
        # 甲册不受影响
        rows_a_after, _ = _cohort_state(4)
        assert any(row["subject_key"] == "s-dual" for row in rows_a_after)

        # 拒写留痕：第二挂拒写痕写入，非静默吞
        with db.connect() as conn:
            rejects = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM mutex_rejections WHERE subject_key='s-dual' ORDER BY id DESC"
                ).fetchall()
            ]
        assert rejects, "第二挂拒写未留痕"
        assert rejects[0]["cohort_id"] == 5
        assert rejects[0]["mutex_group"] == "mx-dual"


def test_divergent_path_recorded_and_rejected():
    """乙路径/折中一律记偏航并拒写，正式成员册零增。"""
    with TestClient(app) as client:
        h = _h(client)
        before, count_before = _cohort_state(5)
        r = client.post(
            "/api/cohorts/5/members",
            headers=h,
            json={"subject_key": "s-fresh", "path": "shadow"},
        )
        assert r.status_code == 409, r.text
        assert "偏航" in r.text
        after, count_after = _cohort_state(5)
        assert all(row["subject_key"] != "s-fresh" for row in after)
        assert count_after == count_before
        with db.connect() as conn:
            div = conn.execute(
                "SELECT * FROM policy_divergences WHERE requested_path='shadow' ORDER BY id DESC"
            ).fetchone()
        assert div is not None, "偏航未留痕"
