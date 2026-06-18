---
name: classify-fix-exposes-latent-bug
description: 修一个分诊判据让从没真跑过的下游分支首次执行，连带暴露预存 bug——改判据必须顺藤查下游消费方
metadata:
  type: learning
---

## 背景

OCR 分诊 `classify._probe_pdf` 用 `has_text = fonts>0 and kb/page<200` 判 PDF 文本层。
`knowledge/ocr` 全部 10 个真实 PDF 中，9 个扫描件 `fonts=0`、1 个电子备案证 `fonts=8`
但单页 378KB > 200KB 阈值 → **全部**被判 `ocr`。即 native PDF 分支（`route=native` →
`native.read_pdf_text`）**从未被任何真实文件触发过**。

## 现象

把判据改成 `has_text = fonts>0`（修复电子证照误判）后，备案证首次走 native 分支，
立刻在 `pipeline._render_body` 崩：`TypeError: 'int' object is not iterable`。

## 根因

字段语义撞名：`classify` 给 result 塞 `pages`（int 页数），而 OCR 引擎产物里 `pages`
是 `list[每页 {markdown}]`。`_render_body` 假设 `pages` 是 list 直接迭代。native PDF
产物 = classify(pages=int) + read_pdf_text(blocks)，于是迭代整数崩。这个 bug 自 native
PDF 分支存在起就在，但因分诊从没让任何文件走到 native PDF，一直是死代码、从没暴露。

## 教训

- **改一个分流 / 判据，等于可能首次激活下游某条死分支**。修 classify 前要顺藤问：改完后
  哪些 route 会第一次被真实数据命中？那些分支的下游（native_read → pipeline 渲染）真跑通过吗？
- **同名字段跨模块语义必须一致**。`pages` 在 classify（页数 int）和 engine（每页 list）
  两处不同义，是定时炸弹。已改 classify 为 `page_count` + `_render_body` 加 `isinstance` 守卫。
- **测试要覆盖「分诊 + 下游渲染」的连通路径**，不只是 classify 单元判定。补了
  `test_ocr_pipeline.py` 锁 page_count(int) / pages(list) 两种语义。
- 真实样本分布会掩盖 bug：10 个样本恰好没有一个能触发 native PDF，单测又用 minimal fake
  bytes 各测各的，导致连通路径长期没人走。

**Why:** 这是「修一处暴露一处」的典型；复利价值在于**改判据 / 分流时的下游连通性检查习惯**。
**How to apply:** 改任何 classify / router / dispatch 逻辑时，列出「改后新增被命中的分支」，
对每条手动走一遍下游或加连通测试。关联 [[project_ocr_form_fill]]。
