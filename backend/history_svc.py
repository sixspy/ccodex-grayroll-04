"""变更历史：争用核销与命运取舍分两段。"""
from __future__ import annotations

from fastapi import APIRouter, Header

import cohort_source
from auth import current_user
from db import connect

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def list_history(authorization: str | None = Header(default=None), limit: int = 100):
    current_user(authorization)
    with connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT h.*, f.key AS flag_key, e.code AS env_code
                FROM change_history h
                LEFT JOIN flags f ON f.id=h.flag_id
                LEFT JOIN environments e ON e.id=h.env_id
                ORDER BY h.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    return {"items": rows}


@router.get("/mutex-timeline")
def mutex_timeline(authorization: str | None = Header(default=None), limit: int = 60):
    """互斥第二挂两段式时间线。

    第一段「争用核销」：拒写痕 + 人群锁争用痕（败方只留痕，正式区零改）。
    第二段「命运取舍」：偏离甲路径的偏航记录（一律拒写，取向已定）。
    """
    current_user(authorization)
    with connect() as conn:
        rejects = cohort_source.mutex_rejections(conn, limit)
        contention = cohort_source.contention_marks(conn, limit)
        divergences = cohort_source.policy_divergences(conn, limit)
        conflicts = cohort_source.mutex_conflicts(conn)
    return {
        "phase_one": {"rejects": rejects, "contention": contention},
        "phase_two": {"divergences": divergences},
        "open_conflicts": conflicts,
        # 兼容旧读法
        "rejects": rejects,
        "divergences": divergences,
    }
