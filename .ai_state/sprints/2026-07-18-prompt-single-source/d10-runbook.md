# D10① 直连路径 Runbook — 休眠资产重启 + 部署机核对清单

> T5(D10④，design.md §T5)。文档项，随 T2 收口。目标读者：把 `AUDIT_DIRECT_CONNECT`
> 从默认关翻成开的运维/部署工程师。本文不含判断逻辑改动，纯运维步骤 + 核对清单。

## 0. 休眠资产是什么

D10① 引入的 `server/audit/direct.py`（`AsyncAnthropic` 直连路径）默认**休眠**——
`AUDIT_DIRECT_CONNECT` env flag 默认 `0`，全部审核走原有 `claude-agent-sdk` CLI
子进程路径（字节级行为不变，见 `tests/test_audit_direct_connect.py` 的 wiring
断言）。休眠状态下，`server/audit/direct.py` 的代码存在但从不被调用——它是随
D3+D10 sprint 一起交付、留给运维**按需**唤醒的资产，不是本 sprint 就默认上线的
功能。本文档就是"唤醒"这份资产的操作手册。

唤醒后的效果（design.md「验收标准」）：单次审核墙钟时延中位数下降（taxi/placeholder
两个 case 合并中位 ≤ CLI 路径 × 70%），网关侧同时吃到 prompt cache 红利；副作用见
下方风险与缓解。

## 1. 开启前部署机核对清单（缺一不可，按顺序做）

### 1.1 网络 / 代理形态核对（P0，直连特有风险）

`server/audit/direct.py:_build_client` 用 `httpx.AsyncClient(trust_env=False)`
显式关闭 httpx 的**环境变量代理自动发现**（`HTTP_PROXY` / `HTTPS_PROXY` /
`ALL_PROXY`）——这是 D10① T2 在本 worktree 实测复现的坑：anthropic SDK 自带的
`DefaultAsyncHttpxClient` 会**无视** `trust_env` 参数、无条件读环境代理变量拼
`mounts`，sandbox/内网常见 `all_proxy=socks5://...` 时若命中会直接对 SOCKS 代理
抛 `ImportError: ... socksio ...`（该机没装 `socksio` 可选依赖）。`direct.py`
已用原生 `httpx.AsyncClient(trust_env=False)` 绕开这个坑（详见该文件
`_build_client` 的 docstring）。

**运维需要核对的是另一件事**：`trust_env=False` 关掉的只是"顺着环境变量自动接管
代理"，直连请求的目标地址仍然是显式的 `MODEL_BASE_URL`/`ANTHROPIC_BASE_URL`
（即部署拓扑里的 LiteLLM 网关，见 README「运行链路」）。核对项：

- [ ] 部署机到 `MODEL_BASE_URL`（通常是 `http://litellm:4000` 或宿主机 IP+端口）
      是否**直接可达**，不依赖任何 `HTTP_PROXY`/`SOCKS` 环境变量做转发。
      验证：`curl -sf $MODEL_BASE_URL/health/liveliness`（或等价健康检查路径）
      在**不设**任何代理 env 的 shell 里也能通。
- [ ] 若部署机访问网关**必须**经过企业代理（较少见——通常网关与业务同内网），
      `trust_env=False` 会让直连路径连不上，此时**不要**开
      `AUDIT_DIRECT_CONNECT`，继续走 CLI 路径（CLI 子进程走 SDK 自身网络栈，
      不受本条约束）；或改造部署拓扑使网关直连可达后再评估。
- [ ] 确认没有防火墙/安全组只放行了 CLI 子进程惯用的出站规则、而遗漏了
      Python 进程本身发起的 HTTPS 出站（直连是应用进程直接发请求，CLI 路径是
      子进程发请求，两者的出站主体不同，安全组按进程名/用户放行时需覆盖两者）。

### 1.2 anthropic SDK 离线安装（P0）

生产部署机通常无外网，需提前把 `anthropic` 及其依赖（`httpx` 等，均已随 D10①
T2 写入 `pyproject.toml`/`uv.lock`）打进离线安装源：

- [ ] 确认 `pyproject.toml` 已含 `anthropic>=0.117.0` 与 `httpx>=0.28.1`
      （`git log --oneline -- pyproject.toml` 应能看到 D10① T2 的 commit）。
- [ ] 内网 PyPI 镜像 / 离线 wheel 仓库已同步 `anthropic`、`httpx`、及其传递依赖
      （`anyio`/`distro`/`jiter`/`pydantic` 等——`uv.lock` 已锁定精确版本，
      离线源按 `uv.lock` 里的版本号逐一核对，不要用"大概兼容"的版本）。
- [ ] 部署机执行 `uv sync`（或对应离线安装流程）后跑：
      ```bash
      uv run python -c "import anthropic; print(anthropic.__version__)"
      ```
      能打印版本号且不报错，才算装妥。

### 1.3 `.env` 配置核对（沿用现有变量，无新增必填项）

`server/audit/direct.py:_build_client` 复用 `configure_claude_runtime_env()`
——即现有 `MODEL_BASE_URL`/`MODEL_AUTH_TOKEN`/`MODEL_NAME`（或原生
`ANTHROPIC_*` 等价变量）齐全即可，**不需要为直连路径单独配一套凭证**：

- [ ] `uv run python -m server.cli runtime` 输出 `status: ok`、
      `errors: []`（这一步在 CLI 路径下本就该过；直连复用同一份配置校验）。
- [ ] 确认目标模型（`MODEL_NAME`）走的网关端点支持 anthropic 原生
      `POST /v1/messages`（LiteLLM 标准部署满足；若网关做过定制路由，需单独确认）。

### 1.4 真网关 golden 3 连跑（P0，先 flag off 基线，再 flag on 验证）

目的：确认直连路径的判断结果与 CLI 路径**结论一致**（design.md 验收标准 2 的
质量前提——时延更快但判断跑偏没有意义）。

```bash
# 基线（flag off，确认改动前环境本身健康；应已是日常状态）
AUDIT_DIRECT_CONNECT=0 uv run python -m server.audit.eval \
  --manifest tests/eval_fixtures/golden_manifest.json
AUDIT_DIRECT_CONNECT=0 uv run python -m server.audit.eval \
  --manifest tests/eval_fixtures/golden_manifest.json
AUDIT_DIRECT_CONNECT=0 uv run python -m server.audit.eval \
  --manifest tests/eval_fixtures/golden_manifest.json

# 唤醒直连路径，跑 3 遍确认稳定
AUDIT_DIRECT_CONNECT=1 uv run python -m server.audit.eval \
  --manifest tests/eval_fixtures/golden_manifest.json
AUDIT_DIRECT_CONNECT=1 uv run python -m server.audit.eval \
  --manifest tests/eval_fixtures/golden_manifest.json
AUDIT_DIRECT_CONNECT=1 uv run python -m server.audit.eval \
  --manifest tests/eval_fixtures/golden_manifest.json
```

- [ ] flag off 3 次全过（沿用日常基线，不应有变化）。
- [ ] flag on 3 次全过，且每个 case 的 `verdict`/`policy_refs` 与 flag off 基线
      一致（`server.audit.eval` 按 golden 期望比对，逐条打印 mismatch；有
      mismatch 先查是否命中「回落语义」——`server/audit/runner.py` 的传输类
      单次回落 CLI，日志会打 `audit direct-connect transport failure,
      falling back to CLI path once`，属预期；若日志显示走的是直连本身但结论
      与 CLI 不同，才是需要排查的真实差异）。
- [ ] 用真实业务案件目录（`data/` 下，非 `tests/eval_fixtures/` 合成样例）
      至少手工核对 1-2 单，确认 `GET /audit/tasks/{id}/result` 能正常读回
      （critic F1 关注的归档接缝——`archive_result_payload` 写 `results` 表；
      单测已覆盖 mock 场景，这一步是真网关场景的最终确认）。

### 1.5 时延对照口径（design.md 验收标准 2，逐字复述以防漂移）

> flag on: 真网关 taxi+placeholder 各 3 轮与 flag off 同窗交错对照，**跨 case
> 合并中位 on ≤ off×70%**（单样本超同 case 中位 2 倍视为网关抖动，允许整场
> 重跑一次）。

- [ ] 复用 `.ai_state/sprints/2026-07-18-prompt-single-source/spike/d10_direct_spike.py`
      （E1 spike 已实现同款「taxi+placeholder 各 3 轮 + CLI 对照组同窗交错」，
      直接重跑一次即可拿到本次部署机的真实对照数据；脚本用法见其文件头注释）：
      ```bash
      uv run --with anthropic python \
        .ai_state/sprints/2026-07-18-prompt-single-source/spike/d10_direct_spike.py
      ```
- [ ] 脚本跑完打印的汇总里，`D`（直连）与 `A-ctl`（CLI 对照组）两行的
      `median` 按上述口径比较：`D.median <= A-ctl.median * 0.7`。
- [ ] 若单个样本墙钟超过同 case 中位数 2 倍——记为网关抖动，**整场重跑一次**
      （不要挑着重跑单个样本，口径要求整场重跑保持交错时序）。
- [ ] 结果记档：新跑的 `d10-results.jsonl` 覆盖/追加到同目录，本次部署机的
      判读结论（达标/不达标 + 数据）写回本 runbook 或新建
      `d10-runbook-<部署机标识>-verify.md`（按需，不强制建新文件）。

## 2. 开启 + 重启步骤

前置：以上第 1 节全部核对项打勾。

### 2.1 Docker Compose 部署（首选方式）

1. 编辑 `audit-agent` 服务的 env file（README「配置」一节描述的位置），加：
   ```dotenv
   AUDIT_DIRECT_CONNECT=1
   ```
2. **`restart` 不重载 env_file**（README 已知坑，见其「改了 env 不生效」条目）
   ——必须：
   ```bash
   docker compose up -d --force-recreate
   ```
3. 验证：
   ```bash
   docker exec audit-agent python -m server.cli runtime
   ```
   （确认服务仍 `status: ok`；本命令本身不直接打印 `AUDIT_DIRECT_CONNECT`，
   该 flag 由 `server/audit/runner.py` 每次审核时读一次 env，无需额外 CLI
   子命令验证配置加载——直接跑一单真实审核 + 查日志确认走了直连路径最可靠，
   见下方「回退步骤」前的验证段）。

### 2.2 原地运行 + systemd（备选方式）

1. 编辑 `/opt/enterprise-agent-platform/.env`，加 `AUDIT_DIRECT_CONNECT=1`。
2. ```bash
   sudo systemctl restart enterprise-agent
   journalctl -u enterprise-agent -f
   ```
3. 验证：`curl http://127.0.0.1:${APP_SERVER_PORT}/health`，再跑一单真实审核。

### 2.3 开发期（`app-server` 后台管理）

```bash
# .env 加 AUDIT_DIRECT_CONNECT=1 后
uv run app-server restart
uv run app-server doctor --require-running
```

### 2.4 唤醒后确认走的是直连路径（不是"配置生效但没人调用"）

跑一单真实审核后，查应用日志（`logs/app/<YYYY>/<MM>/<DD>/app.log`，或
`journalctl -u enterprise-agent`）：

- 应能看到 `server.audit.direct` 记的结构化日志事件 `audit_direct_metrics`
  （含 `wall_s`/`input_tokens`/`output_tokens`，D10③ T3 落的指标字段）——
  出现即证明本单走了直连路径。
- 若该单命中传输类故障并回落，会额外看到
  `audit direct-connect transport failure, falling back to CLI path once`
  一条 warning——这是**预期设计行为**（critic F2 回落语义），不是 bug；但若
  长期频繁出现，回到第 1.1 节重新核对网络/代理形态。

## 3. 回退步骤（出问题怎么关回去）

直连路径是纯 flag 门控，回退**不需要**代码变更、不需要数据迁移：

1. `.env` / env file 把 `AUDIT_DIRECT_CONNECT` 改回 `0`（或删掉该行，默认即 0）。
2. 按第 2 节对应部署方式的步骤重新加载 env + 重启服务
   （Docker: `docker compose up -d --force-recreate`；systemd:
   `systemctl restart enterprise-agent`；开发期: `uv run app-server restart`）。
3. 确认新提交的审核不再出现 `audit_direct_metrics` 日志事件，即已回退到纯
   CLI 路径（与本 sprint 改动前完全一致的行为，`tests/test_audit_direct_connect.py`
   的 wiring 断言即覆盖这条不变量）。

回退不影响历史数据：直连路径写入 `results` 表的记录（`request_mode="direct"`）
与 CLI 路径的记录（`request_mode="structured"/"text"`）共用同一张表/同一套
读取端点，回退后旧记录仍可正常读回。

## 4. 已知风险与缓解（摘自 design.md 风险表，运维视角复述）

| 风险 | 现象 | 缓解 |
|---|---|---|
| 直连丢工具面（Read 附件） | 需要模型读附件原件（图片/扫描件）的案件，直连路径无法像 CLI 路径那样临场 `Read` 文件 | flag 默认关；确需附件预嵌的场景先跑 T4 POC（`spike/d10_vision_poc.py`）确认网关支持 image content block，正式预嵌实施是独立任务；期间该类案件建议 `AUDIT_DIRECT_CONNECT=0`（CLI 路径保留 Read 能力） |
| 网络代理拓扑不满足 1.1 节 | 直连全部走传输类回落，`audit_direct_metrics` 日志几乎不出现，等于隐性只用了 CLI 路径（时延红利拿不到但也不影响正确性） | 按 1.1 节核对；确认前不要以为「flag 开了就一定生效」 |
| 网关 prompt cache 计费口径未确认 | D10③ 指标（`input_tokens`）落地后可观测，但账单口径需财务/运维另行核对 | 唤醒后第一周观察 `audit_direct_metrics` 的 `input_tokens` 趋势，与网关侧账单交叉核对 |
| 契约类故障不回落（design 明确禁止静默降级） | 模型输出格式问题在直连路径下会直接失败上报（不像传输类那样悄悄换 CLI 路径重来） | 属预期设计（critic F2）；`DirectContractError` 会被 `routes/audit_worker.py` 的既有异常处理捕获，任务标 `failed` 并记 `error_detail`，与 CLI 路径失败时的用户体验一致，不新增未处理异常面 |

## 5. 参考

- 实现：`server/audit/direct.py`（`run_direct_audit`/`_build_client`）、
  `server/audit/runner.py`（flag 门控 + 回落语义）。
- 测试：`tests/test_audit_direct.py`、`tests/test_audit_direct_connect.py`、
  `tests/test_audit_direct_metrics.py`。
- 设计：`.ai_state/sprints/2026-07-18-prompt-single-source/design.md`
  （T2/T3 段 + 验收标准 2 + 风险表）。
- 时延实测先例：`.ai_state/sprints/2026-07-18-prompt-single-source/spike/d10_direct_spike.py`
  与其产出 `spike/d10-results.jsonl`（E1 spike 数据）。
