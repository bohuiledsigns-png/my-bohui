"""Translate all publishing HTML pages to Chinese."""
import os
import re

DIR = r"D:\Bohui_Global_Push\GLOWFORGE_CRM\templates\publishing"

translations = {
    # Navigation
    "Dashboard": "仪表板",
    "Schedule": "发布排期",
    "Analytics": "数据分析",
    "Comments": "评论管理",
    "Content": "内容管理",
    "Reports": "报表",
    "Work Time": "工时管理",
    "AI Insights": "AI 洞察",
    "Back to Content": "返回内容列表",

    # Titles
    "Publishing Dashboard": "发布仪表板",
    "Publish Schedule": "发布排期",
    "Content Manager": "内容管理",
    "Comments Inbox": "评论收件箱",
    "Platform Accounts": "平台账号管理",
    "Analytics Dashboard": "数据分析",
    "Performance Reports": "效果报表",
    "Content Detail": "内容详情",

    # Content page
    "My Content": "我的内容",
    "Import from Video Tool": "从视频工具导入",
    "All Status": "全部状态",
    "Draft": "草稿",
    "Ready": "就绪",
    "Published": "已发布",
    "New Content": "新建内容",
    "Scan Video Tool Output": "扫描视频工具输出",

    # Schedule page
    "All Platforms": "全平台",
    "New Schedule": "新建排期",
    "Schedule Publication": "新建排期",
    "Edit Schedule": "编辑排期",
    "Today": "今天",
    "Upcoming Schedules": "排期列表",
    "Uncategorized": "未分类",
    "Untitled": "未命名",
    "Pending": "待发布",
    "Failed": "失败",
    "Normal": "普通",
    "High": "高",
    "Urgent": "紧急",

    # Comments page
    "Refresh": "刷新",
    "Seed": "播种",
    "All Sentiment": "全部情感",
    "Unreplied": "未回复",
    "Replied": "已回复",
    "Flagged": "已标记",
    "Bulk": "批量",
    "Positive": "积极",
    "Negative": "消极",
    "Neutral": "中性",
    "No templates yet": "暂无模板",
    "Add Template": "添加模板",
    "New Auto-Reply Template": "新建自动回复模板",
    "Keyword Pattern": "关键词模式",
    "Sentiment Filter": "情感筛选",
    "Reply Template": "回复模板",
    "Overview": "概览",
    "Auto-Reply Templates": "自动回复模板",
    "Total Items": "内容总数",
    "Total Views": "总播放量",

    # Analytics
    "Seed Analytics Data": "播种分析数据",
    "Total Views": "总播放量",
    "Total Likes": "总点赞",
    "Total Comments": "总评论",
    "Total Shares": "总分享",
    "Views Trend": "播放趋势",
    "Platform Distribution": "平台分布",
    "Top Content": "热门内容",
    "Views": "播放",
    "Likes": "点赞",
    "Shares": "分享",

    # AI Insights
    "Views Change": "播放变化",
    "Current Views": "当前播放",
    "Best Day": "最佳日",
    "Sentiment": "情感分析",
    "Key Insights": "关键洞察",
    "Smart Suggestions": "智能建议",
    "No insights available": "暂无洞察数据",
    "Generate Insights": "生成洞察",

    # Reports
    "Generate Report": "生成报表",
    "Daily": "日报",
    "Weekly": "周报",
    "Monthly": "月报",
    "Period": "周期",
    "Generated": "生成时间",
    "Platform Breakdown": "平台分布",

    # Work Time
    "Production Tasks": "生产任务",
    "Add Task": "添加任务",
    "Video": "视频",
    "Copywriting": "文案",
    "Editing": "剪辑",
    "Planning": "策划",
    "Total Time": "总工时",
    "minutes": "分钟",
    "hours": "小时",
    "No tasks": "暂无任务",
    "Date": "日期",
    "Type": "类型",
    "Duration": "时长",
    "Notes": "备注",

    # Accounts
    "Add Account": "添加账号",
    "Edit Account": "编辑账号",
    "Add Platform Account": "添加平台账号",
    "Account Name": "账号名称",
    "Account ID / Username": "账号ID/用户名",
    "API Key": "API密钥",
    "API Secret": "API密钥",
    "Daily Post Limit": "每日发布上限",
    "Target Market": "目标市场",
    "Timezone Offset": "时区偏移",
    "No platform accounts yet": "暂无平台账号",
    "Market": "市场",
    "Daily Limit": "每日上限",
    "Account": "账号",
    "Cancel": "取消",
    "Save": "保存",
    "Delete": "删除",

    # Dashboard
    "Content Items": "内容数量",
    "Scheduled": "待发布",
    "Recent Activity": "最近动态",
    "Platforms": "平台",
    "Upcoming Schedules": "即将发布",
    "Quick Actions": "快捷操作",
    "Import Videos": "导入视频",
    "Generate Report": "生成报表",
    "Add Platform Account": "添加平台账号",

    # Common
    "Total": "合计",
    "Active": "活跃",
    "Inactive": "未激活",
    "active": "活跃",
    "inactive": "未激活",
    "Select content first...": "请先选择内容...",
    "Search": "搜索",
    "Import": "导入",
    "Edit": "编辑",
    "Reply": "回复",
    "Send": "发送",
    "Settings": "设置",
    "Help": "帮助",
    "Close": "关闭",
    "Type your reply...": "输入回复内容...",
    "All": "全部",
    "No data": "无数据",
}


def safe_translate(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    count = 0
    for eng, chn in sorted(translations.items(), key=lambda x: -len(x[0])):
        if eng in content:
            content = content.replace(eng, chn)
            count += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return count


if not os.path.isdir(DIR):
    print(f"Directory not found: {DIR}")
else:
    total = 0
    for fname in sorted(os.listdir(DIR)):
        if fname.endswith(".html"):
            c = safe_translate(os.path.join(DIR, fname))
            print(f"  {fname}: {c} replacements")
            total += c
    print(f"\nTotal: {total} replacements across all files")
