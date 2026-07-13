---
name: task-bridge
description: Claude Code 与 Cline 的任务桥接系统
metadata: 
  node_type: memory
  type: system
  originSessionId: fc81c567-43fe-4f58-a608-b5ecffad66a8
---

# 🧠 任务桥接系统

## 位置
`D:\task-bridge\`

## 文件结构
- `server.js` - 本地Web服务器（端口3456）
- `index.html` - 可视化看板
- `bridge.json` - 任务队列（Claude写 → Cline读 → Claude读结果）
- `README.md` - 使用说明

## 工作流程
1. Claude Code 写任务到 bridge.json
2. 用户告诉 Cline："去看 D:\task-bridge\bridge.json 里的任务"
3. Cline 执行任务，把结果写回 bridge.json（status, result）
4. Claude Code 读取结果，安排下一步

## 启动命令
```bash
cd D:/task-bridge && node server.js
```
打开 http://localhost:3456 查看看板
