# Learning · 给 store 加必填列时，回归子集按"模块消费面"选会漏掉脚本调用方

- 日期: 2026-08-17
- 类型: learning

## 事故

F1/F3 修复给 `rag_chunks`/`rag_chunk_scan` 加了必填列 `source_file`（`insert_rows` 的具名绑定
`:source_file` 随之成为硬要求）。修复者跑了相当充分的回归：派工子集 160 passed，又因改到
`corpus`/`rag`/`rag_store` 三个共享模块**主动加跑消费面** 225 passed，ruff 净。

仍漏掉 `scripts/measure_tender_recall.py`——它**自己手搓 chunk dict**（不走 `build_chunks`），
少一个键即 `sqlite3.ProgrammingError: You did not supply a value for binding parameter
:source_file`。合并后全量回归才暴露：**2 条新增失败**（`test_tender_recall_measurement.py`）。

## 为什么"加跑消费面"没抓到

消费面是按**模块 import 关系**选的（谁 import 了 corpus/rag/rag_store），
而漏掉的这个调用方特征是：

- 在 `scripts/` 不在 `server/`，容易被"生产链路"心智排除；
- **自己构造行 dict**，不经过被改的 `build_chunks`——所以 import 图上它与改动点的距离
  看起来很远，实际却直接依赖 store 的**列契约**。

## 判据（下次照做）

> 改的是**数据契约**（表列、必填键、schema、TypedDict 字段）时，回归面按
> **"谁构造这个结构"** 选，不按 "谁 import 这个模块" 选。

具体动作：`grep -rn "<写入函数名>" --include="*.py" server scripts tests`，
逐个确认调用方是否手搓入参；`scripts/` 与 `tests/` 的手搓构造点是重灾区。

## 处置

`_build_corpus()` 显式补 `source_file`（构造语料单源文件，头串即文件名），
**没有**把 store 层改成"缺键则填 NULL"——那会让生产链路忘记带来源时静默写空，
违反边界内 fail-fast（铁律[反过度工程]）。相关：[[tender-generality-discipline]]
