"""测试决策负担降低后的AI回复 — Round 3场景"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

# Round 3 场景：客户没照片、要最终价格、急要
history = [
    {"role": "received", "content_en": "Hi, I saw your illuminated sign ads. How much does a sign like that cost for a small restaurant?"},
    {"role": "sent", "content_en": "Imagine walking past your restaurant at night — a warm illuminated sign that makes people stop. For a small restaurant, most of our US clients invest around $180-320 for a backlit sign. To give you the exact price for YOUR shop, send me a photo of your storefront and I'll show you a design preview, exact quote, and the best sign style for your location."},
    {"role": "received", "content_en": "Ok thanks. But another company quoted me $120 for a similar sign. Can you match or beat that price?"},
    {"role": "sent", "content_en": "I understand the price comparison. But a sign is not just a product — it's what people see first before they walk into your restaurant. Instead of guessing based on price, let me show you something real. Send me a photo of your storefront. I will show you: exact design for your shop, night-time visibility effect, final installed look, and exact production cost based on real size. Then you can compare fairly."},
    {"role": "received", "content_en": "I understand what you said. But I don't have a storefront photo right now. I just need a rough final price. Also I need it quite urgently, like within 3-5 days. Can you just give me a final number first?"},
    {"role": "sent", "content_en": "I hear you. Since you don't have a photo right now, let's work with standard dimensions. First, I need to be upfront: custom illuminated signs take 10-12 days to manufacture properly plus 3-5 days air shipping. If anyone promises a custom sign in 3-5 days total, they're cutting corners. For a typical restaurant sign (6-8 letters, each ~16in tall), the total investment is usually USD 380-550 including 304 stainless steel, certified Meanwell power supply, and shipping. To give you the exact number: how many letters are in your restaurant name? And roughly how wide is your wall space?"},
]

result = analyze_customer_message(
    text="I don't have the exact letter count right now. Just give me a price. If it's reasonable I'll pay today, just need it fast. Can you do 3 days?",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)

# Save to file for reading (use absolute path to avoid CWD issues)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_decision_burden_result.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
