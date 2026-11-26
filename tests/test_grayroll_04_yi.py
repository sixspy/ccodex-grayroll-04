"""grayroll-04 失败测乙：求值页把未升正的双挂当已合法命中（须先见红）。

场景：s-dual 正式挂在互斥 A（cohort 4），另有未升正的第二挂 B（cohort 5）。
规则引用 B 时，求值不得命中；引用 A 时命中，且与单一人群成员同源。
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

import db
from app import app


def _h(client):
    t = client.post("/api/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def test_evaluate_ignores_unpromoted_second_mutex_attachment():
    with TestClient(app) as client:
        h = _h(client)
        with db.connect() as conn:
            # 乙册 B 上出现未升正的第二挂（模拟旧写口留下的正式册双挂）
            conn.execute(
                "INSERT INTO cohort_members(cohort_id, subject_key) VALUES(5, 's-dual')"
            )
            # 规则引用乙册 B
            conn.execute(
                "INSERT INTO flag_rules(flag_id, env_id, kind, percent, cohort_id, version, official, updated_at) "
                "VALUES(3, 1, 'cohort', 0, 5, 1, 1, ?)",
                (time.time(),),
            )
            conn.commit()

        r = client.post(
            "/api/evaluate",
            headers=h,
            json={"flag_key": "feed.ranking_v2", "env_code": "dev", "subject_key": "s-dual"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # 未升正的第二挂不得当已合法命中
        assert body["cohort_hit"] is False, body
        assert body["enabled"] is False, body

        # 同一主体在唯一天然册 A 上仍应命中：求值与单一人群成员同源
        with db.connect() as conn:
            conn.execute(
                "UPDATE flag_rules SET cohort_id=4 WHERE flag_id=3 AND env_id=1"
            )
            conn.commit()
        r2 = client.post(
            "/api/evaluate",
            headers=h,
            json={"flag_key": "feed.ranking_v2", "env_code": "dev", "subject_key": "s-dual"},
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["cohort_hit"] is True, body2
        assert body2["enabled"] is True, body2
        assert body2.get("cohort_id") == 4, body2


def test_five_pages_share_mutex_cohort_source():
    """规则页/求值页/发布页/历史页/对比页与互斥人群成员同源。"""
    with TestClient(app) as client:
        h = _h(client)
        with db.connect() as conn:
            conn.execute("INSERT INTO cohort_members(cohort_id, subject_key) VALUES(5, 's-dual')")
            conn.execute(
                "INSERT INTO flag_rules(flag_id, env_id, kind, percent, cohort_id, version, official, updated_at) "
                "VALUES(3, 1, 'cohort', 0, 5, 1, 1, ?)",
                (time.time(),),
            )
            conn.commit()

        # 规则页：规则行带出人群码与互斥组
        rules = client.get("/api/rules", headers=h).json()["official"]
        rule = next(r for r in rules if r["flag_id"] == 3 and r["env_id"] == 1)
        assert rule["cohort_code"] == "mx_dual_b"
        assert rule["cohort_mutex_group"] == "mx-dual"

        # 求值页规则板：同样联查互斥组
        board = client.get("/api/evaluate/board", headers=h).json()["rules"]
        brow = next(r for r in board if r["flag_key"] == "feed.ranking_v2" and r["env_code"] == "dev")
        assert brow["cohort_code"] == "mx_dual_b"
        assert brow["cohort_mutex_group"] == "mx-dual"

        # 发布页：正式发布行联查当前正式规则的人群，与规则页同源
        rels = client.get("/api/releases", headers=h).json()["official"]
        rel = next(r for r in rels if r["flag_id"] == 1 and r["env_id"] == 3)
        assert rel["cohort_code"] == "beta_internal"

        # 对比页：矩阵单元格与双挂冲突同源
        m = client.get("/api/compare/matrix", headers=h).json()
        cell = next(
            c
            for row in m["matrix"]
            if row["flag_id"] == 3
            for c in row["cells"]
            if c["env_id"] == 1
        )
        assert cell["cohort_code"] == "mx_dual_b"
        assert cell["cohort_mutex_group"] == "mx-dual"
        conflicts = m["mutex_conflicts"]
        assert any(c["subject_key"] == "s-dual" and c["books"] == 2 for c in conflicts)

        # 历史页：争用核销与命运取舍分两段呈现，且含双挂冲突
        tl = client.get("/api/history/mutex-timeline", headers=h).json()
        assert "phase_one" in tl and "phase_two" in tl
        assert any(c["subject_key"] == "s-dual" for c in tl["open_conflicts"])
