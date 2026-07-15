"""Test round 8: final showdown - customer chooses simple $120"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "How much for a small restaurant sign?"},
    {"role": "sent", "content_en": "$180-320. Send photo for exact price."},
    {"role": "received", "content_en": "Another quoted $120. Can you match?"},
    {"role": "sent", "content_en": "Which describes you? A) Small takeout B) Standard C) Premium."},
    {"role": "received", "content_en": "No photo. Give me final price."},
    {"role": "sent", "content_en": "A) $180-250 B) $280-380 C) $380-520."},
    {"role": "received", "content_en": "$400 too high."},
    {"role": "sent", "content_en": "A) $270 B) $310 C) $360."},
    {"role": "received", "content_en": "Still too high, other $120."},
    {"role": "sent", "content_en": "A) Non-illuminated $120 B) Front-glow $270 C) Premium $400."},
    {"role": "received", "content_en": "Need night visibility. Other includes lighting for $120."},
    {"role": "sent", "content_en": "A) Essential Night-Glow $270 B) Metal-Trim $310 C) Full Metal $360."},
    {"role": "received", "content_en": "Why $270 vs $120? What am I paying extra for?"},
    {"role": "sent", "content_en": "You're buying first impression. A) Practical $270 B) High-Vis $310 C) Heavy-Duty $360."},
    {"role": "received", "content_en": "I don't care about marketing talk. I just need lights up clearly, doesn't break, fits budget. $270 vs $120 big gap."},
    {"role": "sent", "content_en": "$120 quote uses uncertified parts that break. A) Practical $270-290 B) High-Vis $310-340 C) Heavy-Duty $360-400. Each guarantees bright + lasts."},
]

result = analyze_customer_message(
    text="""Okay I understand the tiers now.
But I'm still stuck on this:
The other guy didn't give me 3 tiers, he just said:
'$120 all-in, LED sign, waterproof, install included'
So from my perspective: yours looks complicated, his looks simple and cheaper.
I'm not trying to overthink this.
I just want something that works.
So why shouldn't I just go with him?""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round8.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
