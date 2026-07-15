# AI Studio 垂直外贸发光字短视频工具 — 完整产品方案

> 定位：垂直外贸广告标识（发光字）短视频生产工具
> 核心解决：超长等待、提示词混乱、人物AI假面、无分层音频、封面无钩子、多镜头不可控、场景空洞虚假

---

## 一、城市实景场景库

独立面板位于模板区下方，分城市选择 + 参数开关。

### 内置城市

| 城市 | 风格 |
|------|------|
| 巴黎 | 法式轻奢、黄昏蓝调 |
| 伦敦 | 英伦经典、阴雨氛围 |
| 纽约 | 都市繁华、霓虹夜晚 |
| 东京 | 赛博朋克、街头潮流 |
| 国内商业街 | 市井活力、真实烟火气 |

### 每城市内置参数开关

**街道人流量：** 冷清 / 适中 / 热闹
- 选中「适中」自动添加：模糊远景路人、行走行人、橱窗顾客
- 不抢主角镜头，填充街道空白

**实景质感开关：【纪实摄影质感】**
- 开启后自动追加：real street photography, actual city street, weathered wall texture, old sidewalk cracks, scattered street props, store display windows, street lamp wear traces
- 消除干净无瑕疵的AI虚拟街道

**自定义场景：** 输入城市 + 街道细节，保存到个人场景库，下次一键调用

**负面词自动绑定：** no empty deserted street, no perfectly clean flawless buildings, no plastic fake architectural texture

---

## 二、写实人物服饰库

嵌入【人物写实控制区】，解决衣服假、布料无质感。

### 3类穿搭预设

| 分类 | 适用场景 |
|------|---------|
| 法式轻奢 | 高端门店、美容院、女装店 |
| 街头潮流 | 夜市、潮牌、酒吧 |
| 商务简约 | 酒店、连锁品牌、办公室 |

### 一键选装自动追加

```
cotton fabric texture, natural fabric wrinkles, soft clothing fold, matte textile, real garment stitching, no smooth plastic fake clothes
```

### 附加细节开关

- 服装轻微褶皱 ☑
- 面料自然反光 ☑
- 合身自然版型 ☑

### 人物底层约束（永久生效）

```
real human skin pores, tiny facial blemishes, relaxed micro-expression, natural body posture, no stiff plastic model
```

---

## 三、发光字产品材质库

独立分栏，可单独切换招牌，场景不改动。

### 内置10款外贸发光字英文参数

一键填充，与场景独立解耦：
```
① titanium backlit sign
② fully sealed waterproof LED letters
③ acrylic through-body luminous letters
④ suspended halo glow sign
⑤ mini delicate small letters
⑥ high-brightness night market sign
⑦ color electroplated LED sign
⑧ thick solid impact-resistant sign
⑨ no-drilling easy install sign
⑩ smart dimming sensor sign
```

---

## 四、分镜可视化剧情编辑器

废弃纯文本输入，改为**时间轴可视化分镜**。

### 15秒固定结构

| 时间段 | 叙事阶段 | 内容 |
|--------|---------|------|
| 00:00-00:03 | 【钩子镜头】封面首帧 | 强制吸睛：人物+发光招牌同框，作为视频封面 |
| 00:03-00:08 | 故事铺垫 | 跑车、下车、眼神被招牌吸引 |
| 00:08-00:13 | 核心展示 | 走近门店，完整露出招牌材质光影，远景带路人 |
| 00:13-00:15 | 收尾定格 | 招牌特写，视频末帧同步封面钩子 |

### 功能改造点

- 每段分镜自带「场景细节补充」快捷按钮：路人、街边道具、墙面磨损、橱窗商品
- 分镜自带运镜预设：推拉、慢环绕、微距，避免AI随机乱切
- 支持单独保存整套分镜剧情，场景/招牌可拆分混搭

---

## 五、独立音频配音专区

单独独立模块，和画面渲染分开。支持单独预听、单独重生成配音，不用重跑视频画面。

### 英文解说旁白

- 独立输入框：13s专属英文台词模板
- 4种美式真人音色：优雅女声 / 沉稳男声 / 活力青年 / 知性女声
- 语速滑块：0.85-1.05倍，精准控制13s读完
- 分句停顿识别：逗号/句号自动标记停顿，停顿瞬间BGM自动拉高

### BGM分层逻辑开关（固定功能）

- ☑ 人声解说播放时，BGM自动降低30%音量，不盖住英文解说
- ☑ 钩子镜头、招牌特写、台词停顿，BGM音量自动抬升

### 剧情环境音效库

可绑定对应分镜时间段：
跑车轰鸣、高跟鞋脚步声、街道环境嘈杂人声、推门铃声

丰富场景真实感，解决街道死寂问题。

---

## 六、独立封面钩子生成模块

封面和视频画面分开渲染，保证引流效果。

### 双模式

- **模式A：** 单独生成封面（推荐）
- **模式B：** 截取视频首尾帧

### 封面专属提示词

内置固定钩子公式：人物特写 + 发光招牌主体 + 城市实景街道背景

### 封面预览窗口

- 先生成封面确认效果，再渲染整条视频
- 封面不满意只重绘封面，无需重新渲染视频
- 支持叠加英文引流短句，适配海外社媒

---

## 七、独立负面提示词自动绑定系统

分3组自动绑定，开启对应模式自动加载，无需手动复制。

### 场景防AI虚假（开启纪实质感自动加载）

```
empty deserted street, perfect flawless building wall, plastic fake architecture, smooth unreal pavement, zero pedestrians, clean unrealistic empty shop windows, CG cartoon scene, render fake texture
```

### 服装失真（选中写实穿搭自动加载）

```
plastic smooth fake clothes, stiff garment, no fabric folds, shiny artificial textile, perfect wrinkle-free costume, CG fashion model suit
```

### 人物假面（开启超写实真人永久加载）

```
flawless plastic skin, zero pores, stiff facial expression, unnatural rigid body, perfect airbrushed face, AI doll features
```

---

## 八、导入 & 一键生成流程

### 积木式自由组合流程

```
场景库选城市街道（自动填充人流量+实景参数）
  → 服饰库选穿搭 + 开启真人写实
    → 产品库选发光字招牌
      → 分镜编辑器核对15s剧情钩子
        → 音频区粘贴英文解说 + 搭配BGM/环境音
          → 独立生成钩子封面预览
            → 一键完整生成视频
```

### 拆分重渲染功能（大幅降低等待时间）

| 变更场景 | 操作 | 耗时 |
|---------|------|------|
| 只改配音解说 | 点击【仅更新音频】 | 10-30s |
| 只不满意封面 | 点击【仅重绘封面】 | 10s |
| 只换招牌材质 | 一键替换产品参数 | 无需渲染 |
| 只更换城市场景 | 一键替换街道参数 | 画面重渲染 |

---

## 九、内置模板预制优化

10套外贸发光字模板全部预制：

- 每套默认开启：纪实街道质感、适中街道人流量、超写实真人皮肤、布料自然褶皱
- 每套预填配套13s英文解说旁白、分层BGM逻辑、专属封面钩子提示词
- 加载模板自动填充全套画面、音频、封面参数，无需手动补充

---

## 十、改造前后对比

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| 剧情 | 纯文本，AI随机发挥 | 可视化15s分镜，固定3s钩子 |
| 封面钩子 | 截取末帧，不可控 | 独立渲染预览，人物+招牌同框 |
| 英文配音 | 无独立面板 | 4种真人音色，可预听可单独重生成 |
| 人物 | 默认AI假面 | 一键写实，毛孔+瑕疵+微表情 |
| 服装 | AI塑料衣 | 布料褶皱+缝线+哑光面料 |
| 场景 | 空洞AI虚拟街道 | 人流量可调+纪实质感+街边道具 |
| 音频 | 文字描述BGM | 人声停顿自动升降+环境音效 |
| 渲染等待 | 每次完整重跑 | 封面/音频/场景可单独重渲染 |
