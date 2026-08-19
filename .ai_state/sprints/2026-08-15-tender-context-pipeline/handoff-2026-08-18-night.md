# Handoff — 2026-08-18 晚（下会话唯一入口）

> 接替 `handoff-2026-08-18.md`（其"下一步主战场=检索"结论已被纠偏令 v2 部分否决）。
> **下会话入口链（按序读）**：本档 → `.ai_state/claude/Tender链路纠偏令 v2 20260818.md`（效力最高）
> → `plan-2026-08-18-v2-execution.md`（六步执行序列）→ 施工文档 v1（按需）。

## 一、一句话状态

P0 五项护栏 + Phase 0 回归闸已合并推送 `origin/main`，线上仍是 `0818b2`+DeepSeek（部署冻结）；
纠偏令 v2 已裁决方向，六步执行计划就绪，**Step 1（部署 0818b3）待用户放行**，其余可顺序开工。

## 二、本日会话完成清单（全部已推送，勿重做）

1. **根因三连修正**（教训记录在 `plan-2026-08-18-accuracy.md`「被证伪的先前结论」节）：
   - "OCR 闸从不触发" = awk 字节计数错（中文×3），实测闸会触发（59/107 空白页）→ 故障在闸后
   - "检索 unresolved=0 ⇒ 块空 ⇒ 摄取主因" = 把命中当命中证据；实为**错位且过薄**（82分项拿到
     招标废标条款 301 token）→ 摄取与检索是并列瓶颈
   - 预算悬崖（95K/50K 时 criteria>21K 硬失败）系当日配 qwen 自引，已回退+修护栏
2. **P0 五项护栏**（merge `682afd5`，56 测试）：预算下界 `max(query_count, criteria_tokens)` 显式
   失败分因 / effort 白名单 env 声明化 / 抽取超时+锁工具面（含 case_root RCE 封堵）/
   criteria 未就绪提交口非阻塞拒绝（`criteria_gate.py`）/ `total_score`+`pending_max` 服务端汇总
3. **Phase 0 回归闸**（merge `744ed63`，60 测试）：`eval/golden/case-zj-live`（7 缺陷+3 客观分+
   报价勾稽，匿名化）/ `eval_tender_regression.py` 四指标 / 守卫扩面 `eval/`+`.yaml` /
   F1 反向假命中已修（`94bf81c`）
4. **Fable review**：VERDICT=CONCERNS 无 P0；十项裁决 KEEP×8 DEFER×2；F2/F3 豁免已写 merge commit
5. **回归**：17 failed / 1,767 passed，与基线逐名一致（17 条既有失败与改动面无交集）
6. **qwen 实验结论**（已回退）：22.5 tok/s 下单发形态跑不完（单结论输出 33K 字≈25min 纯解码）；
   Qwen3.8 模板只认 effort {xhigh,medium,low}；vLLM `/v1/messages` 原生可用；
   qwen 配置存部署机 `.env.bak-qwen-config-*`
7. **对接文档**：`.ai_state/docs/招投标评标服务对接文档.md`（/tender 19 端点）
8. **纠偏令 v2 落库** + 六步执行计划（`plan-2026-08-18-v2-execution.md`）

## 三、v2 对账（三处，勿按 v2 原文重做）

- v2 令三①（P0.1+P0.4）与"P0.2/0.3/0.5 随行"：**已全部完成**（上表 2），销项
- v2 令三②（基线回填）前提：评测读 `total_score`（P0.5 产物），`0818b2` 无 → **先部署 0818b3**
- v2 令三③（case-2/3）素材：YD/BL已删库，唯一副本抢救于
  `knowledge/external/车辆管理系统/results-5ccbb361批-20260818.json`（含 criteria 回显 18,921 字，
  兼作 D2 本地重建索引的输入）
  - **订正（2026-08-19 实查证伪）**：该抢救件**从未存在于盘上**（全盘搜索无踪，服务器
    task 表也无 5ccbb361），"已抢救"是记档时的未验证断言。已用服务器直拉补齐素材
    （`materials-server-pull-20260819.json`：4 条历史结论 + 现役 criteria 12 项），
    case-2/3 已据此沉淀完成。连带证伪：`53f94fd0` 并非BL结论，属另一项目
    （房建/市政类），accuracy 计划里挂它名下的 D2 错位实证出处随之改挂该项目——
    现象仍真（昨晚 6e67cbd2 BL实跑另证了记账错位），但素材归属曾记错。
    教训见 `compound/2026-08-19-learning-handoff-claims-need-artifact-proof.md`。

## 四、下会话执行序列（细节见 plan-2026-08-18-v2-execution.md）

```
Step 0 · 文档令残项: design AC1 措辞回改 / 评测脚本纯搬运拆分 eval/regression.py /
         fixture 真实编号改合成+守卫评估   （v1+v2 落库已在本会话完成）
Step 1 · 部署 0818b3【待用户放行】: rsync+build+重建, smoke 验提交闸与 total_score
Step 2 · case-zj-live single ×3 回填 v1 附录B → Phase 0 过闸
Step 3 · YD/BL → case-2/3（抢救 JSON + 本地底稿, 匿名化同 case-1）
Step 4 · D1/D2 并行诊断: D1 摄取实验(部署机容器, p85-90 证书页), "返回空"首选修复=vision-page;
         D2 本地重建索引逐项验, 修复仅限四项机械缺陷
Step 5 · Phase A agency 薄实验（TENDER_AGENCY 开关, 纠偏令一全文照办, 失败也是产出）
Step 6 · 数字裁决 P2/P3/P4（成功判据 = v2 五节表）
```

**禁令**（v2 令三重申）：词表加词/新增常数/百分比阈值/查询串措辞调整未经诊断数据一律禁止；
回归闸期望值与命中判定逻辑禁改；一次一步，白名单外记 proposals。

## 五、待裁决/挂起

- **P0.6 冻结件**（worktree `agent-aceea5e2cd5e05986`，criteria 回显抑制，未提交）：两轮 Fable
  一致 DEFER 到 Phase 2；worktree 保留，**勿 prune**
- `output.py::_score_summary` 与 `summarize_scoring` DRY 债：漂移守卫已钉，归并落点=P0.6 裁决或 Phase 2
- `prewarm_oracle` 慢挂与文件长度债：沿旧 handoff，未动

## 六、环境备忘

- 部署机 `smardaten@100.91.100.13`（密钥 `~/.ssh/100.91.100.13`，勿用域名），目录
  `/opt/application/enterprise-agent-platform`（rsync 副本非 git）
- 现役 `agent-backend:0818b2` + DeepSeek（已验证 `/health` ok，evidence 额度 59,400）；
  回滚位 `0818b1`；env 备份链 `.env.bak-*`（qwen 配置在 `.env.bak-qwen-config-*`）
- 容器 exec 用 `-u app`（root 撞 CLI 保护）；容器内无 curl 用 python；heredoc 经
  `ssh host 'bash -s' <<'EOF'`
- 全量回归 `--ignore=tests/test_tender_prewarm_oracle.py`；主 checkout 基线 **17F/1652P**
  （worktree venv 缺可选依赖会虚高到 24/34，比对必须同环境逐名）
- 评测：`uv run python scripts/eval_tender_regression.py --case case-zj-live --dry-run
  --corpus-root knowledge/external` 应 EXIT=0；真跑加 `--backend` 与 env `TENDER_EVAL_TOKEN`
