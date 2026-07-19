# D11 Batch A · Review pass1 (落盘记录)

- **分支/merge**: `d11-batch-a`（`9dee52a` 初版 + `f0424e1` fix-round）→ main merge `7d237ab`（本地；push 仍 ship-gated）
- **分派**: codex 实现（RCE 安全轮）；主 agent review + linchpin 独立核验
- **日期**: 2026-07-19

## 三件套结论

| 环节 | 结论 | 要点 |
|---|---|---|
| reviewer（security） | 围栏逻辑 **CLEAN** + 1 P0 + 1 P1（均已 f0424e1 闭合） | 独立构造 ~20 对抗 payload（`~`/`case-a` vs `case-aevil` 前缀混淆/`//`/全角分号/垂直制表符/`#`/`$HOME`/NUL/目录 symlink 别名/`\r`…）直打 `_validate_*` **零绕过**；返回形状 + `input_data` 字段名与 SDK v0.2.88 完全一致。**P0 F1**：bypassPermissions 下 hook deny 无测试证据（判定在打包 Node CLI，静态读不出）。**P1 F2**：`runner.py` case_root 恒开 Bash 需记录为有意决策。F3 INFO：TOCTOU 现架构不可达 |
| spec-compliance | TA1-TA4 **COVERED**，仅 **TA0 MISSING → REWORK**（linchpin 经验闸无真测试） | TA1 case_root 全链透传 + audit 零影响 / TA2 anchored fullmatch + realpath 子树 + page + metachar + Bash 受控加回 / TA3 对抗测试每类覆盖 / TA4 skill 接线 + 页锚保真 |
| **fix-round f0424e1** | F1 + F2 + TA0 全闭合 | 新增 `tests/test_ocr_page_hook_integration.py`：真 `query()` + `permission_mode="bypassPermissions"` + 记录型 deny-hook；断言正确（marker 建=fail P0 / 模型没调 Bash=skip 不伪装 / 调了+marker 未建=pass）。`runner.py` 加 F2 注释 |
| evaluator | **PASS 4.7/5**（Func 4.8 / Spec 4.8 / Craft 4.6 / Robust 4.7） | 独立读测试 + 核 codex **raw stdout**（非自报）：真网关 `Test A/B evidence: hook_calls=1, marker_created=False` / `1 passed`；独立重跑 903 passed/2 skip。P0=0 P1=0，done_without_evidence=0，over_engineering=0 |

## linchpin 证据（核心）

`bypassPermissions` 下 PreToolUse `deny` **真拦住 Bash**：codex `source .env` 真网关跑两条集成测试，实际输出 `hook_calls=1, marker_created=False`（模型确实发起 Bash → hook 被咨询 → deny 生效 → marker 未建）。主 agent 在 codex 原始 stdout 核实运行命令（line 9041/9252）与输出（line 10250/10462），非采信 self-report。

## 主 agent 独立验

- merged main 全量 `uv run pytest -q` = **920 passed, 2 skipped**（integration 无网关 skip），ruff 净
- 读 fence 逻辑 + 集成测试结构确认（真 query()、正确 disambiguation、优雅 skip）

## 遗留（非阻塞）

- F3 TOCTOU：INFO，现架构不可达（Write 只建普通文件、Bash 只跑过闸单命令）；若未来 Bash 来源多路径化需重评
- integration 测试需真网关才断言（部署机/有网关时跑；CI/无网关 skip 属 integration 常态）

## Sisyphus

- [x] TA0-TA4 全完成 + 验收过测试（对抗 + 真网关集成，均独立复核非采信自报）
- [x] P0=0 P1=0；merge 7d237ab（本地）；push 待 ship 窗口
