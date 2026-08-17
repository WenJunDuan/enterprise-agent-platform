# trick · /tmp 下的诊断脚本会遮蔽 stdlib，报错指向完全无关的库

## 现象

`uv run python /tmp/diag_retrieval.py` 报的是 jsonschema 初始化失败：

```
referencing.exceptions.NoSuchResource: 'http://json-schema.org/draft-03/schema#'
```

而 `uv run python -c "import jsonschema"` 单独跑是好的。另外还先打了几行莫名其妙的输出
（`chapters: 3 ['商务标', '技术标', '资格证明']`）。

## 原因

Python 把**脚本所在目录**放进 `sys.path[0]`。历次会话在 `/tmp` 留下过 `struct.py`、`hd.py`、
`mutate.py` 等一次性脚本，其中 `/tmp/struct.py` 遮蔽了 stdlib 的 `struct`——它被 import 时
执行了自己的演示代码（那几行莫名输出），然后下游依赖 `struct` 的库拿到错的模块，报错却落在
jsonschema/referencing 身上，与真因隔了三层。

## 做法

诊断脚本开头显式把脚本目录踢出 `sys.path`：

```python
REPO = Path("/Users/mi_manchi/workspace/enterprise-agent-platform")
# /tmp 里有历史遗留的 struct.py 等文件, 会遮蔽 stdlib（脚本目录默认进 sys.path[0]）
sys.path[:] = [p for p in sys.path if p not in ("", str(Path(__file__).resolve().parent))]
sys.path.insert(0, str(REPO))
```

注意 macOS 上 `/tmp` 是 `/private/tmp` 的符号链接：过滤要用
`Path(__file__).resolve().parent`（得到 `/private/tmp`），写字面量 `"/tmp"` 匹配不上。

## 判据

报错落在一个你没动过、且单独 import 正常的库上 → 先看 `sys.path[0]` 里有什么。
