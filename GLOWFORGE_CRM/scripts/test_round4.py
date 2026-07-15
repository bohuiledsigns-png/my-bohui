"""Test round 4: customer returns with $120 quote pressure"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "Hi, I saw your illuminated sign ads. How much does a sign like that cost for a small restaurant?"},
    {"role": "sent", "content_en": "Imagine walking past your restaurant at night — a warm illuminated sign that makes people stop. For a small restaurant, most of our US clients invest around $180-320 for a backlit sign. To give you the exact price for YOUR shop, send me a photo of your storefront and I'll show you a design preview."},
    {"role": "received", "content_en": "Ok thanks. But another company quoted me $120 for a similar sign. Can you match or beat that price?"},
    {"role": "sent", "content_en": "I understand the price comparison. But let me be honest with you: a sign is not just a product — it's what people see first before they walk into your restaurant. Instead of guessing based on price, let's find the right fit. Which best describes your restaurant? A) Small takeout B) Standard sit-down C) Premium."},
    {"role": "received", "content_en": "I understand what you said. But I don't have a storefront photo right now. I just need a rough final price. Also I need it quite urgently, like within 3-5 days."},
    {"role": "sent", "content_en": "Since you don't have the exact letter count, let's use standard sizes. A) Short name (3-5 letters) — $180-250 B) Standard (6-9 letters) — $280-380 C) 3-day non-illuminated — $120-160."},
    {"role": "received", "content_en": "$400 is still too high. I will check 3 more suppliers. Send me your best price now or I leave. I need to decide in 1 hour."},
    {"role": "sent", "content_en": "I respect your 1-hour deadline. We don't cut corners on certified materials. Here are optimized tiers based on factory costs: A) Essential (Acrylic, 201 SS) — $270 B) Standard Outdoor (Acrylic, 304 SS, Meanwell) — $310 C) Premium Full 304 (304 SS, Meanwell, Epistar) — $360. Reply A, B, or C to lock your price."},
]

result = analyze_customer_message(
    text="""Honestly, your price is still too high.
I got another quote for $120 for a similar sign.
Can you match it?
If not, I'll probably go with them.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round4.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
