"""Test round 9: customer sends screenshot, pushes to $90-100"""
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
    {"role": "sent", "content_en": "A) Essential $270 B) Metal-Trim $310 C) Full Metal $360."},
    {"role": "received", "content_en": "What am I paying extra for?"},
    {"role": "sent", "content_en": "You're buying first impression. A) $270 B) $310 C) $360."},
    {"role": "received", "content_en": "I just need lights up, doesn't break, fits budget."},
    {"role": "sent", "content_en": "A) $270-290 B) $310-340 C) $360-400. Each guarantees bright + lasts."},
    {"role": "received", "content_en": "Yours looks complicated, his $120 all-in simple. Why shouldn't I go with him?"},
    {"role": "sent", "content_en": "You're right $120 exists. Question is who takes responsibility when it fails in 4 months. Lowest cost → $120. Never worry → $270. If $120 works for you, go ahead. If it fails, my door is open."},
]

result = analyze_customer_message(
    text="""I appreciate you being honest. But check this out — I just got a screenshot from the other guy.

His quote:
- LED illuminated sign
- Waterproof (IP65)
- Free installation
- 1 year warranty
- $95 all-in

That's almost half your price AND he includes installation.

Can you at least match $120? Or even $150?

Because $95 with install included is REALLY hard to ignore.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round9.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
