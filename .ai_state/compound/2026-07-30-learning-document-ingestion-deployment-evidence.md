---
doc_type: learning
slug: "document-ingestion-deployment-evidence"
created: "2026-07-30"
sprint_slug: "2026-07-30-demo-full-doc-ocr"
severity: "P1"
status: executed
---

# Learning: document-ingestion-deployment-evidence

## 现象

拆分前后端镜像后，代码仍能直读现代 Office，但演示后端缺 xlrd/pyxlsb/python-pptx、
LibreOffice、Tesseract 与 Paddle 依赖；扫描标书、旧 Office 和 PPT 会从“部分支持”退化成识别失败。
同时，单轮格式 smoke 可能命中旧缓存，或只证明 VLM/Tesseract 其中一条路径，制造假绿。

## 根因

“支持格式”不是安装包清单，而是上传校验、native reader、Office 转换、VLM、Tesseract、缓存和目标
配置共同构成的运行时契约。仅检查 import 或只跑一份样例无法证明成品镜像接缝；页锚也可能把空 OCR
包装成表面非空。部署同步若覆盖 `.env`/Compose/knowledge/data/logs，又会把代码升级变成环境事故。

## 教训

格式/OCR 能力必须以目标成品镜像中的真实双路径、禁缓存、非空正文 hard gate 验收；部署时把目标配置
和运行数据视为受保护输入，而不是仓库产物。

## 通用化

1. manifest 只声明候选格式；每个后缀仍要通过 `magic → extract_one → 非空底稿`。
2. VLM 轮使用可达 endpoint；Tesseract 轮故意让 VLM 不可达，两轮均要求预期 engine/degraded。
3. smoke 期间关闭缓存，并对每个完成单元硬断言 `from_cache=false`；degraded 结果不入缓存。
4. 有效正文检查要剥离页锚；空 stdout、空白或只有 `【第 N 页】` 必须失败。
5. 代码同步显式排除 `.env*`、Compose、knowledge/data/logs、备份/导出目录和本地私有配置；
   同步前后比较目标配置 hash。
6. 替换前按实际 image ID 导出双镜像并验证 SHA/load；成功后再导出新镜像，临时 backup tag 可删，
   原旧版本 tag 保留观察期回滚。

## 相关引用

- 实现：`server/ocr/engine.py`、`server/ocr/pipeline.py`、`scripts/smoke_document_formats.py`
- 部署门禁：`deploy/TROUBLESHOOTING.md`
- 架构现状：`architecture/system-document-ingestion.md`
- LibreOffice CLI：<https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html>
- PaddleOCR 安装：<https://github.com/PaddlePaddle/PaddleOCR/blob/2661c7c0ef5c613e8f93c6e93b2e052399f0f854/docs/version3.x/installation.en.md#L9-L51>
- Pillow 校验：<https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.verify>
