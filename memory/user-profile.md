---
name: user-profile
description: 用户个人资料、工作领域和工具配置
metadata: 
  node_type: memory
  type: user
  originSessionId: fc81c567-43fe-4f58-a608-b5ecffad66a8
---

# 用户资料

## 身份
- **角色**：短视频/社媒创作者，做 TikTok 和国内社媒运营
- **技术背景**：非程序员，但会使用设计软件（PS、AI、Blender、剪映等）

## 工作领域
- TikTok / 抖音短视频内容创作
- 社媒运营
- 设计（3D建模、平面设计、渲染）
- 有网站落地需求（考虑阿里云）

## 工具配置
- **Claude Code** (v2.1.197) — 运行在 VS Code 扩展环境，用于写文案、脚本、代码、分析数据
- **Cline** (v4.0.8) — 已安装并配置 DeepSeek API，有 Computer Use 能力，可操作桌面
- **Codex CLI** (v0.144.1) — 已安装但需要协议转换才能连 DeepSeek
- **后端模型**：DeepSeek-V4-Flash（通过 DeepSeek API 连接）
- **API Key**：DeepSeek `sk-c886b4158e024bb8bc6926f6492cbaab`（存储在 settings.json 和 bashrc 中）
- **DeepSeek 基础 URL**：`https://api.deepseek.com`

## 为什么不用官方 Claude
- 国内买不了 Anthropic 的 API，没有美元账户
- 目前所有工具都接在 DeepSeek API 上使用

## 分工模式
- **Claude Code（我）**：写脚本/文案、数据分析、上网搜索、代码开发
- **Cline**：操作桌面、看屏幕、操作软件（剪映/浏览器等）
- **用户**：决策、发指令、执行手工操作

## 关键文件路径
- Claude Code settings: `C:\Users\Administrator\.claude\settings.json`
- Cline state DB: `C:\Users\Administrator\AppData\Roaming\Code\User\globalStorage\state.vscdb`
