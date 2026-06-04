# 📚 公考AI陪练

> 用大白话帮你搞懂每一道错题 —— 可追问、分步骤、举一反三

---

## 项目结构

```
考公ai/
├── backend/
│   ├── main.py           # FastAPI 主应用（API端点）
│   ├── models.py         # Pydantic 数据模型
│   ├── prompts.py        # Prompt 模板（分题型）
│   ├── cache.py          # MD5 缓存模块
│   ├── ocr.py            # OCR 识别（PaddleOCR/EasyOCR）
│   ├── config.py         # 全局配置
│   └── requirements.txt  # Python 依赖
├── web/
│   └── index.html        # Web 前端原型（单文件）
├── tests/
│   └── examples.json     # 测试用例（3道真实行测题）
├── .env.example          # 环境变量模板
└── README.md             # 本文件
```

---

## 快速开始

### 1. 克隆/进入项目

```bash
cd 考公ai
```

### 2. 安装后端依赖

```bash
cd backend

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

> **如果不需要OCR**，可以先不装 PaddleOCR：
> ```bash
> pip install fastapi uvicorn httpx pydantic python-multipart python-dotenv Pillow
> ```

### 3. 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑 .env，填入你的 DeepSeek API Key
# DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

> **获取API Key**: 访问 https://platform.deepseek.com 注册并获取

### 4. 启动后端

```bash
cd backend
python main.py
# 或者：
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API 文档自动生成在: http://localhost:8000/docs

### 5. 打开前端

直接用浏览器打开 `web/index.html`，或者用任意静态文件服务器：

```bash
# 方式1: 直接用浏览器打开
start web/index.html   # Windows
open web/index.html    # Mac

# 方式2: Python简易服务器
cd web && python -m http.server 3000
# 然后访问 http://localhost:3000
```

> **注意**：前端默认连接 `http://localhost:8000`，如果后端地址不同，修改 `index.html` 中的 `API_BASE` 变量。

---

## API 端点说明

### `POST /api/explain` — 提交题目讲解

```bash
curl -X POST http://localhost:8000/api/explain \
  -H "Content-Type: application/json" \
  -d '{"question_text": "甲、乙两人从相距100公里的两地同时出发相向而行，甲6公里/小时，乙4公里/小时，几小时相遇？"}'
```

返回：
```json
{
  "response_id": "abc123...",
  "simple_explanation": "这道题就是在问两个人面对面一起走，多长时间能把100公里走完。",
  "step_by_step": [
    "步骤1：先想清楚...",
    "步骤2：然后计算..."
  ],
  "similar_questions": [
    {"question": "小明和小红从相距240公里...", "answer": "16小时"}
  ],
  "question_type": "数量关系-行程问题",
  "from_cache": false,
  "is_rephrase": false
}
```

### `POST /api/rephrase` — 换个角度重新讲解

```bash
curl -X POST http://localhost:8000/api/rephrase \
  -H "Content-Type: application/json" \
  -d '{"question_text": "...", "previous_response_id": "abc123...", "stuck_reason": "logic"}'
```

> `stuck_reason` 可选值：`number`（数字没懂）、`logic`（逻辑没顺）、`formula`（公式不理解）、留空（不限角度）

### `POST /api/ocr` — 拍照识别

```bash
curl -X POST http://localhost:8000/api/ocr \
  -F "file=@题目照片.jpg"
```

返回：
```json
{"text": "识别出的题目文字...", "confidence": 0.95}
```

### `GET /api/health` — 健康检查

```bash
curl http://localhost:8000/api/health
```

---

## 部署到生产环境（公众号H5方案）

### 方案：Railway 一键部署（推荐，免费额度够用）

前后端部署在一起，`PRODUCTION=true` 时后端会自动托管前端页面。

```bash
# 1. 安装 Railway CLI
npm i -g @railway/cli

# 2. 登录
railway login

# 3. 部署
cd backend
railway up

# 4. 设置环境变量（Railway 控制台里设）
#    DEEPSEEK_API_KEY=sk-xxx
#    PRODUCTION=true
#    OCR_ENABLED=true
```

部署完成后 Railway 会给你一个域名，比如 `kaogong-ai.up.railway.app`。

> ⚠️ Railway 免费额度每月 $5，对个人项目完全够用。

### 接入微信公众号

```
1. 注册个人订阅号（免费）
   → mp.weixin.qq.com → 立即注册 → 订阅号 → 个人

2. 公众号后台 → 设置与开发 → 公众号设置 → 功能设置
   → JS接口安全域名：填 Railway 给你的域名
   → 业务域名：填同一个域名

3. 公众号后台 → 自定义菜单
   → 添加菜单「AI讲题」
   → 类型选「跳转网页」
   → 地址填 https://你的域名

4. 搞定。用户在微信里打开公众号 → 点菜单 → 直接用。
```

### 配置微信 JS-SDK（可选，提升体验）

在 Railway 环境变量中设置：
```
WECHAT_APPID=wx_xxxxxxxx
WECHAT_APPSECRET=xxxxxxxx
```

不配也能用，配了可以自定义分享文案、隐藏微信右上角多余按钮。

### 绑定自定义域名（可选）

```bash
# Cloudflare 买域名（30元/年）→ DNS 指向 Railway
# Railway 控制台 → Settings → Custom Domain → 填入你的域名
```

> HTTPS 证书 Railway 自动处理，不用你管。

---

## OCR 安装指南

### PaddleOCR（推荐，中文最准）

```bash
# CPU 版本（轻量）
pip install paddlepaddle-cpu paddleocr

# GPU 版本（更快，需要 CUDA）
pip install paddlepaddle-gpu paddleocr
```

首次运行时会自动下载模型文件（约100MB），请耐心等待。

### EasyOCR（备选，安装更简单）

```bash
pip install easyocr
```

在 `.env` 中切换：
```
OCR_BACKEND=easyocr
```

### OCR功能关闭

如果不需要OCR，在 `.env` 中：
```
OCR_ENABLED=false
```

---

## 成本估算

| 场景 | 计算 |
|------|------|
| 假设 | 每天100人，每人5题，缓存命中率70% |
| 实际API调用 | 100 × 5 × 30% = 150次/天 |
| 每次消耗 | ~1000 output tokens × 3元/百万 = 0.003元 |
| 日均成本 | 约 0.3-0.5元 |
| 月均成本 | 约 10-15元 |

> 随着缓存命中率提升（高频考题积累），成本会进一步下降。

---

## 测试用例

运行测试（需要后端已启动）：
```bash
# 使用 tests/examples.json 中的用例测试
cd tests

# 测试第一道题
curl -X POST http://localhost:8000/api/explain \
  -H "Content-Type: application/json" \
  -d "$(python -c "import json; data=json.load(open('examples.json')); print(json.dumps({'question_text': data[0]['question']}))")"
```

测试用例包含3道行测真题：
1. **数量关系-行程问题**：相遇问题
2. **判断推理-逻辑判断**：逆否命题推理
3. **数量关系-工程问题**：合作效率计算

---

## 后续升级路线

| 阶段 | 内容 |
|------|------|
| **MVP（当前）** | Web版 + 文本输入 + 拍照OCR + 大白话讲解 + 举一反三 + 错题本 |
| **V1.1** | 支持语音输入（Web Speech API） |
| **V1.2** | 小程序版（微信原生 + 云开发） |
| **V2.0** | 申论批改、面试模拟 |
| **V2.5** | 深色毛玻璃"电影级质感"UI |

---

## 常见问题

**Q: 为什么前端直接打开无法调用API？**
A: 浏览器CORS策略。确保后端已启动且`main.py`中CORS配置正确。生产环境需将前端部署到同一域名下。

**Q: DeepSeek API 返回的JSON格式不对？**
A: `main.py` 中已内置JSON修复器（`extract_json`函数），会自动处理markdown包裹、多余逗号等常见问题。

**Q: OCR 初始化很慢？**
A: PaddleOCR首次加载需要下载模型，请耐心等待。后续调用很快。

---

## License

MIT — 个人开发者自由使用和修改。
