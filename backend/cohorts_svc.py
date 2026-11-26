"""人群圈选：互斥人群第二挂只认甲路径，正式成员册零增拒写。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from audit_svc import write_audit, write_history
from auth import current_user, require_writer
from db import connect
from locks import acquire, release
from policies import (
    MUTEX_COHORT_PATH,
    MUTEX_DIVERGENCE_MSG,
    MUTEX_REJECT_MSG,
    find_conflicting_membership,
    subject_cohort_lock_key,
)
from validators import require_str

router = APIRouter(prefix="/api/cohorts", tags=["cohorts"])


class CohortIn(BaseModel):
    code: str
    title: str
    note: str = ""
    mutex_group: str = ""


class MemberIn(BaseModel):
    subject_key: str
    # 拍板口径：只认 official（甲）。显式请求 shadow / hybrid 等一律记偏航并拒写。
    path: str = MUTEX_COHORT_PATH


def _record_divergence(conn, scope: str, requested: str, actor: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO policy_divergences(scope, requested_path, actor, detail, created_at) "
        "VALUES(?,?,?,?,?)",
        (scope, requested, actor, detail, time.time()),
    )


@router.get("")
def list_cohorts(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM cohorts ORDER BY id").fetchall()]
    return {"items": rows}


@router.get("/{cohort_id}/members")
def list_members(cohort_id: int, authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM cohort_members WHERE cohort_id=? ORDER BY id", (cohort_id,)
            ).fetchall()
        ]
    return {"items": rows}


@router.get("/mutex/rejections")
def list_mutex_rejections(authorization: str | None = Header(default=None), limit: int = 40):
    """互斥第二挂拒写痕（甲路径零增）。"""
    current_user(authorization)
    with connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT mr.*, c.code AS cohort_code, c.title AS cohort_title
                FROM mutex_rejections mr
                LEFT JOIN cohorts c ON c.id=mr.cohort_id
                ORDER BY mr.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    return {"items": rows}


@router.get("/mutex/divergences")
def list_divergences(authorization: str | None = Header(default=None), limit: int = 40):
    """偏航取舍记录：请求非甲路径被拒写的痕迹。"""
    current_user(authorization)
    with connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM policy_divergences ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]
    return {"items": rows}


@router.post("")
def create_cohort(body: CohortIn, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    code = require_str(body.code, "人群码", 2)
    title = require_str(body.title, "标题", 2)
    mutex_group = (body.mutex_group or "").strip()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM cohorts WHERE code=?", (code,)).fetchone():
            raise HTTPException(400, detail="人群码已存在")
        cur = conn.execute(
            "INSERT INTO cohorts(code, title, member_count, note, mutex_group) VALUES(?,?,0,?,?)",
            (code, title, body.note or "", mutex_group),
        )
        cid = cur.lastrowid
        write_audit(conn, user["username"], "create_cohort", "cohort", cid, code)
        conn.commit()
    return {"id": cid, "code": code, "mutex_group": mutex_group}


@router.post("/{cohort_id}/members")
def add_member(cohort_id: int, body: MemberIn, authorization: str | None = Header(default=None)):
    user = current_user(authorization)
    require_writer(user)
    sk = require_str(body.subject_key, "主体键", 2)
    requested_path = (body.path or MUTEX_COHORT_PATH).strip()

    if requested_path != MUTEX_COHORT_PATH:
        with connect() as conn:
            _record_divergence(
                conn, f"cohort_member:{cohort_id}", requested_path, user["username"], MUTEX_DIVERGENCE_MSG
            )
            write_history(
                conn,
                user["username"],
                "cohort_path_divergence",
                f"人群{cohort_id} 加入 {sk} 请求路径 {requested_path} 偏航拒写",
            )
            conn.commit()
        raise HTTPException(409, detail=MUTEX_DIVERGENCE_MSG)

    key = subject_cohort_lock_key(sk)
    with connect() as conn:
        acquire(conn, key, user["username"])
        try:
            if not conn.execute("SELECT 1 FROM cohorts WHERE id=?", (cohort_id,)).fetchone():
                raise HTTPException(404, detail="人群不存在")
            if conn.execute(
                "SELECT 1 FROM cohort_members WHERE cohort_id=? AND subject_key=?", (cohort_id, sk)
            ).fetchone():
                raise HTTPException(400, detail="主体已在人群中")
            conflict = find_conflicting_membership(conn, sk, cohort_id)
            if conflict:
                # 甲路径：第二互斥挂靠拒写，正式成员册零增，只留拒写痕。
                conn.execute(
                    "INSERT INTO mutex_rejections(subject_key, cohort_id, mutex_group, attempted_by, created_at) "
                    "VALUES(?,?,?,?,?)",
                    (sk, cohort_id, conflict["mutex_group"], user["username"], time.time()),
                )
                write_history(
                    conn,
                    user["username"],
                    "cohort_mutex_reject",
                    f"互斥组 {conflict['mutex_group']}：{sk} 已挂 {conflict['cohort_code']}，{cohort_id} 第二挂拒写",
                )
                write_audit(
                    conn, user["username"], "cohort_mutex_reject", "cohort_member", None, sk
                )
                conn.commit()
                raise HTTPException(409, detail=MUTEX_REJECT_MSG)
            cur = conn.execute(
                "INSERT INTO cohort_members(cohort_id, subject_key) VALUES(?,?)", (cohort_id, sk)
            )
            conn.execute(
                "UPDATE cohorts SET member_count = member_count + 1 WHERE id=?", (cohort_id,)
            )
            write_history(conn, user["username"], "cohort_add", f"人群{cohort_id} 加入 {sk}")
            write_audit(conn, user["username"], "cohort_add", "cohort_member", cur.lastrowid, sk)
            conn.commit()
            return {"cohort_id": cohort_id, "subject_key": sk, "mode": "official"}
        finally:
            release(conn, key, user["username"])
            conn.commit()
