---
name: bohui-project-overview
description: 博汇广告GLOWFORGE全栈项目概览
metadata: 
  node_type: memory
  type: project
  originSessionId: fc81c567-43fe-4f58-a608-b5ecffad66a8
---

# 博汇广告 GLOWFORGE 项目

## 公司
中山市博汇广告工艺制品有限公司 — 发光字招牌制造商（中山小榄）

## 核心技术
GLOWFORGE 双通道幻彩发光字专利系统

## 项目组成
- **GLOWFORGE_CRM** (Python Flask): AI销售系统，219文件，71K行代码，V0-V9版本
  - 端口 5789
  - 含 multi-agent 竞争销售系统
  - WhatsApp 自动化集成
  - Safety/constraint 层
  - Strategy engine
- **OpenClaw**: Hermes主动获客引擎 (Python)
- **Sign_Industry_Wiki**: 10份专利技术白皮书
- **Bohui_Media_Arsenal**: TikTok社媒弹药库
- **AI Studio** (设计方案阶段): AI短视频生成工具
- **00_Video_Library**: 51个分类视频素材

## 工具链
- 后端: Python Flask, SQLite
- AI: DashScope/Qwen, DeepSeek, Doubao
- 浏览器自动化: Playwright
- WhatsApp: 多账号Playwright会话
- 视频生成: Kling AI, Jimeng 3.0, Seedance
- 版本控制: GitHub (bohuiledsigns-png/my-bohui)

## GitHub
- 账号: bohuiledsigns-png
- 仓库: my-bohui (master分支)
- SSH密钥: ~/.ssh/github_key（已配置）

## 注意
- 之前尝试用Claude Code做1688自动化失败（模型限制）
- Cline Computer Use 不可用
- 真正需要的是**真Claude API**或人工操作
- 项目代码已推送到GitHub
