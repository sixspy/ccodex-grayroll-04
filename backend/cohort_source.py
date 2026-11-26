"""grayroll-04 互斥人群单一读取源。

规则页、求值页、发布页、对比页、历史页的互斥/人群信息一律经此模块取数，
禁止各页自行拼 SQL —— 避免口径漂移导致的「另一面假绿」。
"""
from __future__ import annotations

MUTEX_GROUP_EMPTY = ""


def official_rule_rows(conn) -> list[dict]:
    """正式规则 + 开关 + 环境 + 所引人群（含互斥组）。规则页/求值页/对比页共用。"""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT r.id, r.flag_id, r.env_id, r.kind, r.percent, r.cohort_id,
                   r.version, r.official, r.updated_at,
                   f.key AS flag_key, f.title AS flag_title, f.status AS flag_status,
                   e.code AS env_code, e.title AS env_title, e.risk_level,
                   c.code AS cohort_code, c.title AS cohort_title,
                   c.mutex_group AS cohort_mutex_group
            FROM flag_rules r
            JOIN flags f ON f.id = r.flag_id
            JOIN environments e ON e.id = r.env_id
            LEFT JOIN cohorts c ON c.id = r.cohort_id
            WHERE r.official = 1
            ORDER BY r.id
            """
        ).fetchall()
    ]


def official_rules_indexed(conn) -> dict[tuple[int, int], dict]:
    """(flag_id, env_id) -> 正式规则行（供发布页/对比页按单元格取数）。"""
    return {(r["flag_id"], r["env_id"]): r for r in official_rule_rows(conn)}


def rule_shadow_rows(conn) -> list[dict]:
    """影子规则草案 + 所引人群（含互斥组）。规则页/对比页共用。"""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT s.*, c.code AS cohort_code, c.mutex_group AS cohort_mutex_group
            FROM rule_shadows s
            LEFT JOIN cohorts c ON c.id = s.cohort_id
            ORDER BY s.id DESC
            """
        ).fetchall()
    ]


def release_rows(conn) -> list[dict]:
    """正式发布 + 当前正式规则所引人群（与规则页同源）。

    人群取当前 (flag_id, env_id) 的正式规则所引册，保证发布页展示的人群
    与规则页、求值命中完全一致。
    """
    rules = official_rules_indexed(conn)
    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT rel.*, f.key AS flag_key, e.code AS env_code
            FROM releases rel
            JOIN flags f ON f.id = rel.flag_id
            JOIN environments e ON e.id = rel.env_id
            WHERE rel.official = 1
            ORDER BY rel.id DESC
            """
        ).fetchall()
    ]
    for rel in rows:
        rule = rules.get((rel["flag_id"], rel["env_id"]))
        rel["cohort_id"] = rule["cohort_id"] if rule else None
        rel["cohort_code"] = rule["cohort_code"] if rule else None
        rel["cohort_mutex_group"] = rule["cohort_mutex_group"] if rule else None
    return rows


def release_shadow_rows(conn) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT s.*, c.code AS cohort_code, c.mutex_group AS cohort_mutex_group
            FROM release_shadows s
            LEFT JOIN cohorts c ON c.id = s.cohort_id
            ORDER BY s.id DESC
            """
        ).fetchall()
    ]


def mutex_conflicts(conn) -> list[dict]:
    """跨册双挂同一互斥组的主体（对比页/历史页共用）。"""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT m.subject_key, c.mutex_group,
                   COUNT(DISTINCT m.cohort_id) AS books,
                   GROUP_CONCAT(DISTINCT c.code) AS cohort_codes
            FROM cohort_members m
            JOIN cohorts c ON c.id = m.cohort_id
            WHERE c.mutex_group <> ''
            GROUP BY m.subject_key, c.mutex_group
            HAVING books > 1
            ORDER BY m.subject_key
            """
        ).fetchall()
    ]


def mutex_rejections(conn, limit: int = 60) -> list[dict]:
    """第一段：第二挂拒写核销痕。"""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT mr.id, mr.subject_key, mr.cohort_id, mr.mutex_group,
                   mr.attempted_by AS actor, mr.created_at,
                   c.code AS cohort_code
            FROM mutex_rejections mr
            LEFT JOIN cohorts c ON c.id = mr.cohort_id
            ORDER BY mr.id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    ]


def contention_marks(conn, limit: int = 60) -> list[dict]:
    """第一段：人群锁争用核销痕（仅人群锁，排除发布/熔断锁）。"""
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT id, lock_key, loser, winner, created_at
            FROM contention_marks
            WHERE lock_key LIKE 'cohort-subject:%'
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    ]


def policy_divergences(conn, limit: int = 60) -> list[dict]:
    """第二段：命运取舍（偏离甲路径的偏航记录）。"""
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM policy_divergences ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    ]
