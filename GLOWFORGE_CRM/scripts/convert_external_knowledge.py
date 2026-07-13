"""外部知识库 → knowledge/ 格式转换脚本
将 Sign_Industry_Wiki 和 Bohui_Media_Arsenal 的文件批量转换
为 knowledge/ 目录的标准格式（标题 + 类别: + 内容）

用法:
  python scripts/convert_external_knowledge.py
"""
import os
import re
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
SIGN_WIKI_DIR = os.path.join(os.path.dirname(BASE_DIR), "Sign_Industry_Wiki")
MEDIA_DIR = os.path.join(os.path.dirname(BASE_DIR), "Bohui_Media_Arsenal")

os.makedirs(KNOWLEDGE_DIR, exist_ok=True)


def _to_title(filename):
    """从文件名生成可读标题"""
    name = filename.replace(".md", "").replace(".txt", "")
    # 去掉前缀
    for p in ["tech_", "media_", "prod_", "core_"]:
        if name.startswith(p):
            name = name[len(p):]
            break
    # 下划线 → 空格
    name = name.replace("_", " ").replace("-", " ")
    return name.strip()


def _clean_markdown(text):
    """清理 markdown 格式，转为纯文本 + === 分隔"""
    # 去掉版本元数据行
    lines = text.split("\n")
    cleaned = []
    in_frontmatter = False
    for line in lines:
        # 跳过 YAML frontmatter (--- ... ---)
        if line.strip() == "---" and not in_frontmatter:
            in_frontmatter = True
            continue
        if line.strip() == "---" and in_frontmatter:
            in_frontmatter = False
            continue
        if in_frontmatter:
            continue
        # 跳过版本/日期/路径元数据
        if re.match(r'^(版本|日期|封存|路径|分类|标签|作者).*[:：]', line.strip()):
            continue
        # 跳过 ──── 或 ════ 装饰线（保留文件自身的装饰线）
        if re.match(r'^[═\─]{10,}$', line.strip()):
            if "══════════════════" not in line:
                continue
        # markdown 标题 → === 格式
        if line.strip().startswith("# ") or line.strip().startswith("## ") or line.strip().startswith("### "):
            title_text = re.sub(r'^#+\s*', '', line).strip()
            cleaned.append(f"=== {title_text} ===")
            continue
        # 去掉图片引用
        if re.match(r'!\[.*?\]\(.*?\)', line.strip()):
            continue
        # 去掉链接引用（保留文字）
        line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
        # 去掉加粗/斜体标记
        line = line.replace("**", "").replace("*", "")
        cleaned.append(line)
    return "\n".join(cleaned)


def _read_source(path):
    """读取源文件，处理编码问题"""
    for enc in ["utf-8", "utf-8-sig", "gbk", "gb18030"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    print(f"  !!  无法解码: {path}")
    return None


def _write_knowledge(filename, title, category, content):
    """写入 knowledge/ 标准格式文件"""
    output_path = os.path.join(KNOWLEDGE_DIR, filename)
    header = f"{title}\n" + "═" * 47 + f"\n类别: {category}\n\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + content.strip() + "\n")
    size = os.path.getsize(output_path)
    print(f"  OK {filename} ({size//1024}KB)")


def convert_sign_wiki():
    """转换 Sign_Industry_Wiki 中的文件"""
    print("\n=== Sign_Industry_Wiki → knowledge/ ===")
    if not os.path.exists(SIGN_WIKI_DIR):
        print(f"  !!  目录不存在: {SIGN_WIKI_DIR}")
        return

    file_mapping = [
        ("博汇广告GLOWFORGE幻彩发光字专利技术工程白皮书.md", "tech_GLOWFORGE幻彩发光字专利技术.txt", "tech"),
        ("博汇广告背发光水晶底座字高端定制工程白皮书.md", "tech_背发光水晶底座字工程.txt", "tech"),
        ("博汇广告不锈钢扣边平面发光字标准化工程白皮书.md", "tech_不锈钢扣边平面发光字工程.txt", "tech"),
        ("博汇广告不锈钢扣边与背发光水晶底座全域工程Wiki.md", "tech_不锈钢扣边与背发光工程Wiki.txt", "tech"),
        ("博汇广告底层高阶术语代码库.txt", "tech_高阶术语代码库.txt", "tech"),
        ("博汇广告高级字形与光效控制专业知识库.md", "tech_高级字形与光效控制.txt", "tech"),
        ("博汇广告工艺死磕与材质百科全书.md", "tech_工艺死磕与材质百科.txt", "tech"),
        ("博汇广告全域招牌工程与材料百科Wiki.md", "tech_全域招牌工程与材料百科.txt", "tech"),
        ("博汇广告外贸大脑系统防灾与模型热切换指南.md", "tech_外贸大脑防灾与热切换.txt", "tech"),
        ("博汇专业广告招牌工艺百科.md", "tech_专业广告招牌工艺百科.txt", "tech"),
    ]

    for src_name, dst_name, category in file_mapping:
        src_path = os.path.join(SIGN_WIKI_DIR, src_name)
        if not os.path.exists(src_path):
            print(f"  !!  源文件不存在: {src_name}")
            continue
        content = _read_source(src_path)
        if content is None:
            continue
        # .md 文件需要清理 markdown
        if src_name.endswith(".md"):
            content = _clean_markdown(content)
        title = _to_title(dst_name)
        _write_knowledge(dst_name, title, category, content)


def convert_media_arsenal():
    """转换 Bohui_Media_Arsenal 中的精选文件"""
    print("\n=== Bohui_Media_Arsenal → knowledge/ ===")
    if not os.path.exists(MEDIA_DIR):
        print(f"  !!  目录不存在: {MEDIA_DIR}")
        return

    file_mapping = [
        # 根目录文件
        ("TikTok海外招牌爆款视频实战拆解指南.md", "media_TikTok爆款视频实战拆解.txt", "media"),
        ("TK同行爆款拆解与博汇多媒体发布V1弹药库.md", "media_同行爆款拆解与多媒体弹药库.txt", "media"),
        ("博汇多媒体矩阵爆款弹药库_V1.md", "media_多媒体矩阵爆款弹药库.txt", "media"),
        # 01_Hooks_Library
        ("01_Hooks_Library/材质工艺细节_5条斩首钩子.md", "media_材质工艺斩首钩子.txt", "media"),
        ("01_Hooks_Library/室内导视与户外钢构_话术钩子库.md", "media_室内导视户外钢构话术钩子.txt", "media"),
        ("01_Hooks_Library/Fizzys_Burgers_EN_direct.txt", "media_Fizzys_Burgers实战案例.txt", "media"),
        ("01_Hooks_Library/澳洲Matilda餐饮全包项目_终极绝杀方案.txt", "media_澳洲Matilda餐饮绝杀方案.txt", "media"),
        ("01_Hooks_Library/澳洲被动客户Nirvair_Bhullar视觉勾引方案.txt", "media_澳洲被动客户视觉勾引方案.txt", "media"),
        ("01_Hooks_Library/澳洲比价客户433_绝杀拦截方案.txt", "media_澳洲比价客户绝杀拦截.txt", "media"),
        ("01_Hooks_Library/澳洲汉堡店_Fizzy_Burgers斩首复活方案.txt", "media_澳洲汉堡店斩首复活.txt", "media"),
        ("01_Hooks_Library/澳洲售货机巨头_Import_Export_终极报价方案.txt", "media_澳洲售货机巨头报价.txt", "media"),
        ("01_Hooks_Library/迪拜巨头同行_Grand_Level_战略合作方案.txt", "media_迪拜巨头同行合作方案.txt", "media"),
        ("01_Hooks_Library/自动售货机_空间体量控光绝杀方案.txt", "media_自动售货机控光绝杀.txt", "media"),
        # 02_Copywriting_Palace
        ("02_Copywriting_Palace/V4全媒体流量劫持与WhatsApp绝杀弹药.md", "media_V4全媒体流量劫持弹药.txt", "media"),
        ("02_Copywriting_Palace/三场景材质工艺_配文模板库.md", "media_三场景材质工艺配文模板.txt", "media"),
    ]

    for rel_path, dst_name, category in file_mapping:
        src_path = os.path.join(MEDIA_DIR, rel_path)
        if not os.path.exists(src_path):
            print(f"  !!  源文件不存在: {rel_path}")
            continue
        content = _read_source(src_path)
        if content is None:
            continue
        if src_path.endswith(".md"):
            content = _clean_markdown(content)
        title = _to_title(dst_name)
        _write_knowledge(dst_name, title, category, content)


if __name__ == "__main__":
    print("=" * 50)
    print("外部知识库 → knowledge/ 格式转换")
    print("=" * 50)
    convert_sign_wiki()
    convert_media_arsenal()
    print("\nOK 转换完成！")
