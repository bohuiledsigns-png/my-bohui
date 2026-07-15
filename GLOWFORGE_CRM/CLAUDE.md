# GLOWFORGE CRM 系统手册

> 此文件由 Claude 自动读取。每次对话开始时，Claude 都会读到这份文档。
> 修改任何内容前，必须先读这份文档。

---

## 项目位置

```
D:\Bohui_Global_Push\GLOWFORGE_CRM\
```

---

## 完整架构文档

**见 `ARCHITECTURE.md`** — 包含完整的九层架构、目录结构、模块说明、数据库、状态评估。

---

## 核心文件（不要乱改）

| 文件 | 作用 | 重要性 |
|------|------|--------|
| `app.py` | CRM主应用（Flask，端口5789） | 核心 |
| `whatsapp_engine.py` | WhatsApp浏览器引擎（Playwright） | 核心 |
| `whatsapp_server.py` | WhatsApp独立HTTP服务（端口15789） | 核心 |
| `database.py` | 数据库初始化 + 全部表结构（V0-V9） | 核心 |
| `ai_sales_prompt.txt` | AI话术核心指令（688行，12条铁律+8脚本+SOP） | 核心 |
| `knowledge_base.json` | 25个产品类目结构化知识库 | 核心 |
| `knowledge/` | 32个深度知识文件（产品目录、技术百科、实战弹药） | 核心 |

---

## 文件结构（根目录布局，2026-07-11 恢复）

```
root/
├── app.py                # Flask 入口（9747行）
├── database.py           # 数据库（5408行）
├── ai_engine.py          # AI 引擎（2865行）
├── voice_engine.py       # TTS 语音
├── video_postprocessor.py
├── video_tool_server.py
├── health_watchdog.py
├── catalog_generator.py
├── review_queue.py
├── action_router.py
│
├── decision_engine.py    # CRM 业务逻辑
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
│
├── revenue_engine.py     # V3 自优化销售
├── a_b_optimizer.py
├── price_optimizer.py
├── intent_weight_tuner.py
├── premium_catalog.py
│
├── region_engine.py      # V5 全球收入OS
├── global_lead_router.py
├── revenue_dashboard_v5.py
├── factory_allocator.py
│
├── pl_engine.py          # V6 财务智能OS
├── expense_engine.py
├── invoice_engine.py
├── budget_engine.py
├── margin_engine.py
├── pricing_lock.py
├── profit_guard.py
├── executive_dash.py
│
├── ai_evolution.py       # V7 AI 进化
├── multi_agent_team.py
├── assumption_engine.py
├── dashboard_engine.py
├── ai_customer.py
│
├── whatsapp_engine.py    # WhatsApp 独立服务
├── whatsapp_server.py
│
├── safety/               # V0 安全治理层
├── ai_engine/            # AI Agent 系统（包目录）
├── ai_overlay/           # AI 覆盖层
├── ai_universe/          # V8 商业宇宙
├── autonomous_org/       # V9 自治组织
├── execution/            # V8 执行引擎
├── commercial_reality/   # WhatsApp 多号轮转
├── publishing_manager/   # 视频发布
├── strategy_engine/      # 增长策略
│
├── admin/                # 部署脚本
├── scripts/              # 工具/测试
├── logs/                 # 日志文件
├── templates/            # HTML 模板
├── knowledge/            # 行业知识
├── countries/            # 市场文化
└── prompts/              # AI 提示词
``` |

---

## AI引擎层（已有完整系统，不做替代方案）

### 话术与Agent
- `ai_engine/agents/` — 5个竞争Agent：hunter/consultant/soft_seller/technical/closer
- `ai_engine/agents/agent_competition.py` — Agent竞争评分系统（并行生成回复→评分选最优）
- `ai_engine/agents/winner_selector.py` — WinnerSelector学习进化（低分Agent向高分学习）
- `ai_engine/agents/agent_router.py` — Agent路由分配

### 调度与跟进
- `ai_engine/revenue_scheduler.py` — 每日调度（09:00/12:00/18:00/22:00）
- `ai_engine/deal_prioritizer.py` — DealPrioritizer客户优先级评分
- `ai_engine/conversion_ai_brain.py` — ConversionBrain决策大脑（是否发/发什么/何时发）
- `ai_engine/autonomous_sender.py` — AutonomousSender自主发送

### 自学习系统
- `ai_engine/revenue_feedback_loop.py` — 收入驱动学习（真金白银数据训练）
- `ai_overlay/v2_strategy_loop.py` — 每日自动优化策略循环
- `ai_overlay/multi_agent_brain.py` — 多Agent协作大脑

### 成交与推进
- `ai_overlay/sales_autopilot.py` — 销售强制推进（超时自动推下一阶段）
- `ai_overlay/followup_engine.py` — 跟进引擎
- `ai_overlay/proactive_messaging.py` — 主动消息
- `ai_overlay/revenue_pressure.py` — 成交压力系统
- `ai_overlay/negotiation.py` — 谈判引擎

### 其他引擎
- `ai_engine/profit_engine.py` — ProfitEngine利润引擎
- `ai_engine/dynamic_pricing.py` — DynamicPricing动态定价
- `ai_engine/market_explorer.py` — MarketExplorer市场探索
- `ai_engine/culture_adaptor.py` — CultureAdaptor文化适配
- `ai_engine/regional_sales_brain.py` — RegionalSalesBrain区域销售脑

---

## 安全层（V0-V9，已部署完成）

| 模块 | 文件 | 功能 |
|------|------|------|
| 执行防火墙 | `safety/execution_firewall.py` | AI动作拦截（ALLOW/BLOCK/MODIFY/FLAG/ESCALATE） |
| 状态注册表 | `safety/state_registry.py` | 统一状态视图+分歧检测 |
| 策略引擎 | `safety/policy_engine.py` | DB规则引擎（热加载）+ BusinessPolicy迁移 |
| 风控引擎 | `safety/risk_engine.py` | 6维连续评分0.0-1.0 |
| 图检查 | `safety/graph_check.py` | 利润路径信号 |
| 审计日志 | `safety/audit_logger.py` | 结构化审计日志 |
| Agent协调 | `safety/agent_coordinator.py` | 每客户互斥锁+主导Agent选举 |
| 内容审核 | `safety/content_gate.py` | 出站消息审核 |
| 消息审计 | `safety/message_audit.py` | 出站消息审计记录 |
| 告警通道 | `safety/alert_channel.py` | 异常告警通知 |
| 仪表盘 | `safety/dashboard.py` | 安全监控仪表盘 |
| 日志设置 | `safety/log_setup.py` | 日志配置 |

---

## V8-V9 执行层与自治组织（已部署）

- `execution/` — 执行队列 + 6 Agent执行器 + 资源调度 + 反馈闭环
- `autonomous_org/` — AI自治组织（董事会4角色 + 6部门 + 预算分配 + 决策循环）
- `business_graph/` — 利润路径图谱（节点+边推导 + 瓶颈检测）

---

## 修改规则（Claude 必须遵守）

### 🔴 红线
1. **改任何文件前，必须先完整读取该文件全文**
2. **不改话术内容**（`ai_sales_prompt.txt` 的规则/脚本/话术）
3. **不改 `knowledge/` 目录下的知识文件内容**
4. **不改 `knowledge_base.json` 的内容**
5. **不绕过安全层**（Execution Firewall / Content Gate）
6. **不改数据库表结构**（除非用户明确要求）

### 🟡 操作规范
1. 涉及架构变更 → 先出方案，用户确认后才动手
2. 涉及 `app.py` 修改 → 先读完整文件，标注修改位置
3. 涉及 `whatsapp_engine.py` 修改 → 先读完整文件，标注修改位置
4. 每次修改后 → 提示用户测试，满意后 `git commit`
5. 用户可以说「读 CLAUDE.md」→ 我重新加载这份文档
6. 用户可以说「先出方案」→ 我只写计划不写代码

---

## 用户偏好（来自记忆系统）

- 外贸客户沟通，先问图纸/尺寸再报价
- WhatsApp 回复等待 1-5 分钟模拟真人节奏
- 测试必须通过 Chrome 浏览器验证
- 桌面路径是 I:\桌面 不是 C 盘
