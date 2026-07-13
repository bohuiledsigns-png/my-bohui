"""Test round 5: customer questions price gap"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "Hi, I saw your illuminated sign ads. How much does a sign like that cost for a small restaurant?"},
    {"role": "sent", "content_en": "Imagine walking past your restaurant at night. For a small restaurant, most US clients invest around $180-320 for a backlit sign."},
    {"role": "received", "content_en": "Another company quoted me $120 for a similar sign. Can you match that?"},
    {"role": "sent", "content_en": "A sign is what people see first. Which best describes your restaurant? A) Small takeout B) Standard sit-down C) Premium."},
    {"role": "received", "content_en": "I don't have a photo. Just need a rough final price. Need it within 3-5 days."},
    {"role": "sent", "content_en": "Here are optimized tiers: A) Budget Acrylic — $180-250 B) Standard Metal — $280-380 C) Premium — $380-520."},
    {"role": "received", "content_en": "$400 is too high. I will check 3 more suppliers. Send best price or I leave."},
    {"role": "sent", "content_en": "We don't cut corners. A) Essential (Acrylic, standard PSU) — $270 B) Standard Outdoor (304 SS, Meanwell) — $310 C) Premium Full 304 — $360."},
    {"role": "received", "content_en": "Honestly, your price is still too high. I got another quote for $120 for a similar sign. Can you match it? If not, I'll go with them."},
    {"role": "sent", "content_en": "At $120 for illuminated, we're looking at different product types. A) Flat non-illuminated letters — $120-150 B) Standard front-glow 3D — $270-290 C) Premium halo-lit — $350-400. Reply A, B, or C."},
]

result = analyze_customer_message(
    text="""I see the options. But honestly:
I don't care about premium or halo or anything fancy.
I just need something that looks decent at night and brings customers in.
Why is your A option not enough for a small restaurant?
Also the other guy said his includes lighting for $120.
So I'm confused why yours starts at $270.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round5.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
