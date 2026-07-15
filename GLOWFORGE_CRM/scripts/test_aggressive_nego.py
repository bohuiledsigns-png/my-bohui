"""Test: Aggressive negotiation — customer ultimatum"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "Hi, I saw your illuminated sign ads. How much does a sign like that cost for a small restaurant?"},
    {"role": "sent", "content_en": "Imagine walking past your restaurant at night — a warm illuminated sign that makes people stop. For a small restaurant, most of our US clients invest around $180-320 for a backlit sign. To give you the exact price for YOUR shop, send me a photo of your storefront and I'll show you a design preview, exact quote, and the best sign style for your location."},
    {"role": "received", "content_en": "Ok thanks. But another company quoted me $120 for a similar sign. Can you match or beat that price?"},
    {"role": "sent", "content_en": "I understand the price comparison. But let me be honest with you: a sign is not just a product — it's what people see first before they walk into your restaurant. Instead of guessing based on price, let's find the right fit. Which best describes your restaurant? A) Small takeout B) Standard sit-down C) Premium. Reply A, B, or C, and I'll show you the exact price for your restaurant type."},
    {"role": "received", "content_en": "I understand what you said. But I don't have a storefront photo right now. I just need a rough final price. Also I need it quite urgently, like within 3-5 days. Can you just give me a final number first?"},
    {"role": "sent", "content_en": "Since you don't have the exact letter count right now, let's use standard sizes. Which best matches your restaurant name? A) Short name (3-5 letters) — Investment: $180-$250, B) Standard name (6-9 letters) — Investment: $280-$380, C) I need it in 3 days (non-illuminated 3D acrylic letters) — Investment: $120-$160. Pick your option and I'll send the invoice for the 30% deposit. Next step: Just reply A, B, or C."},
]

result = analyze_customer_message(
    text="""$400 is still too high.
I will check 3 more suppliers.
Send me your best price now or I leave.
I need to decide in 1 hour.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_aggressive_nego.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
