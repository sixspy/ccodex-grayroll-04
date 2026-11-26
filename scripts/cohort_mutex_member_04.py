"""grayroll-04 争用复现：两路并发双请求打同主体人群写口。

用法（后端已启动或由脚本自起 TestClient）：
    python scripts/cohort_mutex_member_04.py

判定：
  - 同主体「两路同时加入同一互斥册」：至多一路成功，落库恰一行（禁双成）；
  - 同主体「先入甲册、两路并发再入乙册」：两路都 409（互斥拒写），正式成员册零增；
  - 同主体人群锁已被另一会话持有：两路都 409，只记争用痕，败方零正式改。
退出码 0 表示符合预期，1 表示失败（无锁双成 / 正式册被增）。
"""
from __future__ import annotations

import json
import sys
import threading
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# 独立单文件库，避免污染 data/app.db
_TMP = tempfile.mkdtemp(prefix="cohort_mutex_member_04_")

import db  # noqa: E402

db.DATA = Path(_TMP)
db.DB_PATH = Path(_TMP) / "app.db"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

MUTEX_A = 4
MUTEX_B = 5


def _token(client):
    r = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _members(subject: str):
    with db.connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT cohort_id FROM cohort_members WHERE subject_key=? ORDER BY id", (subject,)
            ).fetchall()
        ]
    return [r["cohort_id"] for r in rows]


def _race(add_targets):
    """两路线程同时 POST 加入；返回各自状态码。"""
    with TestClient(app) as client:
        h = _token(client)

        def hit(cohort_id):
            client.post(f"/api/cohorts/{cohort_id}/members", headers=h, json={"subject_key": "s-race"})

        results = []

        def worker(cohort_id):
            r = client.post(
                f"/api/cohorts/{cohort_id}/members",
                headers=h,
                json={"subject_key": "s-race"},
            )
            results.append(r.status_code)

        threads = [threading.Thread(target=worker, args=(cid,)) for cid in add_targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return sorted(results)


def scenario_same_book() -> bool:
    codes = _race([MUTEX_A, MUTEX_A])
    books = _members("s-race")
    # 同册并发：至多一路成功（禁双成），落库恰一行；另一路 409 锁争用或 400 已存在均可。
    ok = codes.count(200) == 1 and books == [MUTEX_A]
    print(json.dumps({"scenario": "same_book", "codes": codes, "books": books, "ok": ok}, ensure_ascii=False))
    return ok


def scenario_cross_book() -> bool:
    # s-dual 已在甲册 A；两路并发再入乙册 B，均应互斥拒写。
    with TestClient(app) as client:
        h = _token(client)

        results = []

        def worker(_):
            r = client.post(
                f"/api/cohorts/{MUTEX_B}/members",
                headers=h,
                json={"subject_key": "s-dual"},
            )
            results.append(r.status_code)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    books = _members("s-dual")
    ok = sorted(results) == [409, 409] and books == [MUTEX_A]
    print(json.dumps({"scenario": "cross_book", "codes": sorted(results), "books": books, "ok": ok}, ensure_ascii=False))
    return ok


def scenario_preheld_lock() -> bool:
    """同主体人群锁被另一会话持有：两路并发双请求都只记争用痕，正式区零改。"""
    subject = "s-locked"
    key = f"cohort-subject:{subject}"
    with TestClient(app) as client:
        h = _token(client)
        with db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO row_locks(lock_key, holder, expires_at) VALUES(?,?,?)",
                (key, "session-b", time.time() + 120),
            )
            conn.commit()

        results = []

        def worker(_):
            r = client.post(
                f"/api/cohorts/{MUTEX_A}/members",
                headers=h,
                json={"subject_key": subject},
            )
            results.append(r.status_code)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        with db.connect() as conn:
            books = [
                dict(r)["cohort_id"]
                for r in conn.execute(
                    "SELECT cohort_id FROM cohort_members WHERE subject_key=?", (subject,)
                ).fetchall()
            ]
            marks = conn.execute(
                "SELECT loser, winner FROM contention_marks WHERE lock_key=?", (key,)
            ).fetchall()
            live = conn.execute("SELECT holder FROM row_locks WHERE lock_key=?", (key,)).fetchone()
    ok = (
        sorted(results) == [409, 409]
        and books == []
        and len(marks) >= 1
        and all(m["winner"] == "session-b" for m in marks)
        and live is not None
        and live["holder"] == "session-b"
    )
    print(
        json.dumps(
            {
                "scenario": "preheld_lock",
                "codes": sorted(results),
                "books": books,
                "contention_marks": len(marks),
                "ok": ok,
            },
            ensure_ascii=False,
        )
    )
    return ok


def main() -> int:
    db.init_db()
    ok_same = scenario_same_book()
    ok_cross = scenario_cross_book()
    ok_lock = scenario_preheld_lock()
    all_ok = ok_same and ok_cross and ok_lock
    print(json.dumps({"all_ok": all_ok}, ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
