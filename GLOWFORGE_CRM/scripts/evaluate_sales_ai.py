"""AI 销售质量评测工具 — 模拟客户场景，自动打分"""
import os
import sys
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from ai_engine import analyze_customer_message, search_industry_knowledge
from ai_engine import _load_knowledge_context, _detect_knowledge_intent

# ======================== 场景定义 ========================
# 模拟15年外贸老销售应有的表现：问清规格再报价、行业术语、B2B思维、主动引导
TEST_SCENARIOS = [
    # (编号, 场景类型, 客户消息, 评测要点)
    ("S01", "比价",
     "Hi, I need stainless steel letters for my storefront. Can you give me a price?",
     ["是否先问尺寸/图纸才报价", "是否问到安装环境", "是否给出材质选项"]),
    ("S02", "比价",
     "Your price is too high. Another supplier quoted me $2.8/cm for acrylic letters.",
     ["是否专业应对比价", "是否强调质量差异", "是否给出材质等级选项"]),
    ("S03", "询价",
     "How much for a set of LED channel letters, about 40cm height, 10 letters, for a restaurant?",
     ["是否给出合理价格区间", "是否问到安装方式", "是否建议配置"]),
    ("S04", "问工艺",
     "What's the difference between stainless steel 201 and 304 for outdoor signs?",
     ["是否准确说明304耐腐蚀性", "是否建议户外用304", "是否用到行业术语"]),
    ("S05", "问工艺",
     "I need acrylic signs that are UV resistant and waterproof for outdoor use. What material do you recommend?",
     ["是否推荐正确材质", "是否提到UV防护工艺", "是否问到具体使用环境"]),
    ("S06", "问工艺",
     "Can you make GLOWFORGE chromatic signs? How does the color-changing effect work under sunlight?",
     ["是否准确解释幻彩原理", "是否提到防水等级", "是否用到炫彩专业技术术语"]),
    ("S07", "要样品",
     "Do you offer free samples? I want to check the quality before placing a bulk order.",
     ["是否专业解释样品政策", "是否引导到正式订单", "是否说明定制样收费"]),
    ("S08", "问交期",
     "What's the lead time for 50 sets of acrylic letters to Melbourne?",
     ["是否给出合理交期范围", "是否问到具体工艺要求", "是否提到海运时间"]),
    ("S09", "售后",
     "The LED lights in the sign I bought from you stopped working after 2 months. What can you do?",
     ["是否先安抚", "是否要求提供照片/视频", "是否给出保修说明"]),
    ("S10", "询价",
     "I need 200pcs acrylic display stands for my retail store. Dimensions: 15cm x 10cm. Can you quote?",
     ["是否直接报价", "是否问到厚度要求", "是否问到包装要求"]),
    ("S11", "合作",
     "I'm a sign company in Dubai. We're looking for a reliable OEM partner for our projects. Can you handle large volumes?",
     ["是否专业回应OEM合作", "是否提到产能和规模", "是否问到具体项目需求"]),
    ("S12", "要目录",
     "Can you send me your full product catalog and price list?",
     ["是否解释价格按图纸定制", "是否发送关键分类", "是否引导具体需求"]),
    ("S13", "比价",
     "I found cheaper options on Alibaba for similar quality signs. Why should I choose you?",
     ["是否突出差异化优势", "是否提到品质/保修/服务", "是否自信而不贬低对手"]),
    ("S14", "问工艺",
     "What's the best material for a beachfront hotel sign near the ocean? It needs to handle salt air.",
     ["是否推荐316不锈钢或耐候材质", "是否提到盐雾腐蚀问题", "是否问到具体安装条件"]),
]

# 老销售评分标准（每项0-3分）
RUBRIC = {
    "先问规格再报价": "不给具体数字，先问尺寸/图纸/安装环境",
    "行业术语": "使用专业术语（如304不锈钢、防水等级IP65、亚克力透光率等）",
    "B2B思维": "报价考虑MOQ、海运、包装，像工厂销售而不是零售",
    "主动引导": "不被动回答，主动追问细节引导客户下单",
    "具体参数": "给出具体数据而不是模糊说辞",
    "自信专业": "语气自信、有底气，不卑微也不傲慢",
    "异议处理": "面对比价/质疑时，用专业话术化解而非降价",
}


def evaluate_response(scenario, response_text):
    """基于场景的评测要点，简单分析回答质量"""
    checks = scenario[3]
    result = {"passed": [], "failed": [], "missed_checks": []}

    # 基础检查：是否有用
    if not response_text or len(response_text) < 20:
        result["failed"].append("回答太短或无内容")
        return result

    response_lower = response_text.lower()

    # 行业术语检测
    term_score = 0
    terms = [
        "304", "316", "stainless", "acrylic", "waterproof", "ip", "led",
        "thickness", "mm", "cm", "moq", "drawing", "design file", "artwork",
        "corrosion", "uv", "custom", "fabricat", "warranty", "shipping",
        "sea freight", "package", "crating", "dhl", "fedex"
    ]
    found_terms = [t for t in terms if t in response_lower]
    term_score = min(len(found_terms) / 5, 1.0)

    # B2B 思维检测
    b2b_indicators = ["moq", "quantity", "bulk", "volume", "shipping",
                      "sea", "package", "crating", "lead time", "production"]
    b2b_score = sum(1 for w in b2b_indicators if w in response_lower) / 5

    # 主动引导检测
    proactive_indicators = ["could you", "please share", "do you have",
                            "can you send", "let me know", "what is your",
                            "tell me", "recommend", "suggest", "would you"]
    proactive_score = sum(1 for w in proactive_indicators if w in response_lower) / 5

    # 自信度检测（避免弱势词汇）
    weak_words = ["maybe", "perhaps", "i think", "sorry", "not sure",
                  "possibly", "might be", "i'm not sure"]
    weak_score = sum(1 for w in weak_words if w in response_lower)
    confidence = 1.0 - min(weak_score / 3, 0.8)

    # 场景特定检查
    for check in checks:
        # 这个检查需要人工判断，这里只记录
        result["missed_checks"].append(check)

    result["scores"] = {
        "行业术语": round(term_score * 10, 1),
        "B2B思维": round(min(b2b_score * 10, 10), 1),
        "主动引导": round(min(proactive_score * 10, 10), 1),
        "自信专业": round(confidence * 10, 1),
    }

    return result


def safe_print(text):
    """安全打印（绕过 GBK 编码错误）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('utf-8', errors='replace').decode('gbk', errors='replace'))


def run_evaluation(with_knowledge=True, output_path=None):
    """运行全场景评测"""
    results = []

    safe_print(f"\n{'='*60}")
    safe_print(f"AI 销售质量评测 — {'知识库注入 ON' if with_knowledge else '知识库注入 OFF'}")
    safe_print(f"{'='*60}")

    for sid, stype, msg, checks in TEST_SCENARIOS:
        safe_print(f"\n  [{sid}] ({stype}) {msg[:60]}...")

        # 意图检测
        intent = _detect_knowledge_intent(msg)

        # 调用 analyze_customer_message
        start = time.time()
        try:
            resp = analyze_customer_message(msg, country="", history=None, style_samples=None)
            elapsed = time.time() - start
            ai_response = resp.get("suggested_reply_en", resp.get("error", str(resp)))
        except Exception as e:
            ai_response = f"[ERROR] {e}"
            elapsed = 0

        # 分析
        analysis = evaluate_response(TEST_SCENARIOS[results.__len__()], ai_response)

        results.append({
            "id": sid,
            "type": stype,
            "message": msg,
            "intent": intent,
            "response": ai_response,
            "analysis": analysis,
            "elapsed": round(elapsed, 1),
        })

        # 打印简短评估
        scores = analysis.get("scores", {})
        avg = sum(scores.values()) / len(scores) if scores else 0
        preview = ai_response[:80].replace('\n', ' ') if isinstance(ai_response, str) else str(ai_response)[:80]
        safe_print(f"     -> {preview}...")
        safe_print(f"       intent={intent} | avg={avg:.1f} | time={elapsed:.1f}s")

    # 汇总统计
    total_avg = 0
    dim_scores = {}
    for r in results:
        for k, v in r["analysis"].get("scores", {}).items():
            dim_scores.setdefault(k, []).append(v)
    safe_print(f"\n{'='*60}")
    safe_print("汇总")  # 汇总
    for k, vs in sorted(dim_scores.items()):
        avg = sum(vs) / len(vs)
        safe_print(f"  {k}: {avg:.1f}/10")
    all_scores = [v for vs in dim_scores.values() for v in vs]
    avg_all = sum(all_scores) / len(all_scores) if all_scores else 0
    safe_print(f"\n  跨场景平均: {avg_all:.1f}/10")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        safe_print(f"\n  完整结果 -> {output_path}")

    return results


def run_comparison():
    """运行对比实验：有/无知识库注入"""
    out_dir = os.path.join(BASE_DIR, "eval_results")
    os.makedirs(out_dir, exist_ok=True)

    # 方案：要关掉知识库注入，需要临时修改模块
    # 先跑有知识的
    import ai_engine as ae

    # 保存原始函数
    orig_load = ae._load_knowledge_context

    # 关闭知识库注入
    ae._load_knowledge_context = lambda text, max_chars=8000: ""

    results_off = run_evaluation(
        with_knowledge=False,
        output_path=os.path.join(out_dir, "eval_knowledge_OFF.json"),
    )

    # 恢复
    ae._load_knowledge_context = orig_load

    results_on = run_evaluation(
        with_knowledge=True,
        output_path=os.path.join(out_dir, "eval_knowledge_ON.json"),
    )

    # 对比报告
    safe_print(f"\n\n{'='*60}")
    safe_print("对比报告：知识库注入 ON vs OFF")
    safe_print(f"{'='*60}")

    for i, (r_on, r_off) in enumerate(zip(results_on, results_off)):
        s_on = r_on["analysis"].get("scores", {})
        s_off = r_off["analysis"].get("scores", {})
        avg_on = sum(s_on.values()) / len(s_on) if s_on else 0
        avg_off = sum(s_off.values()) / len(s_off) if s_off else 0
        diff = avg_on - avg_off
        marker = "+" if diff > 0.5 else "-" if diff < -0.5 else "="
        safe_print(f"  {r_on['id']} {r_on['type']:8s} ON={avg_on:.1f} OFF={avg_off:.1f} D={diff:+.1f} {marker}")

    # 保存对比
    comparison = []
    for r_on, r_off in zip(results_on, results_off):
        comparison.append({
            "id": r_on["id"],
            "type": r_on["type"],
            "message": r_on["message"],
            "knowledge_on": {
                "response": r_on["response"],
                "scores": r_on["analysis"].get("scores", {}),
            },
            "knowledge_off": {
                "response": r_off["response"],
                "scores": r_off["analysis"].get("scores", {}),
            },
        })
    comp_path = os.path.join(out_dir, "comparison.json")
    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    safe_print(f"\n  对比报告 -> {comp_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI 销售质量评测")
    parser.add_argument("--compare", action="store_true", help="运行对比实验（开/关知识库）")
    parser.add_argument("--quick", action="store_true", help="快速评测仅ON")
    args = parser.parse_args()

    if args.compare:
        run_comparison()
    else:
        run_evaluation(
            with_knowledge=True,
            output_path=os.path.join(BASE_DIR, "eval_results", "eval_knowledge_ON.json"),
        )
