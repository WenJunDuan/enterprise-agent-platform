# 部署 / 运行踩坑记录

> 按"症状 → 真因 → 解法"组织。新坑往这里追加，方便下次秒定位。
> 凭据/IP 等敏感值不在此文写明文。

---

## A. 网关与模型路由

### A1. 审核"时好时坏" / 偶发 400 或 exit 1（最隐蔽）
- **症状**：同样的请求，有时成功有时失败，无规律。
- **真因**：**litellm 配置里同一个 `model_name` 定义了两次**（指向不同上游，如一条云 dashscope、一条本地 vLLM），litellm 当负载均衡组**随机路由**。跳到限制紧的那个上游就失败。
- **解法**：`curl litellm:4000/v1/models` 看有无重名；`litellm_config.yaml` 里**一个 model_name 只留一条**，重名的改名。改后 `docker restart ea-litellm`。

### A2. `400 ... requested 64000 output tokens ... context length only 65536`
- **真因**：Claude CLI **默认请求 64000 output token**（写死在 CLI，项目代码/配置里没有），本地 vLLM `--max-model-len 65536` 装不下 `输入+64000`。
- **解法**：`audit-agent.env` 设 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000`（本地 65536 模型必设）。大上下文云模型（256K）不受影响。改后 `up -d --force-recreate`。

### A3. litellm 连不上上游 `Cannot connect to host 127.0.0.1:xxxx`
- **真因**：litellm 在容器里，`127.0.0.1` 指**容器自身**，不是宿主机/别的容器。
- **解法**：上游用**宿主机 LAN IP**（如 `http://<宿主IP>:8082/v1`）或把上游容器接到同一 docker 网络后用**容器名 + 容器内部端口**（注意不是宿主映射端口）。`docker network connect <net> <container>`。

### A4. litellm `AnthropicResponse ValidationError` / 上游用 https 失败
- **真因**：上游 `api_base` 写了 `https://` 但 vLLM 是明文 http；或上游返回的 reasoning/tool_calls 字段 litellm 翻译成 Anthropic 格式时崩。
- **解法**：`api_base` 用 `http://`；上游开了 `--reasoning-parser`/`--enable-auto-tool-choice` 时，文本模式审核易出畸形响应 → 见 E 区。

---

## B. 容器 / 网络 / 镜像

### B1. 改了代码但容器行为没变
- **真因**：`server/` `.claude/` `agent-front/dist` **烤进镜像**，不重建不生效（`knowledge/`/`data/`/`logs/` 才是挂载）。
- **解法**：`docker compose build` 重建（必 bump 镜像标签）。规则文件改动则同步到挂载的 `knowledge/`。

### B2. `MODEL_BASE_URL` 没进容器 → CLI 退回 `api.anthropic.com`（内网 ConnectionRefused）
- **诊断**：`docker exec audit-agent python -m server.cli runtime` 看 `anthropic_base_url`（空或指向 anthropic = 在拨公网）。
- **真因**：env 没真正进容器（env_file 没生效 / 没 recreate）。
- **解法**：`audit-agent.env` 设 `MODEL_BASE_URL=http://litellm:4000`，`up -d --force-recreate`。代码已硬约束：base_url 空/指向 anthropic 时直接报错（`ALLOW_ANTHROPIC_API=1` 解除）。

### B3. `env_file ... Additional property format is not allowed`（compose 版本）
- **真因**：compose **< v2.30** 不认 `env_file` 的 `format: raw`（demo 是 v2.27.1）。`path:`/`required:` 需 v2.24+。
- **解法**：该机 `docker-compose.yml` 里**删掉 `format: raw` 一行**（保留 `path:`/`required:`，或退回短格式 `- ./audit-agent.env`）。删后跑 `docker exec audit-agent printenv TENANT_KEYS` 确认 JSON 没被弄坏（应是完整 `{"default":"..."}`）。

### B4. mac mini 大文件招投标上传失败，但小文件正常
- **症状**：前端提示"请求失败，请稍后重试"；nginx/access 看到
  `POST /tender/projects/<id>/evaluate` 返回 400；后端没有生成 `tender_tasks`，
  `data/submissions/default/tender/` 也没有落文件。
- **后端特征**：异常发生在 `request.form()` 解析 multipart 阶段，日志含
  `starlette.requests.ClientDisconnect`。这表示上传流在识别/评标前断开，不是模型识别逻辑失败。
- **cloudflared 特征**：同一时间有 `Incoming request ended abruptly: context canceled`，目标为
  `https://agent.guoker.org/tender/projects/<id>/evaluate`。
- **真因**：公网 `cloudflared-mesh` 链路对大 body 上传不稳定或触发 Cloudflare 请求体限制。Cloudflare 官方
  `413 Payload Too Large` 文档列出 Free/Pro 100MB、Business 200MB、Enterprise 500MB+ 的上传上限：
  https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/
  前端 nginx / 后端路由可用，小文件同路径成功时尤其能确认问题在上传链路。
- **解法**：
  1. mac mini 前端 nginx 保持 `client_max_body_size 512m`、`client_body_timeout 600s`、
     `proxy_send_timeout 600s`、`proxy_read_timeout 1200s`、`proxy_request_buffering off`。
  2. 后端 env 保持 `MAX_UPLOAD_FILE_BYTES=536870912`（512MiB），与 nginx 对齐；改后重建/重启
     `agent-backend`。
  3. 用户无法拆文件时，优先绕过 Cloudflare：本机开
     `ssh -fN -o ExitOnForwardFailure=yes -L 15173:127.0.0.1:5173 macmini`，然后访问
     `http://127.0.0.1:15173/contracts/tender-review` 上传。
  4. 验证是否真正进入评标：`tender_tasks` 应出现 `accepted/running/completed`，上传目录应有 PDF 文件；
     如果只有 `tender_projects` 没有 task，就是还没进入识别。

### B5. Apple `container run --network ... hostname=...` 报错
- **症状**：重建 mac mini 容器时报 `unknown network property 'hostname'. Available properties: mac, mtu`。
- **真因**：Apple `container` 的 `--network` 参数不是 Docker run 语义，目前不接受 `hostname` 属性。
- **解法**：使用 `--network default,mtu=1280`，容器名用 `--name agent-backend` / `--name agent-front` 固定即可。

---

## C. SSH / 跳板

### C1. SSH `Permission denied`，之前还好好的
- **真因**：短时间反复**密码**登录触发 OpenSSH `PerSourcePenalties` / fail2ban，按源 IP 临时封禁（连密钥认证也一起封）。
- **解法**：① 装公钥走密钥认证（不再触发密码惩罚）；② 等冷却；③ 用 SSH ControlMaster 连接复用减少新建连接。

### C2. 连 demo（10.200.52.4）
- demo 只能经 **mac mini 跳板**：`ssh -J macmini -i ~/.ssh/njsr-app01_ed25519 root@10.200.52.4`。
- 用户是 **root**（不是 key 注释里的 codex）。`macmini` 在 `~/.ssh/config` 里定义。

### C3. zsh 下 `$SSHOPT` 变量被当成单个参数
- **真因**：zsh 默认不对未加引号的变量做分词。
- **解法**：ssh 选项**直接 inline 写**，别塞进变量；或用 `${=VAR}` 强制分词。

---

## D. 规则 / 资产校验

### D1. `asset_validation` 报 degraded：`category does not match filename` / `rule_id does not match prefix`
- **真因**：规则文件的 **文件名、`category` 字段、`rule_id` 前缀必须三者一致**。`server/platform/asset_validation.py` 强校验：`category == 文件名(去.rules.json)`，`rule_id` 以 `{domain}_{category}_` 开头。
- **解法**：三者对齐。例：接待规则文件名 `entertainment.rules.json` → `category: entertainment` → `rule_id: expense_entertainment_NNN`（不要文件名叫 reception 而 category 叫 entertainment）。

### D2. 规则文件改了但审核没用上
- **真因**：`knowledge/` 是**挂载目录**，要同步到目标机 `/opt/application/audit-agent/knowledge/`；它被 gitignore，不在镜像/仓库里。
- **说明**：内联 `/audit` 直接 glob `knowledge/expense/*.json` 注入 prompt，**不调用任何 skill**（skill 是旧编排流的废弃脚手架，删了不影响审核）。

---

## E. 模型输出质量（文本模式）

### E1. `audit result field explanation must be non-empty` / `未能从模型输出中解析出 JSON 对象`
- **真因**：文本模式（`AUDIT_STRUCTURED_OUTPUT=0`）下模型输出**有波动**：复杂案子模型长篇 reasoning、**始终没吐出最终 JSON 对象**（或漏填 explanation）。开了 thinking 的模型尤甚。模型分析往往是对的，只是不收尾成 JSON。
- **解法（按推荐）**：
  1. **关模型 thinking**（最对症）：内网 vLLM 用 `--default-chat-template-kwargs '{"enable_thinking": false}'`；云模型在 litellm 侧传等价参数。
  2. 调大 `AUDIT_CONTRACT_MAX_RETRY`（如 3）兜随机波动。
  3. 试 `AUDIT_STRUCTURED_OUTPUT=1`（需 litellm+模型支持 json_schema）。

### E2. CLI 崩 `Command failed with exit code 1 / Check stderr output for details`（黑盒）
- **解法**：代码已加 `_log_cli_stderr`（`server/core.py`）把 CLI stderr 落日志。查 `docker logs audit-agent | grep claude_cli_stderr` 看真因。

### E3. 手动复现审核时 CLI 报 `--dangerously-skip-permissions cannot be used with root`
- **真因**：`docker exec` 默认以 **root** 进容器，Claude CLI 拒绝 root 下跳过权限。真实服务以 `app` 用户（gosu 降权）跑，不受影响。
- **解法**：手动跑加 `-u app`：`docker exec -u app -i audit-agent python - <<'PY' ... PY`。

---

## F. 前端

### F1. 详情页白屏 `Minified React error #31 (object with keys {code,description,severity})`
- **真因**：旧归档结果里 `reasons`/`risk_dimensions` 是对象，前端按字符串/数组渲染对象 → 崩。
- **解法**：① 后端 `enrich_audit_decision` 写入+读取端都归一化（reasons 拍平字符串、risk_dimensions 对象→数组、0-100→0-10）；② 前端 `TaskDetail` 加 `toText`/`normalizeRiskDimensions` 兜底。旧结果免重跑即可渲染。

---

## G. 日志噪音排除特征

这些可以在日志侧先降噪；排除前保留 ERROR、failed、traceback、`status=failed`、`ClientDisconnect`
等异常关键词。

### G1. 后端 `agent-backend`
- 前端轮询任务状态：`INFO: .* "GET /tender/tasks/[0-9a-f-]+ HTTP/1.1" 200 OK`
- 前端轮询项目/结果列表：`INFO: .* "GET /tender/projects.* HTTP/1.1" 200 OK`
- 健康检查：`INFO: .* "GET /health HTTP/1.1" 200 OK`
- 正常启动噪音：`Started server process`、`Waiting for application startup`、
  `Application startup complete`、`Uvicorn running on`
- SDK 正常启动：`Using bundled Claude Code CLI:`
- PyMuPDF 建议提示：`Consider using the pymupdf_layout package`

### G2. 前端 `agent-front` nginx
- 任务状态轮询：`"GET /tender/tasks/[0-9a-f-]+ HTTP/1.1" 200`
- 项目/结果轮询：`"GET /tender/projects.* HTTP/1.1" 200`
- 健康检查：`"GET /health HTTP/1.1" 200`
- 静态资源加载：`"GET /assets/.* HTTP/1.1" 200`、`"GET /images/.* HTTP/1.1" 200`
- SPA 页面缓存命中：`"GET /contracts/tender-review HTTP/1.1" 304`

### G3. `cloudflared-mesh`
- 正常启动/连边缘：`Starting tunnel`、`Registered tunnel connection`、
  `Tunnel connection curve preferences`
- ICMP 能力不足但不影响 HTTP tunnel：`ICMP proxy feature is disabled`、
  `ping_group_range`
- QUIC 不稳但自动降级 HTTP/2：`QUIC connection failed`、
  `Allow outbound QUIC traffic on port 7844 or use HTTP2`、
  `Environment ready with degraded transport`
- 旧 origin 不通的重复噪音：`Unable to reach the origin service.*dial tcp .*:5173: i/o timeout`

不要排除这类上传失败信号，除非已明确改用本地隧道：`Incoming request ended abruptly: context canceled`
且 `dest=https://agent.guoker.org/tender/projects/.*/evaluate`。

---

## H. 演示环境双容器完整文档/OCR 重打包 Runbook（0730b2）

> 本节是执行清单，不代表已经部署成功。目标镜像为 `agent-backend:0730b2`、
> `agent-front:0730b2`，容器名继续固定为 `agent-backend`、`agent-front`。演示机自己的 env、
> Compose、知识库和运行数据是权威配置，禁止拿仓库文件覆盖。

### H1. 同步前冻结保护面

1. 在目标项目目录记录以下路径的存在性、权限和 SHA-256；目录清单也保存到本次 evidence 目录：
   `.env*`、Compose 文件、`knowledge/`、`data/`、`logs/`、`backups/`、`docker-export/`、
   `.claude/settings.local.json`，以及执行前枚举出的全部 `.claude/*.local.*`。
2. 只同步代码和构建资产。`server/`、`shared/` 可分别对自己的目标子目录使用 `--delete`；
   `scripts/` 只同步格式清单生成器、真实格式 smoke、宏安全验收脚本及
   `document_format_fixtures/`，不得把临时 evidence 或其他运维脚本混入；
   `.claude/` 必须带 `--exclude=settings.local.json`，并把上一步枚举的每个 `*.local.*` 加入
   protect filter；`agent-front/` 保护 `.env*`、`node_modules/`。根目录只逐文件更新
   `Dockerfile`、`pyproject.toml`、`uv.lock`、entrypoint 等构建文件。
3. 禁止以项目根为 `--delete` 目标，禁止 `--delete-excluded`。不得同步仓库的 env、Compose、
   `knowledge/`、`data/`、`logs/`、`tests/`、`.ai_state/`、`backups/`、`docker-export/`、归档包或缓存。
4. 每组 rsync 先执行 `--dry-run --itemize-changes` 并保存输出。机器检查输出中上述保护路径没有
   `*deleting`；出现任何一项就停止。正式同步后重新计算保护面 SHA-256，与同步前逐项比对。

`.dockerignore` 同时必须排除 `.git/.ai_state/tests/knowledge/data/logs/backups/docker-export/.env*`、
`.venv`、`node_modules`、缓存和 `*.tar*`；否则历史导出镜像会把构建上下文膨胀到数 GB。

### H2. 替换前建立可恢复的当前镜像证据

1. 从运行容器解析真实 image ID，不以 tag 猜测：

   ```bash
   docker inspect agent-backend agent-front > "$EVIDENCE_DIR/containers-before.json"
   BACKEND_OLD_ID=$(docker inspect agent-backend --format '{{.Image}}')
   FRONT_OLD_ID=$(docker inspect agent-front --format '{{.Image}}')
   docker image inspect "$BACKEND_OLD_ID" "$FRONT_OLD_ID" > "$EVIDENCE_DIR/images-before.json"
   ```

2. 保存容器日志、env **键名**（值脱敏）、挂载、网络、端口、restart policy、CPU/内存限制和
   `docker compose config`。确认 LiteLLM、Milvus 等不在本次重建服务列表。
3. 用时间戳创建临时 backup tag，并从这些真实 image ID 新鲜导出两个旧镜像：

   ```bash
   docker image tag "$BACKEND_OLD_ID" "agent-backend:backup-$STAMP"
   docker image tag "$FRONT_OLD_ID" "agent-front:backup-$STAMP"
   docker image save "agent-backend:backup-$STAMP" -o "$EVIDENCE_DIR/agent-backend-old.tar"
   docker image save "agent-front:backup-$STAMP" -o "$EVIDENCE_DIR/agent-front-old.tar"
   sha256sum "$EVIDENCE_DIR"/*.tar > "$EVIDENCE_DIR/SHA256SUMS"
   sha256sum -c "$EVIDENCE_DIR/SHA256SUMS"
   ```

4. 使用临时 `--data-root`/独立 Docker socket 启动一次性 daemon，在隔离环境中分别 `docker load`，
   再 inspect 加载后的 image ID/架构；结果必须能映射回 `BACKEND_OLD_ID`、`FRONT_OLD_ID`。
   验证完成后停止一次性 daemon，再删除它的临时目录。不要用正式 daemon 中已有 tag 代替 load 验证。

### H3. 构建与依赖 smoke

1. 用演示机现有前端 env 执行前端 build，再分别构建 ARM64 镜像：

   ```bash
   cd agent-front && bun install --frozen-lockfile && bun run test && bun run build && bun run lint
   cd ..
   docker build -f agent-front/deploy/Containerfile.agent-backend -t agent-backend:0730b2 .
   docker build -f agent-front/deploy/Containerfile.agent-front -t agent-front:0730b2 .
   ```

2. 后端镜像内验证架构和固定依赖：xlrd、pyxlsb、python-pptx、pdfplumber、PaddlePaddle 3.2.2、
   PaddleOCR 3.7.0、PaddleX 3.7.2 均可 import；`command -v ps`（来自 `procps`）、`soffice --version`、
   `tesseract --list-langs`（含 `chi_sim`、`eng`）、`fc-list`（含 Noto CJK、Liberation2）实际成功。
   `OCR_VL_USE_PADDLE_PIPELINE=0` 是 ARM64 默认；import 成功不能冒充本地 Paddle pipeline smoke。
3. 显式设置 `OCR_VL_USE_PADDLE_PIPELINE=1` 的启动 smoke 单独记录，失败不得影响默认远端 LiteLLM
   路径的诊断，但不得宣称本地 layout pipeline 可用。

### H4. 重建固定名称容器

1. 只在目标机现有部署定义中把前后端 image tag 改为 `0730b2`；其余 env、挂载、网络、端口、
   restart policy 和资源限制保持 H2 快照不变。
2. 仅重建 `agent-backend`、`agent-front`，不得连带重启 LiteLLM、Milvus、OpenProject 等服务。
3. 重建后再次 inspect 并与 H2 做结构化 diff：固定容器名、三个运行挂载
   `/app/knowledge`、`/app/data`、`/app/logs`、网络、资源限制、restart policy、env 键集合必须一致；
   只有 image ID/tag 和预期代码版本允许变化。
4. 验证后端 `/health`、前端 `/` 均 HTTP 200，日志无 OCR/LibreOffice/Tesseract 启动错误。
   任一步失败，按 H2 保存的 inspect 与旧 image ID 恢复两个固定名称容器；旧归档保留。

### H5. 真实格式/OCR 矩阵

准备每种 canonical 后缀恰好一个真实 fixture（包含中文、表格/正文；至少一份扫描件）。生成物检查在
目标项目的**源码检出**中运行；成品后端只携带前端 `dist`，不携带 TypeScript 源码，不能在镜像内跑
`generate_document_formats.py --check`。其余 smoke 在新后端容器的同一 env/网络下运行：

```bash
set -o pipefail
(cd "$PROJECT_DIR" && python3 scripts/generate_document_formats.py --check)
# The former single document-format-smoke.json is replaced by two engine-specific records below.

# Round 1: use the demo environment's real LiteLLM/PaddleOCR-VL endpoint.
python scripts/smoke_document_formats.py \
  --fixtures-dir scripts/document_format_fixtures \
  --expect-engine openai-compatible-vlm \
  --expect-degraded false \
  --require-ocr-suffix .png \
  | tee "$EVIDENCE_DIR/document-format-smoke-vlm.json"
VLM_SMOKE_RC=${PIPESTATUS[0]}
test "$VLM_SMOKE_RC" -eq 0

# Round 2: force the remote endpoint to fail, proving the real Tesseract fallback.
OCR_VL_SERVER_URL=http://127.0.0.1:1/v1 \
OCR_VL_TIMEOUT=2 \
python scripts/smoke_document_formats.py \
  --fixtures-dir scripts/document_format_fixtures \
  --expect-engine tesseract \
  --expect-degraded true \
  --require-ocr-suffix .png \
  | tee "$EVIDENCE_DIR/document-format-smoke-tesseract.json"
TESS_SMOKE_RC=${PIPESTATUS[0]}
test "$TESS_SMOKE_RC" -eq 0

python - \
  "$EVIDENCE_DIR/document-format-smoke-vlm.json" \
  "$EVIDENCE_DIR/document-format-smoke-tesseract.json" <<'PY'
import json
import sys

expected = [
    (sys.argv[1], "openai-compatible-vlm", False),
    (sys.argv[2], "tesseract", True),
]
for evidence_path, expected_engine, expected_degraded in expected:
    with open(evidence_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["status"] == "ok", payload
    expectation = payload["expectation"]
    assert expectation == {
        "engine": expected_engine,
        "degraded": expected_degraded,
        "required_ocr_suffixes": [".png"],
        "cache_enabled": False,
    }, expectation
    formats = payload["formats"]
    assert formats and all(item["status"] == "ok" for item in formats), formats
    assert all(item["from_cache"] is False for item in formats), formats
    required = {item["suffix"]: item for item in formats if item["suffix"] == ".png"}
    assert set(required) == {".png"}, required
    for item in required.values():
        assert item["route"] in {"ocr", "convert"}, item
        assert item["engine"] == expected_engine, item
        assert item["degraded"] is expected_degraded, item
        assert item["ocr_expectation"] == "matched", item
PY

python scripts/verify_office_macro_safety.py \
  --fixture scripts/document_format_fixtures/macro-on-open.odt \
  --evidence "$EVIDENCE_DIR/office-macro-safety-demo-arm64.json"
```

smoke 必须覆盖 `.txt/.csv/.md/.json/.tsv`、全部图片、`.doc/.docx`、`.xls/.xlsx/.xlsm/.xlsb`、
`.ppt/.pptx`、`.odt/.ods/.odp`、`.pdf`。每个文件都要通过上传 magic、canonical classify、
native/convert/OCR 路由并产出非空底稿；至少一份扫描 PDF/图片实际经过远端 VLM，模拟远端失败时
再证明 Tesseract 降级可用。两轮都必须完成全部 canonical 后缀，逐项记录 `from_cache=false`；
`--require-ocr-suffix` 指定的关键 OCR fixture 还必须逐后缀匹配预期 `engine/degraded`。可重复
传入该参数扩大关键集。不得用“包已安装”、“route 字段正确”或旧缓存代替真实非空底稿。

仓库中的 `scripts/evidence/office-macro-safety-local-arm64.json` 只证明本机 Darwin arm64、
LibreOfficeDev 的宏禁用与进程清理结果，不代表演示机或成品镜像已通过。上面的宏验收必须在目标
Debian ARM64 后端成品镜像内重新执行；结果为 `status=ok`、`side_effect_created=false`、
`profile_removed=true`、`residual_processes=[]` 前，不得宣称远端宏安全验收成功。

### H6. 新镜像导出与临时 tag 清理

1. 所有健康、配置漂移和真实矩阵验证通过后，从**运行容器解析出的新 image ID**新鲜导出到目标
   项目 `docker-export/`，文件名包含 `0730b2` 和架构；写 SHA-256，并用 H2 相同的隔离 daemon
   执行 load/inspect 验证。
2. 确认导出 ID 等于运行中的 `agent-backend`、`agent-front` image ID，且两个归档都可加载后，
   只删除 `agent-backend:backup-$STAMP`、`agent-front:backup-$STAMP` 两个临时 backup tag。
3. 不删除旧镜像 tar、SHA、inspect、日志或恢复说明；它们在观察期结束前持续保留。不得执行
   `docker image prune -a`，不得删除 `0730b1`/旧 image ID，除非另有明确的观察期清理授权。

隔离 load 的 data-root 必须放在容量足够的项目磁盘并优先使用 `overlay2`。不要在小容量 tmpfs 上用
`vfs` 验证多层大镜像：`vfs` 会展开每一层，归档只有约 2.3 GB 也可能耗尽 31 GB tmpfs。

### H7. 2026-07-30 实际部署结果与教训

本次已完成 `agent-backend:0730b2` / `agent-front:0730b2` 部署，运行 image ID 分别为
`sha256:2f7067aee290...`、`sha256:e66a6de49d3f...`。固定容器名、env 键集合、挂载、网络、端口、
CPU/内存、restart policy 与旧容器严格一致；后端 `/health` 和前端 `/` 均为 HTTP 200。

- 演示机配置未被仓库覆盖：`MODEL_BASE_URL=http://litellm:4000`、`OCR_CLOUD=0`、
  `OCR_VL_SERVER_URL=http://litellm:4000/v1`、`OCR_VL_MODEL_NAME=paddleocr`、
  `OCR_VL_USE_PADDLE_PIPELINE=0`。env、Compose、knowledge/data/logs 与本地私有设置均保留。
- 运行中后端的两轮 24 格式矩阵全部成功且 `from_cache=false`：默认轮 PNG 为
  `openai-compatible-vlm/degraded=false`，故障注入轮为 `tesseract/degraded=true`。可选
  `OCR_VL_USE_PADDLE_PIPELINE=1` 启动探测也成功创建 `PaddleOCRVL`。
- Debian ARM64 宏安全验收为 `status=ok`、`side_effect_created=false`、
  `profile_removed=true`、`residual_processes=[]`。最初成品缺 `ps` 导致验收脚本无法检查残留进程，
  因此两个后端 Dockerfile 都固定安装 `procps`；只装 LibreOffice 并不等于验收环境完整。
- 目标 Docker legacy builder 不支持 `--progress=plain`，且默认 `docker0` 缺失；构建改用
  `docker build --network=host`，没有为构建重启正式 Docker daemon。
- `-p 9999:9999` 与 `-p 0.0.0.0:9999:9999` 对外行为相同，但 inspect 的 `HostIp` 字面不同。
  为让参数 diff 真正零漂移，重建时显式写出 `0.0.0.0`。
- 新镜像导出位于项目 `docker-export/`：后端 SHA-256
  `fe64b23ba82d9a52abaa887cde6d0979070ca35f37bf42de6641167a64d4b44f`，前端 SHA-256
  `5dddd68ea5244fa43a1facf2f28887fddf0b3d33a21733d75304b548e0eacf8c`；隔离 `overlay2` daemon
  load 后 ID/架构一致。临时 backup tag 已删除，`0730b1` 标签与旧 tar 继续保留。
- 完整证据目录：`/opt/application/audit-agent/backups/pre-0730b2-20260730-203137/deploy-evidence/`。
