# Session Log — 2026-06-19-contract-tender-review-mock

## 2026-06-25 16:45 (checkpoint)

- 做了: 修复招投标两个投标人同时评审时分数错位的问题；投标人 tab 分数按
  request/task/claim 对应自己的结果，排名按综合得分降序生成。
- 做了: 评分汇总补充扣分/未得分、未计分项的分数和项目名称，报告页与分析页
  都能展示受影响评分项。
- 做了: 头像菜单承接主题、布局、个人资料、系统管理和退出登录；左侧底部用户
  信息整行也改为同一菜单触发区。
- 做了: 菜单管理新增侧边栏显示控制，可隐藏整个业务分组，也可隐藏单个菜单项；
  设置通过 localStorage 保留。
- 做了: 系统管理路由和用户/角色/菜单/部门/字典/文件页面改为本地 JSON 或本地
  no-op 数据路径，不再请求缺失的 `/system/*` 接口。
- 状态: stage=ship，path=System。当前提交范围限定为 `agent-front` 代码和
  `agent-front/.ai_state`；根目录 `.ai_state`、`.claude`、后端和根级 tests 的
  既有未提交改动保持未 staged。
- 验证: `bun run lint` 通过；`bun run test` 43 pass；`bun run build` 通过，仅
  Vite large chunk warning；`/system/menu`、`/system/user`、`/system/role`、
  `/system/dept`、`/system/dict`、`/system/file` HTTP 检查均为 200；
  `git diff --check -- agent-front` 通过。
- 下次接续: 若系统管理后续需要真实接口，再从各 `features/system/*/api.ts`
  的本地 JSON 数据层替换为后端适配，不改页面组件结构。
- blocker: 无。

## 2026-06-24 02:20 (checkpoint)

- 做了: 将用户手测发现的招投标前端问题落到 `agent-front` 并推送
  `6b84ca3 fix(front): polish tender report flow` 到 `origin/main`。
- 做了: 评审入口已从旧 `/contracts/tender-review` 收敛为
  `/contracts/tender/list`，详情/报告共用 `/contracts/tender/detail` 并通过
  `view=analysis|report` 区分；`/contracts/tender/history` 继续保留历史评审。
- 做了: `查看报告` 从分析中心和历史评审进入同一报告界面；报告页不会再被
  `activeEval` 恢复逻辑抢回“等待评审结果”的分析状态。
- 做了: 分项得分紧凑行改为稳定等高；点击中间列定位项时会滚动右侧证据面板。
- 做了: 清理 `knip` 查出的 unused files/dependencies，删除未使用组件、品牌图标、
  settings 表单、system placeholder、date picker，并移除 `date-fns` /
  `react-day-picker`。
- 状态: stage=ship，path=System，当前可见遗留只有根目录
  `.ai_state/_index.md` 的无关本地改动；`agent-front` 代码已推送并与
  `origin/main` 同步。
- 验证: `bun run lint` 通过；`bun run test` 39 pass；`bun run build` 通过，仅
  Vite large chunk warning；`git diff --check -- agent-front` 通过；`knip` 无
  unused files/dependencies，剩余 unused exports/types 暂保留。
- 下次接续: 若继续前端清理，先从 `knip` 剩余 exports/types 入手，逐个确认是否
  为 API/model 预留表面；不要批量删除。
- blocker: 无。
