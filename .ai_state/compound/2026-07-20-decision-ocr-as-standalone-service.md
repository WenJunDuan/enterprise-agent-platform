---
doc_type: decision
slug: ocr-as-standalone-service
date: 2026-07-20
status: leaning  # 用户 2026-07-20 倾向,待部署机窗口+模型池数据回来正式确认开工
supersedes_scope_of: D4 (l2-model-routing)
---

# 决策：OCR 路由 + 模型池拆为独立服务，本项目只调一个 API

## 背景

用户 2026-07-20 提出：OCR 的多模型路由是否新开一个独立项目去做，模型用 paddle 系，
**直读功能也丢进去**，对本项目（enterprise-agent-platform）而言 OCR 就是「一个 API」。

## 决策（主 agent 推荐 = YES）

把 **直读(native) + 路由(能力画像/按置信度自动升降级) + 模型池(PaddleOCR/VL/Unlimited-OCR/seal)**
全部内聚到一个独立可部署的 OCR 服务，对外暴露单一 API：`文件字节 → 结构化底稿(带页锚)`。
本项目 `server/ocr/` 的进程内调用（`engine.recognize` / `extract_dir` / `ocr_preprocess_block`）
改为对该服务的 HTTP 调用。

## 为什么

1. **边界已存在**：2026-07-15 已定「ocr 降为服务层，tender/audit→ocr 单向」
   （[[2026-07-15-decision-ocr-service-layer]]）。进程内服务层 → 网络服务是同一边界的延伸。
2. **依赖/生命周期隔离**：paddle/pymupdf/GPU 模型与审核 FastAPI 绑定是负担；
   代码已记本地 layout predictor 在 arm64 容器 native 崩溃被迫走远端 VLM（engine.py:468）。
   拆出后主服务轻量，OCR 服务贴 GPU 独立扩缩容。
3. **直读必须同域**：「能直读绝不 OCR」是路由梯 T0 层，本身即路由判断；
   若直读留调用方、路由在服务，则「何时直读 vs 调哪个模型」两头都有 = 路由逻辑泄漏回调用方。
   直读+路由+模型池同域 → 调用方只发字节收底稿，真正单一 API。

## 硬约束（拆分时不可丢）

- 页锚 `【第N页】` 全链路保真（evidence-resolution 红线）——API 契约必须带真实页号或 null。
- 返回结构对齐 `doc-structure.schema.json`（D6 已定的结构化底稿契约），不新造格式。
- 新服务种子 = 现 `server/ocr/`（paddle 接入 / classify / native 直读可搬），
  新增层 = EngineRegistry + 能力画像 + 按置信度自动升降级（五级梯见
  [[2026-07-02-decision-ocr-routing-ladder]]）。不从零重写 paddle 集成。

## 对 roadmap 的影响

- **D4 重定义**：从「进程内 EngineRegistry」→「建独立 OCR 路由服务 + 本项目 ocr 调用改指向其 API」。
  更大但更干净。正式开工前置不变（部署机 V4Pro 基线锁硬门 + 模型池实测能力画像）。
- **D9 不阻塞**：D9 流式 = 平台 job 端点 + 前端渐进渲染，现包进程内 OCR；
  将来 OCR 拆服务后 `/ocr/jobs` 数据源从进程内 pipeline 换成代理 OCR 服务流，
  流式契约 + 前端 T4 全复用。故先做 D9，不等 OCR 拆分。

## 待确认（D4 窗口）

- 独立 repo vs 本 monorepo 内独立可部署单元（倾向独立 repo：独立依赖/GPU/生命周期）。
- API 形态：同步 `文件→底稿` vs 页级流式（若 D9 已在平台侧做流式，OCR 服务可先同步，二期再流式）。
