## Spec Compliance (spec-compliance, 2026-06-20T10:00:00Z)

### MISSING (功能做少了)
- M1: checklist.yaml H4 accept 写 "跨租户 submissions(测试证)"，且 checklist H4 files 明列 `tests/test_tender_routes.py # 新增跨租户拒绝测试`；但 `tests/test_tender_routes.py` 无任何跨租户拒绝测试（grep "cross_tenant/跨租户" 零结果）。对比 `tests/test_ocr_routes.py:106` 的 `test_extract_directory_cross_tenant_rejected` 已落地，tender 路由同等验收标准但测试缺失。

### EXTRA (功能做多了)
- E1 [合理]: `tests/test_core_pure.py` 新增 `_neutralize_ambient_rules` autouse fixture，design.md 未提及此文件，但属于真伪闸默认开后必须的 CI fixture 兼容修复，不影响 spec。
- E2 [合理]: `server/common/output_contracts.py:210` 行注释 "默认关(见 _rule_ref_check_enabled)" 未同步更新为 "默认开"，属轻微文案残留，不是 scope creep。

### DEVIATED (功能做偏了)
- D1 [文案矛盾，非实现偏差]: design.md H1 sub-task 写 "rule_id 前缀→tender_statute-*_"（approach B 描述）；user_decision `[已定 2026-06-20]` 明确 "approach A(rule_id 不动)"。实际实现：evalmethod.rules.json rule_id=tender_evalmethod_001，与 user_decision 吻合，validate-assets=ok。design.md 子任务文案早于 user_decision 未更新，代码以 user_decision 为准，不构成实现偏差。记录供 evaluator 参考。

### Spec Compliance 总评

- MISSING 数: 1
- EXTRA 数: 2 (合理 refactor/CI修复 2 个 / scope creep 0 个)
- DEVIATED 数: 0
- **建议**: REWORK
  - 原因: M1 — checklist.yaml H4 accept 以 "测试证" 为验收条件，test_tender_routes.py 跨租户拒绝测试明列于 H4 files 字段但代码中缺失，属 "标 done 实际做少了"。

---

**证据摘要**

| 项 | 状态 | 证据 |
|---|---|---|
| H1 RULE_REF_CHECK 默认 ON | ok | output_contracts.py:42 os.getenv("RULE_REF_CHECK", "1") |
| H1 F3 文件重命名 approach A | ok | evalmethod.rules.json + regulation.rules.json; validate_rule_assets()={status:ok,checked_files:6} |
| H1 CLAUDE.md/tender-evaluate.md 文案已改 | ok | diff: statute-*.rules.json → {法规简称}.rules.json |
| H1 死引用清除 | ok | grep -r statute- 在 server/tests 全零结果 |
| H2 try_transition 原子 CAS | ok | task_store.py:158-183 单条 UPDATE WHERE status!=? |
| H2 delete_if_idle 原子守卫 | ok | task_store.py:185-196 单条 DELETE WHERE status!=? |
| H2 audit.py retry/delete 接入原子方法 | ok | audit.py:218 try_transition_audit_task; :253 delete_audit_task_if_idle |
| H2 8-线程并发单赢家测试 | ok | test_audit_task_store.py:122-148 results.count(True)==1 |
| H3 F4 4处 upsert 包 to_thread | ok | audit_worker.py diff: 4处 await asyncio.to_thread(upsert_audit_task,...) |
| H3 F5① _BACKGROUND_TASKS 引用集+自清 | ok | audit_worker.py:39 + _track_task + add_done_callback |
| H3 F5② admission_available 准入+503 | ok | audit_worker.py:46; audit.py:90,207 |
| H3 F5③ 如实标 backlog | ok | checklist.yaml H3.backlog 完整说明降级理由 |
| H4 audit.py 三路径传 tenant | ok | audit.py:101 validate_directory_case_path(,tenant); :109 materialize_upload_submission(,tenant=tenant) |
| H4 ocr.py extract 补 tenant(原丢弃) | ok | ocr.py:78 tenant=verify_tenant; :92 validate_directory_case_path(,tenant); :97 materialize_ocr_upload(,tenant=tenant) |
| H4 ocr.py fill 传 tenant | ok | ocr.py:160 materialize_ocr_upload(,tenant=tenant) |
| H4 tender.py 传 tenant | ok | tender.py:90 validate_directory_case_path(,tenant); :98 materialize_upload_submission(,tenant=tenant) |
| H4 upload 写 submissions/<tenant>/<request_id> | ok | upload_helpers.py:137 case_dir=SUBMISSION_ROOT_DIR/tenant/request_id |
| H4 OCR 跨租户拒绝测试 | ok | test_ocr_routes.py:106 test_extract_directory_cross_tenant_rejected |
| H4 tender 跨租户拒绝测试 | MISSING | test_tender_routes.py 无对应测试; checklist H4 files 明列须有 |
| 全量 299 passed / ruff clean | ok | 验证通过 |
