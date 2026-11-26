"""行锁与争用痕（嵌进发布/熔断/人群主写路径）。

争用核销：败方只写 contention_marks，正式区零改。
锁定采用单条条件 UPSERT（rowcount 判定），避免「先查后写」双成都拿到锁。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Header, HTTPException

from auth import current_user
from db import connect

router = APIRouter(prefix="/api/locks", tags=["locks"])
TTL = 20.0


def _contention_detail(key: str) -> str:
    if key.startswith("cohort-subject:"):
        return "人群锁争用，请稍后重试"
    return "发布锁争用，请稍后重试"


def acquire(conn, key: str, holder: str) -> None:
    now = time.time()
    deadline = now + TTL
    cur = conn.execute(
        "INSERT INTO row_locks(lock_key, holder, expires_at) VALUES(?,?,?) "
        "ON CONFLICT(lock_key) DO UPDATE SET holder=excluded.holder, expires_at=excluded.expires_at "
        "WHERE row_locks.holder=excluded.holder OR row_locks.expires_at <= ?",
        (key, holder, deadline, now),
    )
    if cur.rowcount == 0:
        row = conn.execute("SELECT holder FROM row_locks WHERE lock_key=?", (key,)).fetchone()
        winner = row["holder"] if row else "unknown"
        conn.execute(
            "INSERT INTO contention_marks(lock_key, loser, winner, created_at) VALUES(?,?,?,?)",
            (key, holder, winner, now),
        )
        conn.commit()
        raise HTTPException(409, detail=_contention_detail(key))
    # 锁必须立即可见，否则跨连接会话看不到持有者。
    conn.commit()


def release(conn, key: str, holder: str) -> None:
    conn.execute("DELETE FROM row_locks WHERE lock_key=? AND holder=?", (key, holder))


@router.get("/contention")
def list_contention(authorization: str | None = Header(default=None), limit: int = 40):
    current_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM contention_marks ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"items": [dict(r) for r in rows]}
