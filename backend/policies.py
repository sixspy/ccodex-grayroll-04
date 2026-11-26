"""发布 / 熔断写路径策略与求值规则。"""
from __future__ import annotations

import hashlib

from fastapi import HTTPException

WRITE_OFFICIAL = "official"
WRITE_SHADOW = "shadow"

# grayroll-04 拍板：互斥人群第二挂只认甲路径 —— 正式成员册零增拒写。
# 乙路径（只落影子草案待裁决升正）本需求不启用；请求乙或其它折中一律记偏航并拒写。
MUTEX_COHORT_PATH = WRITE_OFFICIAL
MUTEX_REJECT_MSG = "主体已挂互斥人群同组另一册，第二挂拒写（正式成员册零增）"
MUTEX_DIVERGENCE_MSG = "互斥人群第二挂只认甲路径拒写；影子/折中路径偏航拒写"

H3_PATHS = {
    "release": {
        WRITE_OFFICIAL: "同事务写入正式生效配置并升版本，旧正式规则被新版本覆盖",
        WRITE_SHADOW: "只写影子发布草案；升正时原子写入正式规则与 releases，升正前正式区零改",
    },
    "kill": {
        WRITE_OFFICIAL: "同事务立即将开关置为熔断并写正式关闭规则",
        WRITE_SHADOW: "影子紧急草案确认后原子熔断正式配置",
    },
    "cohort_bind": {
        WRITE_OFFICIAL: "同事务写正式人群规则",
        WRITE_SHADOW: "影子绑定草案升正后落正式规则",
    },
}


def describe_path(kind: str, use_shadow: bool) -> str:
    bucket = H3_PATHS.get(kind, {})
    return bucket.get(WRITE_SHADOW if use_shadow else WRITE_OFFICIAL, "")


def assert_flag_publishable(status: str) -> None:
    if status in ("archived",):
        raise HTTPException(400, detail="已归档开关不可发布")


def assert_not_killed_or_allow_kill(status: str, for_kill: bool = False) -> None:
    if for_kill:
        if status == "archived":
            raise HTTPException(400, detail="已归档不可熔断")
        return
    if status == "killed":
        raise HTTPException(400, detail="已熔断，须先恢复再发布")


def subject_bucket(subject_key: str, salt: str = "") -> int:
    """稳定哈希到 0..99，用于百分比灰度。"""
    dig = hashlib.sha256(f"{salt}:{subject_key}".encode()).hexdigest()
    return int(dig[:8], 16) % 100


def eval_percent(subject_key: str, percent: int, flag_key: str) -> bool:
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    return subject_bucket(subject_key, flag_key) < percent


def combine_rule(kind: str, percent_hit: bool, cohort_hit: bool) -> bool:
    if kind == "percent":
        return percent_hit
    if kind == "cohort":
        return cohort_hit
    if kind == "percent_and_cohort":
        return percent_hit and cohort_hit
    return False


def subject_cohort_lock_key(subject_key: str) -> str:
    """同主体人群锁：互斥判定与成员落库须在此锁内串行。"""
    return f"cohort-subject:{subject_key}"


def find_conflicting_membership(conn, subject_key: str, cohort_id: int):
    """返回同互斥组内该主体已挂靠的其它册（无冲突返回 None）。

    联查 cohort_members × cohorts.mutex_group，跨表确认互斥身份。
    """
    target = conn.execute(
        "SELECT id, code, mutex_group FROM cohorts WHERE id=?", (cohort_id,)
    ).fetchone()
    if not target:
        return None
    group = (target["mutex_group"] or "").strip()
    if not group:
        return None
    return conn.execute(
        """
        SELECT m.id AS member_id, m.cohort_id, c.code AS cohort_code, c.mutex_group
        FROM cohort_members m
        JOIN cohorts c ON c.id = m.cohort_id
        WHERE m.subject_key=? AND c.mutex_group=? AND m.cohort_id<>?
        ORDER BY m.id
        LIMIT 1
        """,
        (subject_key, group, cohort_id),
    ).fetchone()


def subject_mutex_conflict(conn, subject_key: str):
    """主体是否跨册双挂同一互斥组（返回冲突行或 None）。"""
    return conn.execute(
        """
        SELECT c.mutex_group, COUNT(DISTINCT m.cohort_id) AS books
        FROM cohort_members m
        JOIN cohorts c ON c.id = m.cohort_id
        WHERE m.subject_key=? AND c.mutex_group<>''
        GROUP BY c.mutex_group
        HAVING books > 1
        LIMIT 1
        """,
        (subject_key,),
    ).fetchone()


def cohort_hit(conn, cohort_id: int, subject_key: str) -> tuple[bool, bool]:
    """求值命中：与单一人群成员同源。

    互斥组内同一主体只认首挂册（最早成员行）。第二挂（含未升正/脏数据
    遗留）不产生命中，返回 (hit, mutex_conflict)。
    """
    cohort = conn.execute(
        "SELECT id, mutex_group FROM cohorts WHERE id=?", (cohort_id,)
    ).fetchone()
    if not cohort:
        return False, False
    member = conn.execute(
        "SELECT 1 FROM cohort_members WHERE cohort_id=? AND subject_key=?",
        (cohort_id, subject_key),
    ).fetchone()
    if not member:
        return False, False
    group = (cohort["mutex_group"] or "").strip()
    if not group:
        return True, False
    first = conn.execute(
        """
        SELECT m.cohort_id
        FROM cohort_members m
        JOIN cohorts c ON c.id = m.cohort_id
        WHERE m.subject_key=? AND c.mutex_group=?
        ORDER BY m.id
        LIMIT 1
        """,
        (subject_key, group),
    ).fetchone()
    # 跨册双挂时，请求册若不是首挂册 → 不命中并标记互斥冲突
    if first and first["cohort_id"] != cohort_id:
        return False, True
    return True, False
