"""Test round 6: customer demands honest explanation of price gap"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "Hi, I saw your illuminated sign ads. How much does a sign like that cost for a small restaurant?"},
    {"role": "sent", "content_en": "Most US clients invest around $180-320 for a backlit sign."},
    {"role": "received", "content_en": "Another company quoted me $120 for a similar sign. Can you match that?"},
    {"role": "sent", "content_en": "Which best describes your restaurant? A) Small takeout B) Standard C) Premium."},
    {"role": "received", "content_en": "I don't have a photo. Just need a rough final price."},
    {"role": "sent", "content_en": "A) Budget Acrylic — $180-250 B) Standard Metal — $280-380 C) Premium — $380-520."},
    {"role": "received", "content_en": "$400 is too high. I will check 3 more suppliers."},
    {"role": "sent", "content_en": "A) Essential (Acrylic, standard PSU) — $270 B) Standard Outdoor (304 SS, Meanwell) — $310 C) Premium Full 304 — $360."},
    {"role": "received", "content_en": "Your price is still too high. I got another quote for $120 for a similar sign."},
    {"role": "sent", "content_en": "A) Flat non-illuminated — $120-150 B) Standard front-glow 3D — $270-290 C) Premium halo-lit — $350-400."},
    {"role": "received", "content_en": "Why is A not enough? I need decent night look. Other guy includes lighting for $120."},
    {"role": "sent", "content_en": "A) Essential Night-Glow — $270-290 B) Metal-Trim — $310-340 C) Full Metal Backlit — $360-400. A is enough for small restaurant."},
]

result = analyze_customer_message(
    text="""I still don't get it.
Why would I pay $270+ if another guy is doing it for $120?
They also said it's LED illuminated and waterproof.
To me it sounds the same thing.
Be honest with me — what am I actually paying extra for?
Because right now it just looks like you are more expensive.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round6.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
