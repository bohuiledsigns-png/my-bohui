"""AI Customer Simulator — AI 客户模拟器

模拟真实客户与销售 AI 对话，覆盖多区域/多角色/多场景。
每一次模拟对话都记录到数据库，用于评估和进化销售 AI。
"""
import os
import sys
import json
import random
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")

# ==================== 客户画像模板 ====================

PERSONA_TEMPLATES = [
    {
        "id": "dubai_distributor",
        "name": "Ahmed Al Rasheed",
        "company": "Gulf Signage Solutions",
        "country": "UAE",
        "region": "中东",
        "role": "distributor",
        "language": "English",
        "personality": "专业、注重关系、价格敏感但重视质量",
        "industry_knowledge": "high",
        "opening": "Hi, I'm looking for a reliable supplier for stainless steel channel letters. We supply sign companies across the UAE.",
        "description": "迪拜分销商 — 有行业经验，关注OEM合作和批量价格",
    },
    {
        "id": "german_architect",
        "name": "Klaus Weber",
        "company": "Weber Architekten",
        "country": "Germany",
        "region": "欧洲",
        "role": "architect",
        "language": "English",
        "personality": "严谨、注重认证标准、技术细节",
        "industry_knowledge": "high",
        "opening": "I need acrylic signage for a new office complex. What materials and certifications do you offer?",
        "description": "德国建筑师 — 关注认证、环保、技术参数",
    },
    {
        "id": "us_retail_owner",
        "name": "Mike Johnson",
        "company": "Johnson's Retail",
        "country": "US",
        "region": "北美",
        "role": "end_user",
        "language": "English",
        "personality": "务实、注重性价比、需要引导",
        "industry_knowledge": "low",
        "opening": "Hi, I need a sign for my new store. How much does it cost?",
        "description": "美国零售店主 — 首次购买，需要教育引导",
    },
    {
        "id": "australia_chain",
        "name": "Sarah Chen",
        "company": "AusPac Retail Group",
        "country": "Australia",
        "region": "亚太",
        "role": "procurement",
        "language": "English",
        "personality": "专业采购、注重交期和售后、多方比价",
        "industry_knowledge": "medium",
        "opening": "We need 50 sets of acrylic letters for our连锁 stores across Australia. Can you quote with shipping to Melbourne?",
        "description": "澳洲连锁店采购 — 批量订单，关注交期和物流",
    },
    {
        "id": "saudi_contractor",
        "name": "Faisal Al-Otaibi",
        "company": "Al-Otaibi Contracting",
        "country": "Saudi Arabia",
        "region": "中东",
        "role": "contractor",
        "language": "English",
        "personality": "自信、压价强势、注重社会证明",
        "industry_knowledge": "medium",
        "opening": "We're doing a big hotel project. Can you handle large orders? Your price needs to be competitive with what I can get from China.",
        "description": "沙特承包商 — 大型项目，强势压价",
    },
    {
        "id": "uk_design_agency",
        "name": "Emma Thompson",
        "company": "Thompson Design Studio",
        "country": "UK",
        "region": "欧洲",
        "role": "designer",
        "language": "English",
        "personality": "创意导向、关注视觉效果和定制能力",
        "industry_knowledge": "medium",
        "opening": "We're designing a flagship store and want something unique - chromatic signs with color-changing effects. Can GLOWFORGE do custom colors?",
        "description": "英国设计公司 — 关注定制化和视觉效果",
    },
    {
        "id": "sg_investor",
        "name": "Lim Wei Ming",
        "company": "LWM Investments",
        "country": "Singapore",
        "region": "东南亚",
        "role": "investor",
        "language": "English",
        "personality": "精明、注重成本效益、多方比价",
        "industry_knowledge": "low",
        "opening": "I'm setting up a few businesses and need signs. Your competitor in China offered half your price. Why should I pay more?",
        "description": "新加坡投资者 — 多方比价，用竞争对手压价",
    },
    {
        "id": "france_luxury",
        "name": "Pierre Dubois",
        "company": "Dubois Luxury Retail",
        "country": "France",
        "region": "欧洲",
        "role": "end_user",
        "language": "English",
        "personality": "高端品味、注重品牌形象、愿意为品质付费",
        "industry_knowledge": "low",
        "opening": "I need very high-end illuminated signs for my boutique. Only the best quality. Can you do brushed gold finish stainless steel?",
        "description": "法国奢侈品店主 — 高端需求、品质导向",
    },
    {
        "id": "sea_importer",
        "name": "Thanh Nguyen",
        "company": "Mekong Signage Import",
        "country": "Vietnam",
        "region": "东南亚",
        "role": "importer",
        "language": "English",
        "personality": "价格极度敏感、批量进口、寻找长期合作",
        "industry_knowledge": "high",
        "opening": "I import signs for distributors across Vietnam. Your prices need to be very competitive. Can you do FOB Shenzhen pricing?",
        "description": "越南进口商 — 批量进口、FOB价格敏感",
    },
    {
        "id": "south_africa",
        "name": "David Nkosi",
        "company": "Nkosi Construction",
        "country": "South Africa",
        "region": "非洲",
        "role": "contractor",
        "language": "English",
        "personality": "务实、注重耐用性、需要技术支持",
        "industry_knowledge": "medium",
        "opening": "We need outdoor signs that can handle harsh sun and dust. What materials do you recommend for African conditions?",
        "description": "南非建筑商 — 关注耐候性和技术支持",
    },
]


# ==================== 行业知识注入 ====================

def _get_customer_knowledge():
    """加载行业知识用于 AI 客户，让它更懂行"""
    knowledge_parts = []

    # 材质知识
    knowledge_parts.append("""
【材质知识】
- 不锈钢 201: 室内可用，户外6-12个月生锈，成本低
- 不锈钢 304: 户外行业标准，8-10年不生锈
- 不锈钢 316: 海洋级，耐盐雾，10-15年不生锈，成本最高
- 亚克力: 进口浇铸亚克力（抗UV不黄变）vs 普通挤出亚克力（2-3年黄变）
- LED 芯片: Epistar（台湾，中高端）vs 三安（国产中端）vs 无牌（低端）
- 电源: Meanwell（台湾明纬，UL/CE认证，高端）vs 国产（无认证，低端，有安全隐患）
- 防水等级: IP65（防喷溅）vs IP67（防浸泡）vs IP68（完全防水）
- 包装: 出口级木箱（海运标准）vs 纸箱（仅适合空运）
""")

    # 发光字工艺
    knowledge_parts.append("""
【发光字工艺】
- 正面发光: LED从正面照射，最常用
- 背面发光（光晕效果）: LED从背面照射产生光晕，高端
- 正面+背面同时发光: 最亮效果
- 炫彩/幻彩字（GLOWFORGE 专利）: 双通道LED，日光下金属质感，夜晚色彩变换
- 无边字: 亚克力面板直接发光，无金属边框
- 精工字: 全不锈钢打磨，不发光，高端定位
""")

    # 外贸常识
    knowledge_parts.append("""
【外贸常识】
- FOB Shenzhen: 卖方负责到港口，买方负责后续运费和保险
- DDP: 卖方负责所有费用到门，价格最高
- T/T 30%+70%: 30%定金+70%发货前付清，常见外贸付款方式
- MOQ: 最小起订量，博汇标准 MOQ 1套
- 交期: 标准10-15天，定制产品可能延长
- 木箱包装: 出口级标准，防海运颠簸
- UL/CE认证: 欧美市场必备电源认证
- RoHS: 环保认证，欧洲市场要求
- 木材熏蒸证明: 出口到澳洲/欧美需要
""")

    # 价格参考
    knowledge_parts.append("""
【价格参考（仅客户模拟使用，用于合理压价）】
- 普通不锈钢发光字: 国际批发 USD 2-4/cm（字母高度），零售 USD 5-8/cm
- 304不锈钢发光字: 批发 USD 3-5/cm，零售 USD 6-10/cm
- 炫彩字: 零售 USD 8-15/cm
- 亚克力字: 批发 USD 1.5-3/cm，零售 USD 3-6/cm
- 安装服务: 额外 USD 200-500 视现场情况
- Alibaba 上的低价供应商通常给 201不锈钢 + 无牌LED + 纸箱包装
""")

    # 检验知识
    knowledge_parts.append("""
【客户可能会问的专业问题】
- 你们用什么牌子的LED？Epistar还是国产？
- 304不锈钢多厚？1.0mm还是0.6mm？
- 电源有没有UL认证？
- 质保期多久？LED保几年？
- 户外能用几年不褪色？
- 海运到澳洲要多久？
- 能不能做FOB？
- 样品怎么收费？
""")

    return "\n".join(knowledge_parts)


# ==================== AI 客户生成回复 ====================

def _call_customer_llm(system_prompt, user_prompt):
    """调用 LLM 生成客户回复"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "sk-qpQncoUjfFRIiLCf958b2e921a954d4b961477D14eE042b"),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.302.ai/v1"),
        )
        resp = client.chat.completions.create(
            model=os.environ.get("AI_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=500,
        )
        return resp.choices[0].message.content
    except Exception as e:
        # 降级：返回模板回复
        return _get_fallback_reply(user_prompt)


def _get_fallback_reply(context):
    """兜底回复模板（当 LLM 调用失败时）"""
    fallbacks = [
        "I see. But can you give me a more specific price?",
        "That sounds interesting, but I need to compare with other suppliers.",
        "Can you break down the costs? I need to justify this to my management.",
        "What about the warranty? How long do your signs last?",
        "I appreciate the details, but the price still seems high for my budget.",
        "Can you match what I'm paying now with my current supplier?",
        "What certifications do you have? Quality is important for my clients.",
        "Do you have samples I can see before placing an order?",
    ]
    return random.choice(fallbacks)


def _build_customer_system_prompt(persona, conversation_history):
    """构建 AI 客户的 system prompt"""
    knowledge = _get_customer_knowledge()

    # 对话历史摘要
    history_text = ""
    if conversation_history:
        for h in conversation_history[-6:]:  # 最近6轮
            role_tag = "销售人员" if h.get("role") == "assistant" else "客户"
            content = h.get("content", "")
            history_text += f"{role_tag}: {content}\n"

    prompt = f"""你是 {persona['name']}，{persona['description']}。

你的角色信息：
- 公司: {persona['company']}
- 国家: {persona['country']}
- 性格: {persona['personality']}
- 行业知识水平: {'非常懂行，熟悉各种材质和工艺' if persona['industry_knowledge'] == 'high' else '有一定了解，但不专业' if persona['industry_knowledge'] == 'medium' else '不太懂行，需要销售引导'}
- 角色: {'批发分销商，关注价格和OEM合作' if persona['role'] == 'distributor' else '终端用户，关注自家店面效果' if persona['role'] == 'end_user' else '设计师，关注创意实现' if persona['role'] == 'designer' else '采购，关注交期和批量价格' if persona['role'] == 'procurement' else '建筑承包商，关注项目配合' if persona['role'] == 'contractor' else '进口商，关注FOB和批量价格'}
- 目标: 测试销售人员的专业能力，你会在合理的范围内提出质疑和追问

你深谙行业知识，可以合理运用以下知识来质疑销售人员：
{knowledge}

规则：
1. 你是一个潜在客户，正在和博汇的销售沟通
2. 你会根据你的角色和行业知识提出合理的问题和质疑
3. 如果销售人员报价没有先问你的具体需求（尺寸/图纸/安装环境），你应该指出这一点
4. 在适当时机可以用竞争对手来压价（但不能无理取闹）
5. 回答要自然，不要暴露你是测试AI
6. 每次回复 1-3 句话，不要过长
7. 说英语（外贸场景）

当前对话历史（最新消息在最下方）：
{history_text}
"""
    return prompt


def generate_customer_response(persona, conversation_history, sales_last_message):
    """AI 客户根据销售的最后一条消息生成回复"""
    if not conversation_history:
        # 首次回复：使用预设开场白
        return persona["opening"]

    system_prompt = _build_customer_system_prompt(persona, conversation_history)
    user_prompt = f"销售人员刚刚说了：\n{sales_last_message}\n\n作为 {persona['name']}，请回复销售人员（保持角色，1-3句话，英语）："

    return _call_customer_llm(system_prompt, user_prompt)


def get_persona(pid):
    """按 ID 获取客户画像"""
    for p in PERSONA_TEMPLATES:
        if p["id"] == pid:
            return dict(p)
    return None


def get_personas():
    """获取所有客户画像"""
    return PERSONA_TEMPLATES


def list_persona_options():
    """返回前端选择器用的精简列表"""
    return [
        {"id": p["id"], "name": p["name"], "company": p["company"],
         "country": p["country"], "role": p["role"], "description": p["description"]}
        for p in PERSONA_TEMPLATES
    ]


# ==================== 运行模拟测试 ====================

def run_simulation(persona_id, max_rounds=6):
    """运行 AI 客户 vs AI 销售的模拟对话

    Args:
        persona_id: 客户画像 ID
        max_rounds: 最大对话轮数

    Returns:
        dict: {conversation: [...], summary: {...}}
    """
    persona = get_persona(persona_id)
    if not persona:
        return {"error": f"Persona not found: {persona_id}"}

    # 引入销售 AI
    sys.path.insert(0, BASE_DIR)
    from ai_engine import analyze_customer_message

    conversation = []
    history = []

    # 第一轮：客户开场
    customer_msg = persona["opening"]
    conversation.append({
        "round": 1,
        "role": "customer",
        "content": customer_msg,
        "persona": persona["name"],
    })
    history.append({"role": "user", "content": customer_msg})

    for round_num in range(1, max_rounds + 1):
        # 销售 AI 回复
        try:
            sales_result = analyze_customer_message(
                text=customer_msg,
                country=persona["country"],
                history=[{"role": "received", "content_en": m["content"]}
                         for m in conversation if m["role"] == "customer"]
            )
            sales_reply = sales_result.get("reply_en", "") or sales_result.get("reply", "")
        except Exception as e:
            sales_reply = f"Thank you for your inquiry. Let me check the details and get back to you."

        if not sales_reply:
            break

        conversation.append({
            "round": round_num + 1,
            "role": "sales",
            "content": sales_reply,
        })

        # 客户再回复
        try:
            customer_msg = generate_customer_response(
                persona=persona,
                conversation_history=conversation,
                sales_last_message=sales_reply,
            )
        except Exception as e:
            customer_msg = _get_fallback_reply(sales_reply)

        conversation.append({
            "round": round_num + 1,
            "role": "customer",
            "content": customer_msg,
            "persona": persona["name"],
        })

    return {
        "persona": persona,
        "conversation": conversation,
        "rounds": max_rounds,
        "created_at": datetime.now().isoformat(),
    }


# ==================== 测试入口 ====================
if __name__ == "__main__":
    print("=== AI Customer Simulator ===")
    print(f"Personas available: {len(PERSONA_TEMPLATES)}")
    for p in PERSONA_TEMPLATES:
        print(f"  {p['id']}: {p['name']} ({p['country']}) - {p['description']}")
