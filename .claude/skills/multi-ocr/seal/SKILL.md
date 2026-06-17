---
name: multi-ocr-seal
description: 印章/签章专项识别——定位红章区域并识别章内文字(圆/椭圆/方/弯曲)，印章压字硬指标兜底
---

# 印章 / 签章识别

印章、手写签名、电子签章是**三种不同技术**，按需选（详见 `references/engines.md`）：

| 你要的 | 本质 | 扫描件适用 | 方案 |
|---|---|---|---|
| 印章 / 公章 | 图像识别 | ✅ | PaddleX 印章产线（弯曲章文字）/ 商用印章 API |
| 手写签名 | 检测 + 真伪验证（非 OCR） | ⚠️看需求 | YOLO 检测 + 孪生网络 |
| 电子签章 | PKI 验签（证书+时间戳） | ❌ 扫描件无嵌入证书 | iText+BouncyCastle，本场景多不适用 |

## 调用

实现：`server/ocr/engine.py:recognize_seal`，输出每枚印章 `bbox` / `shape` / `text` / `color` / `confidence`。

## 用途

- 印章存在 = "已盖章/已审批"的事实信号，写入证据链。
- 章内文字低置信（印章压字常见）→ 标 `low_confidence`，交人工，**不强判**。
- 硬指标且 PaddleX 不达标 → 切商用「印章擦除后识别」（阿里读光，支持私有化），见 `references/engines.md`。
