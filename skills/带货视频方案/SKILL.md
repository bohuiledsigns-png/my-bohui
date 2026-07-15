# 爆款AI带货视频方案

Turn any LED sign product photo into a complete viral 15s AI short video plan — with scene, character, clothing, audio, cover hook, and negative prompt control.

## When to use

User provides a product photo or product name + key features of an LED sign / light-up letter product. Output is a ready-to-generate video plan matching professional AI video tool inputs.

## Required inputs

- Product photo (or product name + key features + material)
- Target market / city style (default: overseas English market)
- Optional: preferred scene type, character style, clothing style

## Output structure

```
├── 🎯 Target user + pain points + selling points
├── 🌆 Scene setting (city, crowd density, texture)
├── 👤 Character (clothing, realism mode)
├── 🪧 Product material params
├── 🎬 15s storyboard (4 phases, 8-9 shots)
├── 🎙 13s English voiceover + voice tone
├── 🎵 BGM selection + volume curve + SFX timeline
├── 🖼 Cover hook prompt
├── 🤖 Full AI video generation prompt
└── ⛔ Negative prompt bundle (scene/clothing/person)
```

## Core constraints

| Rule | Value |
|------|-------|
| Total duration | 15s exactly |
| Voiceover | 13s (2s freeze at end) |
| Shots | 8-9 smooth transitions |
| Story arc | Hook → Setup → Showcase → Freeze |
| Language | Pure English prompts only |

## BGM volume rules

| Time | Volume | Reason |
|------|--------|--------|
| 0-2s | Off or minimal | Pure ambient SFX build hook |
| 2-3s | Fade in low | Atmosphere before voice |
| 3-13s (voiceover) | -30% to -40% | Never bury the voice |
| Pauses / close-ups / sign light-up | Rise back +10% | Emotion lift |
| 13-15s (ending) | Gradually swell and fade | Emotional close |

## Scene library

### Available cities

| City | Vibe | Best for |
|------|------|----------|
| Paris | French luxury, dusk blue hour | High-end fashion, beauty, boutique |
| London | Classic elegant, rainy mood | Premium retail, hotel |
| New York | Urban vibrant, neon night | Night markets, bars, street shops |
| Tokyo | Cyberpunk, street trendy | LED neon, colorful signs |
| Chinese commercial street | Lively, authentic everyday | Local shops, restaurants |

### Crowd density (adjustable)

| Setting | Effect |
|---------|--------|
| Quiet | Empty street, focus on subject |
| Moderate (recommended) | Blurred background pedestrians, window shoppers, fills empty street |
| Busy | Full street with busy foot traffic |

### Documentary realism toggle

When ON, auto-appends:
```
real street photography, actual city street, weathered wall texture, old sidewalk cracks, scattered street props, store display windows, street lamp wear traces
```

### Custom scene

User can describe custom city + street details. Saved to personal scene library for one-click reuse.

**Scene negative prompt (auto-bound):**
```
no empty deserted street, no perfectly clean flawless buildings, no plastic fake architectural texture
```

## Character & clothing library

### 3 preset styles

| Style | Vibe | Best for |
|-------|------|----------|
| French chic | Effortless elegance, neutral tones | High-end boutiques, salons, hotels |
| Street trendy | Casual, denim, sneakers | Night markets, bars, street food |
| Business classic | Blazer, tailored, minimalist | Corporate, hotel lobbies, franchises |

### Auto-bound fabric realism keywords

```
cotton fabric texture, natural fabric wrinkles, soft clothing fold, matte textile, real garment stitching, no smooth plastic fake clothes
```

### Detail toggles

- ✔ Slight clothing wrinkles
- ✔ Natural fabric light reflection
- ✔ Natural well-fitted silhouette

### Person realism mode (recommended ON)

Permanently active when realism mode is on:
```
real human skin pores, tiny facial blemishes, relaxed micro-expression, natural body posture, no stiff plastic model
```

## Product material library

10 preset LED sign material keywords — switch independently without changing scene or character:

| # | Product | English keywords |
|---|---------|-----------------|
| ① | Titanium brushed backlit sign | brushed titanium stainless steel backlit luminous sign, suspended soft halo glow, seamless metal edge, anti-rust craft |
| ② | Outdoor waterproof LED letters | fully sealed waterproof LED letters, all-weather anti-UV, rubber edge encapsulation, IP65 waterproof |
| ③ | Acrylic through-body luminous | acrylic through-body luminous letters, uniform 3D glow, transparent crystal acrylic, vibrant color |
| ④ | Hotel suspended halo sign | suspended halo glow sign, floating light effect, ceiling mount, premium lobby grade |
| ⑤ | Mini delicate small letters | mini delicate small LED letters, 2-3cm fine detail, precision craft, indoor boutique |
| ⑥ | High-brightness night market | high-brightness night market sign, super luminous LED, visible from distance, eye-catching |
| ⑦ | Color electroplated LED | color electroplated LED sign, rainbow metallic finish, gradient color, fashion bar style |
| ⑧ | Iridescent color-shifting sign | iridescent color-shifting LED sign, rainbow gradient surface, color changes with viewing angle, eye-catching vibrant |
| ⑨ | RGB programmable sign | programmable RGB LED sign, dynamic color cycling, breathing mode, chasing effect, esports cyberpunk style |
| ⑩ | Smart dimming sensor sign | smart dimming sensor sign, auto brightness adjustment, light sensor, energy saving |

## 15-second storyboard structure (4 phases)

```
00:00-00:03  [HOOK] Cover frame — character + sign in same frame, strong visual hook
00:03-00:08  [SETUP] Story setup — arrival, attention drawn to sign
00:08-00:13  [SHOWCASE] Core display — approach sign, full material detail, street ambiance
00:13-00:15  [FREEZE] Ending freeze — sign close-up, matches cover frame
```

### Shot allocation (8-9 shots)

| Shot type | Count | Purpose |
|-----------|-------|---------|
| Wide establishing | ×2 | Set scene (hook + ending) |
| Medium | ×2 | Character action (driving, walking) |
| Close-up / macro | ×3 | Eye expression, sign material, craft detail |
| POV push/pull | ×1-2 |视线引导至招牌 |
| Static freeze | ×1 | Ending frame |

### Camera movement presets

Slow push, orbiting, macro close-up, fade transition, static wide

### Per-shot detail add-ons

Each shot can add: background pedestrians, street props, wall wear, window display items

## Audio control panel

### English voiceover

- **Duration:** Exactly 13 seconds spoken
- **Tone by product:**
  - Premium / luxury → calm male voice or elegant female, slow, weighty
  - Functional / durable → capable female voice, clear, credible
  - Fashion → energetic young voice, trendy
- **Pace:** Natural American intonation, pauses between segments, emotional rise toward end
- **Timing structure:**
  - 0-4s: Hook sentence (problem they recognize)
  - 4-8s: Pain + knowledge insight  
  - 8-13s: Solution + result ("our product fixes this")

### BGM layering logic

- Voiceover playing → BGM auto -30% volume
- Pause / close-up / sign light-up → BGM auto +10% rise
- 13-15s ending → BGM gradually swell and fade out

### SFX timeline (bind to shot segments)

Available sound effects: car engine, brake screech, high-heel footsteps, evening wind, rain, doorbell

## Cover hook module

### Two modes

- **Mode A:** Independent custom cover — dedicated prompt,人物 + 招牌同框
- **Mode B:** Extract video first/last frame

### Cover formula

```
[Character close-up or side profile] + [sign as focal background] + [city street ambiance]
```

### Text overlay

Optional English hook text overlay for TikTok/FB/IG. Example: `Premium Store Sign — Upgrade Your Shop`

## Negative prompt auto-binding system

Three groups, auto-loaded when corresponding mode is enabled:

### Scene anti-AI (loaded with documentary realism)

```
empty deserted street, perfect flawless building wall, plastic fake architecture, smooth unreal pavement, zero pedestrians, clean unrealistic empty shop windows, CG cartoon scene, render fake texture
```

### Clothing anti-AI (loaded with realistic clothing)

```
plastic smooth fake clothes, stiff garment, no fabric folds, shiny artificial textile, perfect wrinkle-free costume, CG fashion model suit
```

### Person anti-AI (loaded with person realism)

```
flawless plastic skin, zero pores, stiff facial expression, unnatural rigid body, perfect airbrushed face, AI doll features
```

## Full workflow

### 1. Analyze product input

| Product type | Target user | Pain points | Selling points |
|-------------|-------------|-------------|----------------|
| Premium material (titanium, brushed) | High-end shop owners | Old sign looks cheap, oxidation, low store grade | Premium look, anti-rust, halo glow |
| Functional (waterproof, anti-UV) | Street shop owners | Rain damage, UV fading, frequent replacement | Durable, sealed, all-weather |
| Decorative (color, neon) | Entertainment venues | Boring storefront, no attraction | Eye-catching, unique, vibrant |

### 2. Choose scene

- Select city based on product vibe
- Set crowd density (default: moderate)
- Enable documentary realism (default: ON)

### 3. Choose character + clothing

- Select clothing style based on scene
- Enable person realism mode (default: ON)

### 4. Set product material

- Select from 10 preset materials
- Or write custom sign keywords

### 5. Build 15s storyboard

- Hook (0-3s): attention grabber with sign
- Setup (3-8s): build context + character
- Showcase (8-13s): full sign display
- Freeze (13-15s): sign close-up

### 6. Write 13s voiceover

- Hook line → Pain/knowledge → Solution/result
- Match tone to product type

### 7. Configure audio

- Select BGM genre
- Enable auto ducking (voiceover → BGM -30%)
- Bind SFX to timeline
- Set voice tone + pace

### 8. Generate cover

- Mode A: custom cover prompt
- Preview before final generation

### 9. Assemble full prompt

Merge: scene params + character params + product params + storyboard + negative prompts

### 10. Output complete plan

Deliver all modules as structured output.

## Modular swap (no full re-render)

| Change | Action | Render cost |
|--------|--------|-------------|
| Change voiceover only | Re-generate audio only | 10-30s |
| Change cover only | Re-generate cover only | ~10s |
| Swap sign material | One-click replace product params | No re-render needed |
| Swap city scene | One-click replace scene + re-render scenes | Partial |
| Change character clothing | One-click swap clothing params | No re-render needed |
