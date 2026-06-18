---
doc_type: decision
slug: "front-domain-navigation"
created: "2026-06-19"
sprint_slug: "2026-06-18-front-framework-migration"
status: accepted
deciders: ["user", "codex"]
---

# Decision: front-domain-navigation

## 背景 (context)

迁移后的前端从通用后台模板转成业务操作平台。旧侧边栏包含仪表盘、
系统菜单和技术化入口，不符合当前用户要测试的业务流程。

## 选项 (options considered)

### 选项 A: 保留模板菜单
- 优点: 改动少，系统管理页面都可见。
- 缺点: 入口杂，用户第一眼看不到真实业务域。

### 选项 B: 按业务域静态整理
- 优点: 首屏只展示真实业务入口，登录后路径清晰。
- 缺点: 后端动态菜单暂时不参与主导航。

### 选项 C: 混合业务域和系统菜单
- 优点: 系统管理入口仍在侧边栏。
- 缺点: 容易再次把业务入口和后台配置混在一起。

## 决定 (decision)

采用选项 B。侧边栏固定为三个域组：`发票审核`、`OCR 识别`、`合同审查`。
每个域组下只放该域的具体菜单入口：`发票审核清单`、`OCR 识别`、
`合同审查清单`。系统布局和主题配置放到右上角配置抽屉。

## 权衡 (trade-offs)

接受暂时不在侧边栏展示后台系统管理菜单。若后续需要恢复，应新增独立
系统管理组，不把它混入业务域。

## 影响 (consequences)

- 对本次 sprint: dashboard 和旧账号密码入口从主体验中移除。
- 对后续 sprint: 新业务入口应先归入业务域，再考虑是否需要独立页面。
- 对 architecture/: 暂不触发架构档更新；这是前端导航产品决策。
