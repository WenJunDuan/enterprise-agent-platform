# Issue Report — Tender Score Summary

## 现象

- 用户反馈评标结果里扣分/得分计算疑似有问题。
- 最后总结出现内部字段或英文技术词，不适合业务人员直接阅读。
- 需要先对比招标文件本身应抽多少评分项，再看 Mac mini 已落库结果。

## 复现与对比

- 本地文件：`knowledge/external/张謇企业家学院/张謇企业家学院网络学院直播间建设项目公开招标文件.doc`
- 原生读取结果：`kind=word route=native handler=legacy_word chars=39058`
- 招标原文评分表：商务技术 8 项，共 70 分；价格 1 项，30 分；顶层合计 9 项，100 分。
- 本地 `tender-extract-info` 抽取：9 项，满分合计 100。
- Mac mini 当前数据库无张謇项目记录；最新可对比项目为川姜花苑：
  - 招标文件 criteria：10 项，满分 100。
  - 两条评标结果 scoring：均 10 项。

## 失败样例

Mac mini 结果 `737b2449-63e3-4cef-93b0-89ea922564ad`：

- `scoring[]` 非空得分合计：5.00。
- `explanation` 写成“施工组织设计初评5.05/6 + 业绩0/2”。
- `explanation` 出现 `cross_bid变量`。

