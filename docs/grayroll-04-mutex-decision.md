# grayroll-04 · 互斥人群第二挂拍板说明（当班封死）

**域：应用开发 · 全栈开发**　**闸：灰栈第 4 闸**　**状态：已封死**

## 1. 问题

人群页允许把同一主体 `s-dual` 同时写进互斥人群 A 与 B；规则页引用任一人群后，
求值页双路径都可能命中——同一主体在互斥组里被算了两次，正式零增失效。

## 2. 拍板口径（唯一）

**只走甲路径：互斥人群第二挂 → 正式成员册零增、拒写（HTTP 409）。**

- 判定在**同主体人群锁**内串行完成：先跨表联查 `cohort_members × cohorts.mutex_group`，
  同组内该主体已挂其它册即拒写。
- 拒写时只留两类痕：`mutex_rejections`（拒写核销痕）与 `change_history` 的
  `cohort_mutex_reject` 事件；`cohort_members` 与 `cohorts.member_count` **零改**。
- 求值侧联查同一互斥组：同一主体只认**首挂册**，第二挂（含历史脏数据、未升正的
  影子挂靠）不产生命中，响应带 `mutex_conflict=true`。求值与"单一人群成员"同源。

**乙路径（只落影子草案、待裁决升正）本需求不启用。** 请求里显式带
`path:"shadow"`（或任何非 `official` 的折中值）一律写 `policy_divergences`
偏航痕并 409 拒写，正式区零改。**不设第三路折中。**

## 3. 两段式写入

1. **第一段 · 争用核销**：并发两路抢同主体人群锁，败方只写 `contention_marks`，
   正式成员行/人数零改；胜方落库后释放锁。
2. **第二段 · 命运取舍**：第二挂的处置只走甲路径拒写并记 `mutex_rejections`；
   任何偏离甲路径的请求记 `policy_divergences` 并拒写。两段在历史页
   `/api/history/mutex-timeline` 分段呈现。

## 4. 落点（三红分服务救绿）

| 失败测 | 盯的问题 | 所在服务 | 测试文件 |
| --- | --- | --- | --- |
| 甲 | 第二互斥挂靠仍写正式成员行 | 人群服务 `cohorts_svc` | `tests/test_grayroll_04_jia.py` |
| 乙 | 求值页把未升正双挂当已合法命中（假绿） | 求值服务 `evaluate_svc` + 策略 `policies` | `tests/test_grayroll_04_yi.py` |
| 争用 | 两路会话抢同主体人群锁无锁双成 | 锁 `locks` | `tests/test_grayroll_04_zheng.py` |

- 三红分属不同服务、**分别**见红，**不靠单点互斥校验一并救齐**。
- 争用侧并发双请求脚本：`scripts/cohort_mutex_member_04.py`。
- 五页同源（规则/求值/发布/历史/对比）均在各自读接口联查 `cohorts.mutex_group`，
  由 `tests/test_grayroll_04_yi.py::test_five_pages_share_mutex_cohort_source` 兜底。

## 5. 复现夹具（先见红后改）

- 互斥组 `mx-dual`：`cohorts.id=4`（A 册）、`cohorts.id=5`（B 册）。
- 主体 `s-dual` **已在 A 册**（`cohort_members.id=8`），B 册另有 `u-bonly`。
- 复现路径：对 `/api/cohorts/5/members` 提交 `{"subject_key":"s-dual"}`。

## 6. 验收

```bash
python -m pytest tests/test_grayroll_04_jia.py tests/test_grayroll_04_yi.py tests/test_grayroll_04_zheng.py -q
python scripts/cohort_mutex_member_04.py
```

- 三红改绿：`本套 15 passed`；
- 争用脚本三项 `all_ok: true`（同册禁双成 / 跨册双拒 / 预置锁两路皆败方）；
- 偏航：`path:"shadow"` → 409「偏航拒写」，`policy_divergences` 留痕。
