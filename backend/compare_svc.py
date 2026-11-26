"""正式规则 vs 影子草案对比。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

import cohort_source
from auth import current_user
from db import connect
from validators import require_int

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("/flag/{flag_id}/env/{env_id}")
def compare_flag_env(flag_id: int, env_id: int, authorization: str | None = Header(default=None)):
    current_user(authorization)
    fid = require_int(flag_id, "开关", 1)
    eid = require_int(env_id, "环境", 1)
    with connect() as conn:
        fl = conn.execute("SELECT id, key, title, status FROM flags WHERE id=?", (fid,)).fetchone()
        env = conn.execute("SELECT id, code, title FROM environments WHERE id=?", (eid,)).fetchone()
        if not fl or not env:
            raise HTTPException(404, detail="开关或环境不存在")
        official = conn.execute(
            "SELECT * FROM flag_rules WHERE flag_id=? AND env_id=? AND official=1", (fid, eid)
        ).fetchone()
        official_cohort = None
        if official and official["cohort_id"]:
            official_cohort = conn.execute(
                "SELECT id, code, title, mutex_group FROM cohorts WHERE id=?",
                (official["cohort_id"],),
            ).fetchone()
        rule_shadows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM rule_shadows WHERE flag_id=? AND env_id=? AND status='open' ORDER BY id DESC",
                (fid, eid),
            ).fetchall()
        ]
        for sh in rule_shadows:
            if sh.get("cohort_id"):
                c = conn.execute(
                    "SELECT code, mutex_group FROM cohorts WHERE id=?", (sh["cohort_id"],)
                ).fetchone()
                if c:
                    sh["cohort_code"] = c["code"]
                    sh["cohort_mutex_group"] = c["mutex_group"]
        release_shadows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM release_shadows WHERE flag_id=? AND env_id=? AND status='open' ORDER BY id DESC",
                (fid, eid),
            ).fetchall()
        ]
        kill_shadows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM kill_shadows WHERE flag_id=? AND env_id=? AND status='open' ORDER BY id DESC",
                (fid, eid),
            ).fetchall()
        ]
        recent_releases = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM releases WHERE flag_id=? AND env_id=? AND official=1 ORDER BY id DESC LIMIT 5",
                (fid, eid),
            ).fetchall()
        ]
    diffs = []
    if official and release_shadows:
        sh = release_shadows[0]
        for field in ("kind", "percent", "cohort_id"):
            if official[field] != sh.get(field):
                diffs.append({"field": field, "official": official[field], "shadow": sh.get(field)})
    return {
        "flag": dict(fl),
        "env": dict(env),
        "official_rule": dict(official) if official else None,
        "official_cohort": dict(official_cohort) if official_cohort else None,
        "open_rule_shadows": rule_shadows,
        "open_release_shadows": release_shadows,
        "open_kill_shadows": kill_shadows,
        "recent_releases": recent_releases,
        "diffs": diffs,
        "has_pending_shadow": bool(rule_shadows or release_shadows or kill_shadows),
    }


@router.get("/matrix")
def compare_matrix(authorization: str | None = Header(default=None)):
    current_user(authorization)
    with connect() as conn:
        flags = [dict(r) for r in conn.execute("SELECT id, key, status FROM flags ORDER BY id").fetchall()]
        envs = [dict(r) for r in conn.execute("SELECT id, code FROM environments ORDER BY risk_level").fetchall()]
        # 与规则页/求值页/发布页同源：统一经 cohort_source 取数
        rules = cohort_source.official_rules_indexed(conn)
        conflicts = cohort_source.mutex_conflicts(conn)
        matrix = []
        for f in flags:
            row = {"flag_id": f["id"], "flag_key": f["key"], "status": f["status"], "cells": []}
            for e in envs:
                rule = rules.get((f["id"], e["id"]))
                row["cells"].append(
                    {
                        "env_id": e["id"],
                        "env_code": e["code"],
                        "has_rule": rule is not None,
                        "percent": rule["percent"] if rule else None,
                        "version": rule["version"] if rule else None,
                        "kind": rule["kind"] if rule else None,
                        "cohort_id": rule["cohort_id"] if rule else None,
                        "cohort_code": rule.get("cohort_code") if rule else None,
                        "cohort_mutex_group": rule.get("cohort_mutex_group") if rule else None,
                    }
                )
            matrix.append(row)
    return {"envs": envs, "matrix": matrix, "mutex_conflicts": conflicts}
