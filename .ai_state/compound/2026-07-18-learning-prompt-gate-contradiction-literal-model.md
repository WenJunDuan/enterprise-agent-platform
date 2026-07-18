# Learning · prompt 承诺与服务端语义闸的矛盾会潜伏到换 literal 模型才爆

- 日期: 2026-07-18
- 场景: D3 spike (sprints/2026-07-18-prompt-single-source) 首跑, 生产 Mode A 在 golden 用例上必挂
- 类型: learning

## 事实

`AUDIT_INSTRUCTIONS`(server/audit/runner.py:56) 向模型承诺「数据真实性拒绝时 policy_refs 允许为空数组」;
而承重依据闸 `_validate_audit_result`(server/common/output_contracts.py:286) 对 rejected **无条件**要求 ≥1
policy_ref。两者写入时间不同、各自局部合理, 合起来矛盾。

矛盾长期未爆, 因旧模型(deepseek-v4-pro)恰好会顺手引一条反虚报类规则过闸。换 deepseek-v4-flash(更
literal, 忠实执行 prompt 的空数组承诺)后: 占位/造假案件 → 空 policy_refs → 闸拒 → 重试同因失败 →
生产必 failed。`tests/eval_fixtures/golden_manifest.json` 唯一用例(placeholder-invoice)正是此形态 →
**D1 audit 回归闸在 flash 下假红**。

同场次要发现(方向一致的第二例): `.claude/commands/audit.md` 与 AUDIT_INSTRUCTIONS 双源漂移(command 版缺
「数据真实性快速核验」整节与 JSON 引号纪律), 且 spike 实测两源契约失败率不对称(内联 4/6 漏 explanation vs
command 侧 1/7)——**prompt 内容差异直接兑换成生产可靠性差异**, 不只是卫生债。

## 教训

1. **prompt 是契约的一半**: 改 prompt 输出承诺或改语义闸, 必须 grep 对侧是否有相反承诺/要求。闸从严 +
   prompt 从宽 = 模型越听话越容易挂, 这是「模型依赖的隐性 flaky」, 测试与旧模型都测不出来。
2. **换模型 = 契约一致性回归的触发器**: literal 模型是免费的 prompt-闸一致性 fuzzer; 换 MODEL_NAME 后应
   先跑一轮 golden manifest 再上生产。
3. **golden 用例要覆盖 prompt 的每条特殊承诺**: 「允许空 policy_refs」这类例外分支若有 golden 用例逐承诺
   校验, 矛盾在写入当天就会被闸抓住。

## 后续

修复方向二选一待用户拍(倾向 prompt 从严: 引 expense_travel_026 反虚报或降 manual_review, 不松闸), 详见
sprints/2026-07-18-prompt-single-source/route-note.md 附录。
