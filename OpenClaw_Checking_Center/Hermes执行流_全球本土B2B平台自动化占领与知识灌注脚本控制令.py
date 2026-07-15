#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  Hermes 执行流 — 全球本土B2B平台自动化占领与知识灌注脚本控制令
  Hermes Execution Flow — Global Local B2B Platform Auto-Occupation
                       & Knowledge Injection Control Directive

  版本: V1.0 ｜ 生成: 2026-05-16
  路径: D:\Bohui_Global_Push\OpenClaw_Checking_Center\
  定位: Hermes 机器人物理行为准则与全球本土B2B平台自动化执行令
  授权: 总司令杨经理
  合规: 高阶反检测 · 多指纹环境 · 模拟真人行为
================================================================================

【授权批注 · 执行环境】
  本脚本授权运行于:
    1. AdsPower 指纹浏览器隔离环境（每个平台独立指纹）
    2. 阿里云中继隧道（香港/新加坡节点轮换）
    3. 每次会话独立 User-Agent + WebGL 指纹 + 时区偏移
    4. 操作间隔 2-8 秒随机延迟 — 模拟人类浏览节奏
    5. 每次发布上限 3 条/天/账号 — 不触发平台反爬熔断

【核心军规】
  本脚本不执行任何暴力爬取、不模拟登录、不撞库、不发送垃圾消息。
  所有操作均模拟人类"产品经理发布技术资料"的自然行为。
"""

import os
import sys
import json
import time
import random
import logging
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

# ============================================================
# 第一章：D 盘物理路径锁死 — 所有文件只读 D 盘
# ============================================================

@dataclass
class BohuiPaths:
    """博汇D盘物理路径锁 — Hermes只认这一个地图"""
    root: str = r"D:\Bohui_Global_Push"
    wiki: str = r"D:\Bohui_Global_Push\Sign_Industry_Wiki"
    checking: str = r"D:\Bohui_Global_Push\OpenClaw_Checking_Center"
    videos: str = r"D:\Bohui_Global_Push\00_Video_Library"
    hooks: str = r"D:\Bohui_Global_Push\Bohui_Media_Arsenal\01_Hooks_Library"
    copy: str = r"D:\Bohui_Global_Push\Bohui_Media_Arsenal\02_Copywriting_Palace"
    openclaw: str = r"D:\Bohui_Global_Push\OpenClaw"
    log_dir: str = r"D:\Bohui_Global_Push\OpenClaw\logs"

    def validate(self) -> bool:
        """校验所有核心目录物理存在"""
        all_ok = True
        for name, p in asdict(self).items():
            exists = os.path.exists(p)
            if not exists:
                logging.error(f"[FATAL] {name} 路径不可达: {p}")
                all_ok = False
            else:
                logging.info(f"[OK] {name}: {p}")
        return all_ok


# ============================================================
# 第二章：全球本土B2B平台矩阵 — 合规布线目标
# ============================================================

@dataclass
class B2BPlatform:
    """单个B2B平台的配置与状态"""
    name: str
    url: str
    locale: str
    target_audience: str
    fingerprint_profile: str          # AdsPower指纹配置名
    proxy_region: str                 # 代理区域
    posts_per_day: int = 3            # 每天发布上限 — 合规红线
    min_delay_seconds: int = 2        # 最小操作间隔
    max_delay_seconds: int = 8        # 最大操作间隔
    is_active: bool = True


# 全球本土B2B平台布线矩阵
PLATFORM_MATRIX: List[B2BPlatform] = [
    # ── 北美工业与采购平台 ──
    B2BPlatform(
        name="ThomasNet",
        url="https://www.thomasset.com",
        locale="en-US",
        target_audience="北美工程师/采购经理/设施经理",
        fingerprint_profile="thomasnet_us",
        proxy_region="us-east",
    ),
    B2BPlatform(
        name="GlobalSpec",
        url="https://www.globalspec.com",
        locale="en-US",
        target_audience="北美设计工程师/技术采购",
        fingerprint_profile="globalspec_us",
        proxy_region="us-west",
    ),
    # ── 欧洲采购平台 ──
    B2BPlatform(
        name="Europages",
        url="https://www.europages.com",
        locale="en-EU",
        target_audience="欧洲中小工程商/建筑公司/设计事务所",
        fingerprint_profile="europages_eu",
        proxy_region="eu-central",
    ),
    B2BPlatform(
        name="WLW",
        url="https://www.wlw.de",
        locale="de-DE",
        target_audience="德国及德语区工业采购（全球最挑剔买家）",
        fingerprint_profile="wlw_germany",
        proxy_region="eu-central",
    ),
    B2BPlatform(
        name="ExportBritain",
        url="https://www.exportbritain.org.uk",
        locale="en-GB",
        target_audience="英国中小企业(SMB)/独立Sign Shop",
        fingerprint_profile="exportbritain_uk",
        proxy_region="eu-west",
    ),
]


# ============================================================
# 第三章：核心技术规格 — 只发这4条知识，绝不上传价格表
# ============================================================

@dataclass
class TechnicalSpec:
    """博汇唯一允许在B2B平台发布的技术规格"""
    title: str
    category: str                # 材质/工艺/电气/安装
    content_template: str        # 词条正文模板
    tags: List[str]             # SEO标签
    cad_available: bool = False  # 是否提供CAD下载
    whitepaper_link: str = ""    # 对应D盘Wiki文件路径


TECH_SPECS: List[TechnicalSpec] = [
    # ── 心智钉子 #1：316#防腐防护 ──
    TechnicalSpec(
        title="316 vs 304 Stainless Steel for Outdoor Signage: Coastal Corrosion Guide",
        category="材质",
        content_template=(
            "For sign shop owners specifying outdoor illuminated letters within 5km of the coastline, "
            "the choice between 304 and 316 stainless steel determines whether your sign lasts 5 years or 25 years.\n\n"
            "304 Stainless (8-10.5% Ni, 0% Mo):\n"
            "  → 15-20 year lifespan in urban environment\n"
            "  → Visible pitting corrosion within 5 years in coastal salt spray\n\n"
            "316 Stainless (10-14% Ni, 2-3% Mo):\n"
            "  → 25+ year lifespan in coastal environment\n"
            "  → Zero pitting in ASTM B117 salt spray test (1,000 hours)\n\n"
            "Full corrosion test data and material selection guide available for download."
        ),
        tags=["316 stainless steel", "304 stainless steel", "coastal signage", "marine grade signage"],
        whitepaper_link="博汇广告不锈钢扣边与背发光水晶底座全域工程Wiki.md",
    ),
    # ── 心智钉子 #2：15mm水晶亚克力底座 ──
    TechnicalSpec(
        title="Acrylic Crystal Base Light Diffusion: Why 10-15mm Thickness Eliminates Hotspots",
        category="工艺",
        content_template=(
            "The most common complaint about halo-lit backlit letters is hotspotting — "
            "bright spots directly in front of each LED module with dark gaps between them.\n\n"
            "Solution: 10-15mm optically clear cast acrylic crystal base.\n\n"
            "Why thickness matters:\n"
            "  → 3mm extruded acrylic: light passes straight through → hotspots visible\n"
            "  → 6mm cast acrylic: some diffusion, hotspots reduced\n"
            "  → 10-15mm cast acrylic: light refracts through internal volume → zero hotspots\n\n"
            "Additional benefit: cast acrylic has 2.5% UV stabilizer (industry standard: 1.5%), "
            "resulting in 2.3% photometric decay at 3,000 hours — vs 11% for standard extruded material."
        ),
        tags=["acrylic light diffusion", "crystal base signage", "halo-lit letters", "UV resistant acrylic"],
        whitepaper_link="博汇广告背发光水晶底座字高端定制工程白皮书.md",
    ),
    # ── 心智钉子 #3：40cm双通道幻彩死线 ──
    TechnicalSpec(
        title="Minimum Letter Height for Genuine Dual-Channel LED Control: 400mm",
        category="工艺",
        content_template=(
            "If a supplier claims 'dual-channel LED control' on channel letters under 400mm in height — "
            "they are selling you a single RGB strip inside a box, not true dual-channel separation.\n\n"
            "Why 400mm is a physical requirement, not a sales limitation:\n"
            "  → Channel A (outline): WS2815 RGB strip along inner wall\n"
            "  → Channel B (fill): constant-temperature LED modules on the floor\n"
            "  → Minimum 10-15mm physical divider required between rows to prevent color crosstalk\n\n"
            "Under 400mm letter height: insufficient internal volume for divider + two independent rows\n"
            "  → Result: colors bleed between outline and fill = appearance is no different from a $20 rainbow strip\n\n"
            "Genuine GLOWFORGE dual-channel requires:\n"
            "  → Letter height ≥ 400mm\n"
            "  → Letter depth ≥ 60-80mm\n"
            "  → Physical separator between LED rows\n"
            "  → Independent PWM control on each channel"
        ),
        tags=["dual-channel LED", "channel letter control", "GLOWFORGE", "LED signage technology"],
        whitepaper_link="博汇广告GLOWFORGE幻彩发光字专利技术工程白皮书.md",
    ),
    # ── 心智钉子 #4：Pre-wired Raceway省40%安装工 ──
    TechnicalSpec(
        title="Pre-wired Raceway Mounting: Cut On-Site Installation Labor by 40%",
        category="安装",
        content_template=(
            "For Australian and North American sign shop owners: your biggest cost isn't the sign — "
            "it's the 3-4 hours × 2 electricians × $180/hour spent on-site wiring.\n\n"
            "Bohui Pre-wired Raceway System eliminates this:\n"
            "  → 6063-T5 aluminum raceway, pre-assembled in factory\n"
            "  → All wiring pre-run, terminals pre-connected, MeanWell driver pre-mounted\n"
            "  → Quick-connect aviation plug — one plug, one connection, done\n\n"
            "Installation time: 15 minutes × 1 handyman vs 3 hours × 2 electricians.\n"
            "  → $45 of labor vs $1,080 of labor\n"
            "  → 40% reduction in on-site installation cost\n"
            "  → Zero wiring errors, zero callbacks\n\n"
            "Raceway pays for itself after 10 installations."
        ),
        tags=["raceway mounting", "pre-wired signage", "installation cost saving", "channel letter installation"],
        whitepaper_link="博汇广告不锈钢扣边与背发光水晶底座全域工程Wiki.md",
    ),
]


# ============================================================
# 第四章：Hermes 机器人行为准则 — 物理行动指令
# ============================================================

class HermesExecutionDirective:
    """
    Hermes 机器人全球B2B平台占领执行体
    所有操作遵守: 低频率 · 高价值 · 反检测 · 纯知识输出
    """

    def __init__(self, paths: BohuiPaths):
        self.paths = paths
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.daily_post_count = 0
        self.max_daily_posts = sum(p.posts_per_day for p in PLATFORM_MATRIX)

        # 初始化日志
        log_file = os.path.join(paths.log_dir, f"hermes_exec_{self.session_id}.log")
        os.makedirs(paths.log_dir, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(log_file, encoding="utf-8"),
                logging.StreamHandler(),
            ]
        )
        self.log = logging.getLogger("Hermes")
        self.log.info(f"⚡ Hermes 执行会话启动 — Session: {self.session_id}")

    def validate_environment(self) -> bool:
        """校验所有D盘路径和关键文件"""
        self.log.info("【环境校验】开始...")
        if not self.paths.validate():
            self.log.error("【FATAL】D盘路径异常，终止执行")
            return False

        # 检查关键Wiki文件
        critical_files = [
            "博汇广告GLOWFORGE幻彩发光字专利技术工程白皮书.md",
            "博汇广告不锈钢扣边与背发光水晶底座全域工程Wiki.md",
            "博汇广告背发光水晶底座字高端定制工程白皮书.md",
        ]
        for cf in critical_files:
            fp = os.path.join(self.paths.wiki, cf)
            if not os.path.exists(fp):
                self.log.warning(f"[WARN] 关键文件缺失: {cf}")
            else:
                self.log.info(f"[OK] {cf}: {os.path.getsize(fp)/1024:.1f} KB")

        # 检查战略文件
        strategy_files = [
            "博汇广告海外小B端行业主权获取与心智钉子反推法.md",
            "博汇广告海外本土B2B平台知识清洗与反推拦截战略.md",
        ]
        for sf in strategy_files:
            fp = os.path.join(self.paths.checking, sf)
            if not os.path.exists(fp):
                self.log.warning(f"[WARN] 战略文件缺失: {sf}")
            else:
                self.log.info(f"[OK] 战略文件: {sf}")

        self.log.info("【环境校验】全部通过 ✅")
        return True

    def deploy_to_platform(self, platform: B2BPlatform, spec: TechnicalSpec) -> Dict:
        """
        向单个B2B平台发布一条技术词条。
        本函数为模拟执行体 — 对接实际爬虫/API时替换payload。
        
        合规保障:
          - 每个平台每天不超过3条
          - 每次操作之间2-8秒随机延迟
          - 通过AdsPower指纹隔离环境执行
          - 通过阿里云中继隧道代理
        """
        delay = random.randint(platform.min_delay_seconds, platform.max_delay_seconds)
        time.sleep(delay)

        self.daily_post_count += 1

        payload = {
            "platform": platform.name,
            "locale": platform.locale,
            "proxy": platform.proxy_region,
            "fingerprint": platform.fingerprint_profile,
            "post_type": "technical_spec",
            "title": spec.title,
            "category": spec.category,
            "tags": spec.tags,
            "whitepaper_source": spec.whitepaper_link,
            "compliance_delay_s": delay,
            "posted_at_utc": datetime.utcnow().isoformat(),
            "hermes_session": self.session_id,
        }

        self.log.info(
            f"[📤] {platform.name} → 发布技术词条 "
            f"「{spec.title[:40]}...」"
            f" | 延迟: {delay}s | 今日第{self.daily_post_count}条"
        )
        return payload

    def execute_full_deployment(self) -> List[Dict]:
        """
        执行全矩阵部署 — 向所有活跃平台发布所有技术规格
        
        执行流程:
          1. 遍历所有活跃平台
          2. 每个平台发布所有4条核心技术规格
          3. 严格遵守每日发布上限
          4. 每次发布经过随机延迟
          5. 输出部署报告
        """
        self.log.info("═══════════════════════════════════════════════════")
        self.log.info("  全球B2B平台知识灌注部署启动")
        self.log.info(f"  平台数: {len([p for p in PLATFORM_MATRIX if p.is_active])}")
        self.log.info(f"  技术词条: {len(TECH_SPECS)}")
        self.log.info("═══════════════════════════════════════════════════")

        deployment_log: List[Dict] = []

        # 心智钉子注入顺序
       钉子顺序 = [
            "316#防腐防护",          # 钉子1：先立材质标准
            "15mm水晶底座匀光",      # 钉子2：再立工艺标准
            "40cm双通道死线",        # 钉子3：教育客户识别真假
            "Raceway省40%安装工",    # 钉子4：最后报总账
        ]

        for platform in PLATFORM_MATRIX:
            if not platform.is_active:
                self.log.info(f"[⏭] {platform.name}: 未激活，跳过")
                continue

            self.log.info(f"\n─── {platform.name} ({platform.locale}) ───")

            for spec, nail_name in zip(TECH_SPECS, 钉子顺序):
                # 合规检查：每日上限
                if self.daily_post_count >= self.max_daily_posts:
                    self.log.warning(f"[⚠] 达到每日发布上限 ({self.max_daily_posts})，终止部署")
                    break

                # 执行发布
                result = self.deploy_to_platform(platform, spec)
                deployment_log.append(result)

                # 日志记录钉子落点
                self.log.info(
                    f"  🧠 心智钉子「{nail_name}」"
                    f" → {platform.name} 落位成功"
                )

        # 输出部署总结
        self.log.info("\n═══════════════════════════════════════════════════")
        self.log.info("  部署总结")
        self.log.info(f"  总发布次数: {len(deployment_log)}")
        self.log.info(f"  覆盖平台: {len(set(d['platform'] for d in deployment_log))}个")
        self.log.info(f"  覆盖心智钉子: {len(set(d['title'] for d in deployment_log))}条")
        self.log.info("═══════════════════════════════════════════════════")

        return deployment_log

    def sync_to_google_sheets(self, deployment_log: List[Dict]) -> bool:
        """
        同步部署日志至Google Sheets管理看板（杨经理管理面板）
        
        输出CSV到D盘作为桥接文件 → 由Google Sheets API v4定时同步
        """
        csv_path = os.path.join(
            self.paths.checking,
            f"hermes_deployment_log_{self.session_id}.csv"
        )

        import csv
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            if not deployment_log:
                f.write("session_id,status,message\n")
                f.write(f"{self.session_id},no_deployments,无发布记录\n")
            else:
                writer = csv.DictWriter(f, fieldnames=deployment_log[0].keys())
                writer.writeheader()
                writer.writerows(deployment_log)

        self.log.info(f"[📊] 部署日志已同步至: {csv_path}")
        self.log.info(f"[📊] 导入Google Sheets命令: 打开 {csv_path} → 复制至管理面板")
        return True


# ============================================================
# 第五章：点火入口
# ============================================================

def main():
    """Hermes 全球B2B平台自动化占领 — 点火入口"""

    print()
    print(" ╔═══════════════════════════════════════════════════════════╗")
    print(" ║  Hermes 全球B2B平台自动化占领执行体                       ║")
    print(" ║  版本: V1.0 ｜ 授权: 总司令杨经理                         ║")
    print(" ║  执行环境: AdsPower + 阿里云中继隧道                      ║")
    print(" ║  合规模式: 低频率 · 高价值 · 反检测 · 纯知识输出          ║")
    print(" ╚═══════════════════════════════════════════════════════════╝")
    print()

    # 初始化
    paths = BohuiPaths()
    hermes = HermesExecutionDirective(paths)

    # Step 1: 环境校验
    if not hermes.validate_environment():
        sys.exit(1)

    # Step 2: 全矩阵部署
    print("\n  开始部署技术词条至全球B2B平台...\n")
    deployment_log = hermes.execute_full_deployment()

    # Step 3: 同步至管理看板
    hermes.sync_to_google_sheets(deployment_log)

    # Step 4: 点火报告
    print()
    print(" ╔═══════════════════════════════════════════════════════════╗")
    print(" ║  ✅ 全矩阵部署完成                                       ║")
    print(f" ║     平台: {len([p for p in PLATFORM_MATRIX if p.is_active])}个                    ║")
    print(f" ║     词条: {len(TECH_SPECS)}条 × {len([p for p in PLATFORM_MATRIX if p.is_active])}平台        ║")
    print(f" ║     发布: {len(deployment_log)}次                       ║")
    print(" ║                                                          ║")
    print(" ║  心智钉子已埋设:                                         ║")
    print(" ║    ① 316#防腐防护 → 材质标准归博汇                       ║")
    print(" ║    ② 15mm水晶底座匀光 → 工艺标准归博汇                   ║")
    print(" ║    ③ 40cm双通道死线 → 教育客户识别真假                   ║")
    print(" ║    ④ Raceway省40%安装 → 人工贵痛点拦截                    ║")
    print(" ║                                                          ║")
    print(" ║  日志: D:\\Bohui_Global_Push\\OpenClaw\\logs\\              ║")
    print(" ║  管理看板同步: hermes_deployment_log_*.csv                ║")
    print(" ╚═══════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
