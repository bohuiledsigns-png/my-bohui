"""Test round 10: customer has photos, pushes $115, 7-day delivery"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ai_engine import analyze_customer_message

history = [
    {"role": "received", "content_en": "How much for a small restaurant sign?"},
    {"role": "sent", "content_en": "$180-320 range."},
    {"role": "received", "content_en": "Another quoted $120. Match?"},
    {"role": "sent", "content_en": "A) Small B) Standard C) Premium."},
    {"role": "received", "content_en": "No photo. Give final price."},
    {"role": "sent", "content_en": "A) $180-250 B) $280-380 C) $380-520."},
    {"role": "received", "content_en": "$400 too high."},
    {"role": "sent", "content_en": "A) $270 B) $310 C) $360."},
    {"role": "received", "content_en": "Still too high, other $120."},
    {"role": "sent", "content_en": "A) Non-illuminated $120 B) Front-glow $270 C) Premium $400."},
    {"role": "received", "content_en": "Other includes lighting for $120."},
    {"role": "sent", "content_en": "A) Essential $270 B) Metal $310 C) Full $360."},
    {"role": "received", "content_en": "Why $270 vs $120, what am I paying extra?"},
    {"role": "sent", "content_en": "You're buying first impression, not just a light box."},
    {"role": "received", "content_en": "I don't care about marketing. Just need bright, durable, affordable."},
    {"role": "sent", "content_en": "A) $270-290 B) $310-340 C) $360-400. Each guarantees quality."},
    {"role": "received", "content_en": "Yours complicated, his $120 is simple and includes everything."},
    {"role": "sent", "content_en": "Those offers exist. Question is who takes responsibility when it fails. Go with $120 if it fits, my door is open."},
    {"role": "received", "content_en": "Check this screenshot — $95 LED sign, waterproof, free installation, 1 year warranty, $95 all-in. Can you at least match $120?"},
    {"role": "sent", "content_en": "No overseas factory includes US installation labor for $95. Free installation means mounting hardware — we include that too. My floor for certified outdoor sign is $270. If $95 is your hard limit, I understand."},
]

result = analyze_customer_message(
    text="""I'm going to be honest with you.

Another supplier just sent me this:
$115 total
includes LED sign
waterproof
free installation support
7 days delivery

And they also showed me photos. It looks basically the same as yours.

So I don't really see why I should pay $270+.

Unless you can explain it clearly, I'll just go with them.""",
    country="USA",
    history=history
)

out = json.dumps(result, ensure_ascii=False, indent=2)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_round10.json")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"Saved to {out_path}")
