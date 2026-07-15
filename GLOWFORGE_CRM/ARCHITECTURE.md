# GLOWFORGE CRM — 完整系统架构

> 最后更新: 2026-07-11
> 总文件: 219 个 Python 文件 / 71,844 行 / 65+ 数据库表 / 150+ API 端点

---

## 一、目录结构

```
GLOWFORGE_CRM/
│
├── app.py               # Flask 主程序入口 (9747 行, 端口 5789)
├── .env                 # 环境变量 / API Keys
├── .gitignore
├── CLAUDE.md            # 项目手册
├── ARCHITECTURE.md      # 本文件
├── crm_data.db          # SQLite 数据库
│
├── ai_engine.py         # 核心 AI 引擎 (2865 行)
├── database.py          # 数据库 (5408 行)
├── voice_engine.py      # TTS 语音
├── video_postprocessor.py
├── video_tool_server.py
├── health_watchdog.py
├── catalog_generator.py
├── review_queue.py
├── action_router.py
├── decision_engine.py
├── lead_state_engine.py
├── sales_state.py
├── sales_executor.py
├── conversion_tracker.py
├── deal_analyzer.py
├── lead_router.py
├── closing_engine.py
├── outreach_engine.py
├── recovery_engine.py
├── reentry_engine.py
├── campaign_engine.py
├── script_builder.py
├── revenue_engine.py
├── a_b_optimizer.py
├── price_optimizer.py
├── intent_weight_tuner.py
├── premium_catalog.py
├── region_engine.py
├── global_lead_router.py
├── revenue_dashboard_v5.py
├── factory_allocator.py
├── pl_engine.py
├── expense_engine.py
├── invoice_engine.py
├── budget_engine.py
├── margin_engine.py
├── pricing_lock.py
├── profit_guard.py
├── executive_dash.py
├── ai_evolution.py
├── multi_agent_team.py
├── assumption_engine.py
├── dashboard_engine.py
├── ai_customer.py
├── whatsapp_engine.py
├── whatsapp_server.py
│
├── safety/              # V0 安全治理层 (19 文件)
├── ai_engine/           # AI Agent 系统 (19 文件)
├── ai_overlay/          # AI 覆盖层 (16 文件)
├── ai_universe/         # V8 商业宇宙 (7 文件)
├── autonomous_org/      # V9 自治组织 (8 文件)
├── business_graph/      # 利润路径图谱 (2 文件)
├── commercial_reality/  # V5 商业现实层 (6 文件)
├── execution/           # V8 执行引擎 (7 文件)
├── publishing_manager/  # 视频发布管理 (5 文件)
├── strategy_engine/     # 增长策略引擎 (20 文件)
│
├── admin/               # 部署/运维脚本
├── scripts/             # 工具/测试脚本 (36 文件)
├── templates/           # HTML 模板 (8 文件)
├── knowledge/           # 行业知识库 (32 文件)
├── countries/           # 各国市场文化 (8 文件)
├── prompts/             # AI 提示词模板 (13 文件)
├── uploads/             # 上传文件
├── logs/                # 日志文件
└── tests/               # 自动化测试
```

---

## 二、九层递进架构 (V0-V9)

系统核心设计理念：**优雅降级** — 每个 V 层独立加载，任何一层失败不影响其他层运行。

### V0 — 安全层 (Safety Layer)

| 模块 | 文件 | 功能 |
|------|------|------|
| 执行防火墙 | `safety/execution_firewall.py` | AI 动作拦截 (ALLOW/BLOCK/MODIFY/FLAG/ESCALATE) |
| 状态注册表 | `safety/state_registry.py` | 统一状态视图 + 分歧检测 |
| 策略引擎 | `safety/policy_engine.py` | DB 规则引擎 (热加载) |
| 风控引擎 | `safety/risk_engine.py` | 6 维连续评分 0.0-1.0 |
| 内容审核 | `safety/content_gate.py` | 出站消息三级审核 |
| 审计日志 | `safety/audit_logger.py` | 结构化审计追踪 |
| 告警通道 | `safety/alert_channel.py` | 异常告警通知 |
| Agent 协调 | `safety/agent_coordinator.py` | 每客户互斥锁 + 主导 Agent 选举 |
| 统一升级引擎 | `safety/unified_escalation_engine.py` | SLA 违反检测 + 自动升级 |
| 约束因果记忆 | `safety/constraint_causal_memory.py` | V8.5-B 约束推导 |
| 业务执行门 | `safety/business_execution_gate.py` | 执行前 5 项安全检查 |

### V0-SAFETY 工作台 — 仪表盘

| 页面 | 路由 | 数据表 |
|------|------|--------|
| 今日工作台 | `/api/dashboard` | customers, orders, leads |
| 客户管理 | `/api/customers` | customers |
| 潜客管理 | `/api/leads` | leads |
| 跟进提醒 | `/api/leads/due-followup` | leads |
| 消息中心 | `/api/messages` | messages |
| 文件库 | `/api/media` | media |
| 产品 | `/api/products` | products |
| 产品目录 | `/api/catalog` | products |
| 报价计算 | `/api/calc` | — |
| 报价管理 | `/api/quotes` | quotes |
| 订单管理 | `/api/orders` | orders |
| 订单统计 | `/api/orders/stats` | orders |
| 获客分析 | `/api/leads/analytics` | leads |

### V3 — 自优化销售 (Self-Optimizing Sales)

| 模块 | 文件 | 功能 |
|------|------|------|
| A/B 测试 | `v3_opt/a_b_optimizer.py` | 多变量 A/B/C 实验 |
| 价格优化 | `v3_opt/price_optimizer.py` | 动态价格弹性优化 |
| 意图权重调优 | `v3_opt/intent_weight_tuner.py` | 意图权重自动调优 |
| 成交分析 | `crm/deal_analyzer.py` | 成交/流失模式分析 |
| 转化追踪 | `crm/conversion_tracker.py` | 转化漏斗度量 |
| 收入引擎 | `v3_opt/revenue_engine.py` | 加载 V3 优化配置 |

### V4 — 活动管理 (Campaign Management)

| 页面 | 文件 | 功能 |
|------|------|------|
| 活动管理 | `crm/campaign_engine.py` | 营销活动创建/跟踪/分析 |

### V5 — 全球收入OS (Global Revenue OS)

| 模块 | 文件 | 功能 |
|------|------|------|
| 区域概览 | `v5_global/region_engine.py` | 全球区域管理 + 汇率转换 |
| 销售团队 | `v5_global/factory_allocator.py` | 多工厂产能分配 |
| 市场定价 | `v5_global/global_lead_router.py` | 全球线索智能路由 |
| 全球仪表盘 | `v5_global/revenue_dashboard_v5.py` | V5 收入仪表盘 |
| 商业现实 | `commercial_reality/` | WhatsApp 多号轮转 + 订单履约 + 支付 |

### V6 — 财务智能OS (Financial Intelligence OS)

| 模块 | 文件 | 功能 |
|------|------|------|
| 损益表 | `v6_finance/pl_engine.py` | P&L 计算引擎 |
| 发票管理 | `v6_finance/invoice_engine.py` | 发票生成/追踪 |
| 费用管理 | `v6_finance/expense_engine.py` | 费用录入/审批/分析 |
| 预算控制 | `v6_finance/budget_engine.py` | 部门预算管控 |
| 现金流 | `v6_finance/margin_engine.py` | 利润分析引擎 |
| CEO 仪表盘 | `v6_finance/executive_dash.py` | 高管驾驶舱 |
| 利润守卫 | `v6_finance/profit_guard.py` | 利润底限保护 |
| 定价锁 | `v6_finance/pricing_lock.py` | 定价策略锁定 |

### V7 — AI 进化 (AI Evolution)

| 模块 | 文件 | 功能 |
|------|------|------|
| AI 测试中心 | `v7_ai/ai_evolution.py` | AI 回复质量评测 + 自进化 |
| AI 进化管理 | `v7_ai/multi_agent_team.py` | 多 Agent 团队协作 |
| 假设引擎 | `v7_ai/assumption_engine.py` | 客户假设推导 |
| 仪表盘引擎 | `v7_ai/dashboard_engine.py` | 多维度仪表盘 |
| AI 客户模拟 | `v7_ai/ai_customer.py` | 客户角色模拟测试 |

### V8 — 商业宇宙OS (Business Universe OS)

| 模块 | 文件 | 功能 |
|------|------|------|
| 公司工厂 | `ai_universe/company_factory.py` | AI 生成虚拟公司 |
| 商业克隆 | `ai_universe/business_clone_engine.py` | 克隆真实商业模式 |
| 资金分配 | `ai_universe/capital_allocator.py` | 虚拟资本配置 |
| 投资组合 | `ai_universe/portfolio_manager.py` | 组合管理 |
| ⚠️ 执行引擎 | `execution/kernel.py` | **消费者线程已禁用** |

### V9 — 自治组织 (Autonomous Organization)

| 模块 | 文件 | 功能 |
|------|------|------|
| 虚拟董事会 | `autonomous_org/virtual_board.py` | 4 角色董事会 (CEO/CFO/COO/CMO) |
| 部门系统 | `autonomous_org/department_system.py` | 6 部门管理 |
| 预算分配 | `autonomous_org/budget_allocator.py` | 跨部门预算分配 |
| 决策循环 | `autonomous_org/decision_loop.py` | ⚠️ **决策线程已禁用** |
| 部门间协议 | `autonomous_org/inter_dept_protocol.py` | 部门协作协议 |

---

## 三、核心模块详解

### 3.1 AI 引擎 (`ai_engine.py` + `ai_engine/`)

```
ai_engine.py            → ./ai_engine.py  (2865 行)
ai_engine/              → 包目录，__init__.py 自动加载 ./ai_engine.py
```

**能力矩阵：**
| 能力 | 模型 | API |
|------|------|-----|
| 文本翻译/生成 | 阿里云 Qwen3.7 Max | DashScope |
| 文生图 | 通义万相 WAN2.7 | DashScope |
| 图生视频 | 通义万相 WAN2.6 | DashScope |
| 文生图 (备) | 火山引擎 Doubao Seedream | Volcengine |
| 图生视频 (备) | 火山引擎 Doubao Seedance | Volcengine |
| TTS 语音 | 阿里云 Qwen-TTS | DashScope |
| 即梦视频 | Jimeng | Volcengine Visual |

**Agent 系统 (`ai_engine/agents/`):**
- 5 个竞争 Agent: Hunter / Consultant / Soft Seller / Technical / Closer
- Agent 竞争评分: 并行生成回复 → 评分选最优
- 自学习: WinnerSelector 低分 Agent 向高分学习

### 3.2 WhatsApp 通信 (`whatsapp_engine.py` + `whatsapp/`)

```
whatsapp_engine.py      # 浏览器引擎 (Playwright, 51412 行)
whatsapp_server.py      # 独立 HTTP 服务 (端口 15789)
whatsapp/run_whatsapp_server.bat
```

**架构：**
- 独立进程，与 CRM 分离
- 双工通信: HTTP 回调 + 独立端口 API
- v3 稳定版: `launch_persistent_context` 取代 subprocess+CDP
- 2 秒启动，关窗自启
- 多号轮转: `commercial_reality/wa_rotation.py` 3 账号自动切换
- Webhook 认证: HMAC-SHA256 签名验证

### 3.3 AI 覆盖层 (`ai_overlay/`)

| 模块 | 功能 |
|------|------|
| `multi_agent_brain.py` | 多 Agent 协作大脑 |
| `orchestrator.py` | 编排引擎 |
| `sales_autopilot.py` | 销售强制推进 (超时自动推下一阶段) |
| `followup_engine.py` | 跟进引擎 |
| `proactive_messaging.py` | 主动消息 |
| `revenue_pressure.py` | 成交压力系统 |
| `negotiation.py` | 谈判引擎 |
| `lead_scoring.py` | 线索评分 |
| `analytics.py` | 分析引擎 |
| `v2_core.py` | V2 核心策略循环 |
| `v2_strategy_loop.py` | 每日自动优化策略循环 |

### 3.4 增长策略引擎 (`strategy_engine/`)

```
strategy_engine/
├── core/           # 决策路由 + 策略引擎
├── ads/            # 广告追踪 + 预算分配 + ROI
├── growth/         # 实验引擎 + 市场扩张 + 自学习
├── learning/       # 反馈闭环 + 指标收集
├── market/         # 需求分析 + 地理分析 + 市场评分
├── policy/         # 业务策略 + 约束引擎
├── pricing/        # 折扣策略 + 定价模型
├── product/        # 产品评分 + 需求匹配
└── data/           # 策略状态持久化
```

### 3.5 报价计算器

| 功能 | 说明 |
|------|------|
| 产品类型 | 10 大类 (发光字/灯箱/招牌等) |
| 材质 | 18 种 (304 不锈钢/201 不锈钢/镀锌板/亚克力等) |
| 色温 | 12 种 |
| 计价模式 | 按面积/边长阶梯计价 |
| 木箱体积 | 自动计算 |
| 双语 | 中英文切换 |
| 双模式 PDF | 内部成本价 / 对外正式报价 |
| 汇率隔离 | 内部 6.8 / 客户 6.6 |

---

## 四、数据库架构

**65+ 表分布：**

| 业务域 | 核心表 |
|--------|--------|
| 客户 | customers, leads, lead_state_log |
| 订单 | orders, order_items, shipments |
| 报价 | quotes, quote_items |
| 产品 | products, product_categories |
| 消息 | messages, media, email_log |
| 财务 | invoices, expenses, budgets, payments, pl_records |
| 生产 | production_tasks, qc_inspections, qc_templates |
| 库存 | inventory_items, stock_movements |
| 采购 | purchase_orders, po_timeline |
| 活动 | campaigns, campaign_events |
| 用户 | users, activity_log |
| V3 优化 | ab_tests, price_anchors, intent_weights |
| V5 全球 | regions, region_agents, factory_allocations |
| V6 财务 | invoice_items, expense_categories, budget_allocations |
| V7 AI | ai_feedback_rules, ai_test_results, ai_generations |
| V8 执行 | execution_queue, task_orchestrations |
| V9 自治 | board_decisions, budget_proposals |
| 安全 | escalation_events, policy_rules, audit_log |

---

## 五、当前状态评估

### ✅ 已完工可运行

| 模块 | 状态 |
|------|------|
| V0 工作台 (仪表盘/客户/潜客/消息/产品/报价/订单) | ✅ |
| V3 自优化销售 (A/B 测试/价格优化/成交分析) | ✅ |
| V4 活动管理 | ✅ |
| V5 全球区域/销售团队/工厂管理/市场定价/路由 | ✅ |
| V6 财务 (P&L/发票/费用/预算/现金流/CEO仪表盘) | ✅ |
| V7 AI 测试中心/进化管理 | ✅ |
| V8 公司工厂/商业克隆/资金分配 (UI) | ✅ |
| V9 自治组织 (代码存在，占位) | ⏸️ |
| WhatsApp 独立服务 (v3 稳定版) | ✅ |
| AI 多引擎 (翻译/生图/生视频/TTS) | ✅ |
| 报价计算器 + 双模式 PDF | ✅ |
| 短视频系统 (8 语言/多角色语音) | ✅ |
| 侧栏重组 (V0→V3→V4→V5→V6→V7→V8→V9→📹) | ✅ |
| API Key 移到 .env | ✅ |
| Webhook HMAC 认证 | ✅ |

### ⚠️ 已编码但被禁用

| 功能 | 原因 | 位置 |
|------|------|------|
| V8 执行引擎 | 消费者守护线程被注释 | `app.py` ~520 行 |
| V9 决策循环 | `_v9_decision_loop.start()` 被注释 | `app.py` ~550 行 |
| 发布管理器 | YouTube/TikTok 返回 fake post_id | `publishing_manager/` |

### 🔴 待修复问题

| 问题 | 优先级 | 详情 |
|------|--------|------|
| Flask Secret Key | 中危 | 明文 `.secret_key` 文件，应移到 `.env` |
| 无 CSRF 防护 | 中危 | 所有 API 无 CSRF Token |
| SQL 注入风险 | 中危 | 多处 f-string 拼接 SQL |
| 无密码策略 | 低危 | 无复杂度/过期/锁定 |
| Session 安全 | 低危 | 未设置 Secure/HttpOnly/SameSite |
| 零测试覆盖 | 致命 | 无单元/集成/E2E 测试 |
| SQLite 并发 | 中危 | 多进程同时写同一文件 |
| 无数据库迁移 | 中危 | ALTER TABLE try/except 静默失败 |

### ❌ 缺失功能

| 类别 | 缺失项 |
|------|--------|
| 🧪 测试 | 零单元测试、零集成测试、零 E2E |
| 🔄 CI/CD | 无 GitHub Actions |
| 📖 API 文档 | 150+ 端点无 OpenAPI/Swagger |
| 📱 移动端 | 桌面端单页设计 |
| 🔔 实时通知 | 无 WebSocket/SSE |
| 🗑️ 软删除 | DELETE 物理删除 |
| 💾 自动备份 | API 存在但无调度 |
| 🌐 多语言 UI | 仅前端中文 |
| 📊 监控 | 无指标/追踪/告警 |

---

## 六、关键数据

| 指标 | 数值 |
|------|------|
| Python 文件 | 219 |
| Python 行数 | 71,844 |
| 最大文件 | `app.py` (9,747 行) |
| 数据库表 | 65+ |
| API 端点 | 150+ |
| Git 提交 | 23 |

### 最大瓶颈

1. **`app.py` 9747 行** — 所有路由和业务逻辑挤在一文件
2. **`core/database.py` 5408 行** — 表定义 + 迁移 + 查询混合
3. **`templates/index.html` 14,234 行** — 内联 CSS + JS，无框架
4. **零测试** — 每次改动靠手动浏览器验证

---

## 七、快速参考

### 启动命令

```bash
# 启动 CRM
cd D:\Bohui_Global_Push\GLOWFORGE_CRM
python app.py

# 启动 WhatsApp 服务 (独立)
python whatsapp/whatsapp_server.py

# 快捷方式
start.bat                    # CRM
run_whatsapp_server.bat      # WhatsApp
```

### 核心端口

| 服务 | 端口 |
|------|------|
| CRM (Flask) | 5789 |
| WhatsApp 服务 | 15789 |
| Chrome (账号1) | 9223 |
| Chrome (账号2) | 9224 |
| Chrome (账号3) | 9225 |

### 环境变量

见 `.env` 文件 — 包含所有 AI API Keys + Webhook Secret。

---

*此文档由 Claude 自动生成并维护。修改文件结构后请同步更新。*
