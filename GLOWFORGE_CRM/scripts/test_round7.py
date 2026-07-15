"""Test round 7: final crunch - customer wants concrete reason for $270 vs $120"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "How much for a small restaurant sign?"},
    {"role": "sent", "content_en": "Most US clients invest $180-320. Send photo for exact price."},
    {"role": "received", "content_en": "Another company quoted $120. Can you match?"},
    {"role": "sent", "content_en": "Which describes you? A) Small takeout B) Standard C) Premium."},
    {"role": "received", "content_en": "No photo. Just give me final price. Need in 3-5 days."},
    {"role": "sent", "content_en": "A) Budget $180-250 B) Standard $280-380 C) Premium $380-520."},
    {"role": "received", "content_en": "$400 too high. Will check other suppliers."},
    {"role": "sent", "content_en": "A) Essential $270 B) Standard $310 C) Premium $360."},
    {"role": "received", "content_en": "Price still too high. Another quote for $120."},
    {"role": "sent", "content_en": "A) Non-illuminated $120-150 B) Front-glow 3D $270-290 C) Premium $350-400."},
    {"role": "received", "content_en": "Why is A not enough? I need night visibility. Other guy includes lighting for $120."},
    {"role": "sent", "content_en": "A) Essential Night-Glow $270-290 B) Metal-Trim $310-340 C) Full Metal $360-400."},
    {"role": "received", "content_en": "Why $270 vs $120? They also say LED illuminated waterproof. Sounds same. What am I paying extra for?"},
    {"role": "sent", "content_en": "You're buying first impression. $120 option won't give you that. A) Clean Casual $270-290 B) Modern Sharp $310-340 C) Premium $360-400."},
]

result = analyze_customer_message(
    text="""I hear you. But honestly, I don't really care about 'first impression' marketing talk.
My restaurant is small. It's not some luxury brand.
I just need something that:
1. lights up clearly
2. doesn't break in 1 year
3. fits my budget

Because right now, $270 vs $120 is a big gap.
So I still don't see why I should pay more.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round7.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
