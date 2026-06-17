# 引擎调用约定与端点

> ⚠️ 具体 API 签名以你实际安装的 paddleocr / paddlex 版本与部署的 serving 为准。
> 下方按官方文档实现；**POC 阶段须对真实文件/端点核对返回结构后定稿**（铁律[出处优先]）。

## 主引擎：PaddleOCR-VL

- 模型：默认 `PaddleOCR-VL-1.6`（2026-05，OmniDocBench v1.6 = 96.33，当前 SOTA；Apache-2.0）。
- 完整 pipeline = PP-DocLayoutV2 版面分析 → VLM 识别。**勿只打裸 VLM 端点**，否则掉精度/幻觉（官方提示）。
- 输出：每页 Markdown + JSON（含表格、分离的印章/图、阅读顺序）。
- 部署（vLLM 加速，需与 paddleocr 分开 venv，避免依赖冲突）：
  ```
  paddleocr install_genai_server_deps vllm   # 首次：装 vLLM 后端依赖（CUDA 12.6）
  paddleocr genai_server --model_name PaddleOCR-VL-1.6-0.9B --host 0.0.0.0 --port 8118 --backend vllm
  ```
- 环境变量：
  - `OCR_VL_PIPELINE_VERSION`（默认 `v1.6`）；`OCR_VL_BACKEND`（默认 `vllm-server`）
  - `OCR_VL_SERVER_URL`（**统一 litellm 网关** OpenAI 端点，如 `http://litellm:4000/v1`，与 audit 同地址）
  - `OCR_VL_MODEL_NAME`（litellm 里为 PaddleOCR-VL 注册的 `model_name`；pipeline 发 `model=该名` → litellm 转发到 VLM 上游）
  - 注：仅 **VLM 阶段** 走网关；**版面分析(PP-DocLayoutV2) 在容器内本地跑**，故镜像需装 paddlepaddle+paddleocr。
- 硬件：官方列支持 NVIDIA / 华为昇腾 NPU / 昆仑芯 / CPU(慢)。昇腾上须 POC 验证目标版本可跑。
- 文档：https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html
- 备选主引擎：MinerU2.5-Pro（端到端、组件更少、表格强），如嫌两段式部署件数多可对比。

## 印章引擎

- 开源：PaddleX 印章文本识别产线（PP-OCRv4，支持圆/椭圆/方/弯曲章文字，输出文字+多边形坐标+置信度）。
  - 环境变量 `OCR_SEAL_PIPELINE`（默认 `seal_recognition`）。
  - 文档：https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/seal_recognition.html
- 商用（印章压字硬指标兜底，均支持私有化）：
  - **阿里云读光**：印章重叠场景 +「印章擦除后识别」——最对症印章遮挡正文。
  - 百度印章识别 / 华为云 RecognizeSeal / 合合 INTSIG / 来也 IDP。

## 三类「签章」区分

- **印章/公章** → 图像识别（上方印章引擎）。
- **手写签名** → 检测(YOLO)+真伪验证(孪生网络/SVM)，另一套，非 OCR。
- **电子签章(数字签名)** → PKI 验签(iText+BouncyCastle / Adobe)；**扫描件无嵌入证书，通常不适用**。
  别把扫描红章当作有法律效力的电子签章。

## 依赖

- OCR venv：`pip install 'paddleocr[doc-parser]>=3.4.0'` + `paddlex`（印章产线）；vLLM 单独 venv。
- 原生直读（服务 venv）：`openpyxl`（Excel）、`python-docx`（Word）、`pypdf`（PDF 文本）。
