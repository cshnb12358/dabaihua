"""
FastAPI 主应用 —— 大白话考公

API 端点：
  POST /api/explain        — 提交题目，获取大白话讲解+分步解析+举一反三
  POST /api/rephrase       — 换个角度重新讲解
  POST /api/ocr            — 上传图片，OCR识别文字
  GET  /api/health         — 健康检查
  GET  /api/cache/stats    — 缓存统计
  GET  /api/wechat/config  — 微信 JS-SDK 签名
"""
import json
import json5
from json_repair import repair_json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
    MAX_TOKENS_FIRST, MAX_TOKENS_REPHRASE,
    TEMPERATURE, TEMPERATURE_REPHRASE, API_TIMEOUT,
    CACHE_ENABLED, OCR_ENABLED, OCR_BACKEND, OCR_MAX_IMAGE_SIZE,
    DEBUG, PRODUCTION,
)
from models import (
    QuestionRequest, RephraseRequest, OCRRequest,
    ExplanationResponse, OCRResponse, HealthResponse, CacheStatsResponse,
    SimilarQuestion,
)
from cache import cache
from prompts import (
    build_system_prompt, build_rephrase_prompt, classify_question,
)

# ── 日志 ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger("kaogong-api")


# ── 应用生命周期 ────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时执行"""
    logger.info("🚀 大白话考公 API 启动")
    logger.info(f"   模型: {LLM_MODEL}")
    logger.info(f"   缓存: {'开启' if CACHE_ENABLED else '关闭'}")
    logger.info(f"   OCR:  {'开启' if OCR_ENABLED else '关闭'}")

    # 预热 OCR 引擎（避免首次调用超时）
    if OCR_ENABLED:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _warm_up_ocr)
        except Exception as e:
            logger.warning(f"OCR预热失败（首次OCR调用时会重试）: {e}")

    yield
    logger.info("👋 大白话考公 API 关闭")


def _warm_up_ocr():
    """在后台线程中预热OCR引擎"""
    from ocr import init_ocr
    logger.info("正在预热 OCR 引擎...")
    init_ocr(OCR_BACKEND)
    logger.info("OCR 引擎预热完成")


app = FastAPI(
    title="大白话考公 API",
    description="每道题都讲大白话 — 帮助考生彻底搞懂每一道错题",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS 中间件 ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 工具函数 ────────────────────────────────────────────────

def extract_json(text: str) -> dict:
    """
    从AI返回的文本中提取JSON
    兼容千问/DeepSeek/OpenAI的各种返回格式
    """
    last_error = None

    # 先清理markdown包裹
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned)

    # 策略1: json-repair 修复（处理换行符/尾部逗号/缺引号等）
    try:
        return json.loads(repair_json(cleaned))
    except Exception:
        pass

    # 策略2: 直接解析
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        last_error = e

    # 策略2: 提取 ```...``` 代码块
    code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 策略3: 找第一个 { 和最后一个 } 之间的内容
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass

    # 策略4: 用 json5 宽松解析（容忍换行符/尾部逗号/单引号）
    try:
        return json5.loads(cleaned)
    except Exception:
        pass

    # 策略5: 修复常见错误后重试
    fixes = [
        (r',\s*([}\]])', r'\1'),           # 尾部多余逗号
        (r'([{,])\s*(\w+)\s*:', r'\1"\2":'),  # key缺引号
    ]
    for pattern, replacement in fixes:
        try:
            fixed = re.sub(pattern, replacement, cleaned)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"无法从AI回复中提取有效JSON。"
        f"原始回复前200字: {text[:200]}"
        f"（最后解析错误: {last_error}）"
    )


async def call_llm(
    system_prompt: str,
    user_message: str,
    max_tokens: int = MAX_TOKENS_FIRST,
    temperature: float = TEMPERATURE,
) -> dict:
    """
    调用LLM API（千问/DeepSeek/OpenAI兼容接口）
    包含重试机制和错误处理
    """
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
    }

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_error = None
    max_retries = 2

    if DEBUG:
        import json as _json
        logger.debug(f"DeepSeek请求payload: {_json.dumps(payload, ensure_ascii=False, indent=2)[:500]}")

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
                response = await client.post(
                    f"{LLM_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 429:
                    # 频率限制，等待后重试
                    wait_time = 2 ** attempt
                    logger.warning(f"API频率限制，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"DeepSeek API 返回错误: {response.status_code} - {response.text[:500]}"
                    )

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # 解析JSON
                parsed = extract_json(content)
                logger.debug(f"API调用成功, tokens: {result.get('usage', {})}")
                return parsed

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"网络错误，重试中 ({attempt+1}/{max_retries}): {e}")
                time.sleep(1)
                continue
            raise HTTPException(
                status_code=504,
                detail=f"DeepSeek API 连接超时，请稍后重试: {str(e)}"
            )

    raise HTTPException(
        status_code=502,
        detail=f"DeepSeek API 调用失败（已重试{max_retries}次）: {str(last_error)}"
    )


def validate_explanation(data: dict) -> dict:
    """
    验证并修复AI返回的数据格式
    确保返回的JSON包含所有必需字段
    """
    # 确保 simple_explanation 存在且非空
    if not data.get("simple_explanation"):
        data["simple_explanation"] = "抱歉，这道题的解析生成出现了问题，请重试。"

    # 确保 step_by_step 是列表且截断到4步
    steps = data.get("step_by_step", [])
    if not isinstance(steps, list) or len(steps) == 0:
        data["step_by_step"] = ['请点击"没懂，再讲一遍"重新获取解析']
    else:
        data["step_by_step"] = steps[:4]

    # 确保 similar_questions 格式正确
    similar = data.get("similar_questions", [])
    if not isinstance(similar, list):
        similar = []
    # 每个元素必须有 question 和 answer
    cleaned = []
    for sq in similar[:3]:  # 最多3道
        if isinstance(sq, dict) and sq.get("question") and sq.get("answer"):
            cleaned.append({
                "question": sq["question"],
                "answer": sq["answer"],
            })
    data["similar_questions"] = cleaned if cleaned else None

    # 可选字段：提供默认值
    if not data.get("exam_point"):
        data["exam_point"] = None
    if not data.get("difficulty"):
        data["difficulty"] = None
    if not data.get("common_mistake"):
        data["common_mistake"] = None
    if not data.get("exam_tip"):
        data["exam_tip"] = None

    return data


# ── API 端点 ────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    return HealthResponse(
        status="ok",
        cache_size=cache.size,
        ocr_backend=OCR_BACKEND if OCR_ENABLED else None,
    )


@app.get("/api/cache/stats", response_model=CacheStatsResponse)
async def cache_stats():
    """缓存统计信息"""
    stats = cache.stats()
    return CacheStatsResponse(
        total_entries=stats['size'],
        max_entries=stats['max_size'],
        ttl_seconds=stats['ttl_seconds'],
    )


@app.post("/api/explain", response_model=ExplanationResponse)
async def explain(request: QuestionRequest):
    """
    提交题目，获取AI讲解

    流程：
    1. 查缓存 → 命中直接返回
    2. 缓存未命中 → 调用DeepSeek API
    3. 写入缓存 → 返回结果
    """
    question_text = request.question_text.strip()

    # 1. 查缓存
    if CACHE_ENABLED:
        cached = cache.get(question_text)
        if cached:
            logger.info(f"缓存命中! (总命中率: {cache.hit_rate:.1%})")
            cached["from_cache"] = True
            cached["is_rephrase"] = False
            return cached

    # 2. 识别题型
    qtype = classify_question(question_text)
    logger.info(f"题目类型: {qtype} | 题目: {question_text[:80]}...")

    # 3. 构建 Prompt 并调用 API
    system_prompt = build_system_prompt(
        question_text, qtype,
        correct_answer=getattr(request, 'correct_answer', None)
    )

    # 构建用户消息
    correct = getattr(request, 'correct_answer', None)
    if correct:
        user_msg = f"题目：{question_text}\n\n正确答案是：{correct}\n请解释为什么这个是对的。"
    else:
        user_msg = f"题目：{question_text}\n\n请帮我分析这道题。"

    try:
        ai_result = await call_llm(
            system_prompt=system_prompt,
            user_message=user_msg,
            max_tokens=MAX_TOKENS_FIRST,
            temperature=TEMPERATURE,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API调用异常: {e}")
        raise HTTPException(status_code=500, detail=f"AI服务异常: {str(e)}")

    # 4. 验证格式
    validated = validate_explanation(ai_result)

    # 5. 组装响应
    response_data = {
        "response_id": str(uuid.uuid4()),
        "simple_explanation": validated["simple_explanation"],
        "step_by_step": validated["step_by_step"],
        "similar_questions": validated.get("similar_questions"),
        "question_type": qtype,
        "exam_point": validated.get("exam_point"),
        "difficulty": validated.get("difficulty"),
        "common_mistake": validated.get("common_mistake"),
        "exam_tip": validated.get("exam_tip"),
        "from_cache": False,
        "is_rephrase": request.rephrase,
    }

    # 6. 写入缓存
    if CACHE_ENABLED:
        cache.set(question_text, response_data)

    return response_data


@app.post("/api/rephrase", response_model=ExplanationResponse)
async def rephrase(request: RephraseRequest):
    """
    换个角度重新讲解（用户点了"没懂"）

    只重新生成 simple_explanation 和 step_by_step，
    similar_questions 复用首次调用缓存中的结果。
    """
    question_text = request.question_text.strip()

    # 1. 获取上次的讲解内容
    previous_data = cache.get(question_text) if CACHE_ENABLED else None

    previous_explanation = ""
    if previous_data:
        previous_explanation = previous_data.get("simple_explanation", "")
        # 合并步骤
        if previous_data.get("step_by_step"):
            previous_explanation += "\n" + "\n".join(previous_data["step_by_step"])

    # 2. 构建重讲 Prompt
    system_prompt = build_rephrase_prompt(
        question_text=question_text,
        previous_explanation=previous_explanation,
        stuck_reason=request.stuck_reason,
        custom_question=request.custom_question,
    )

    logger.info(
        f"重新讲解 | 卡住原因: {request.stuck_reason or '未指定'} "
        f"| 自定义提问: {request.custom_question[:50] if request.custom_question else '无'} "
        f"| 题目: {question_text[:80]}..."
    )

    # 3. 调用 API（较小的 max_tokens，因为只生成解析部分）
    try:
        ai_result = await call_llm(
            system_prompt=system_prompt,
            user_message=question_text,
            max_tokens=MAX_TOKENS_REPHRASE,
            temperature=TEMPERATURE_REPHRASE,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重讲API调用异常: {e}")
        raise HTTPException(status_code=500, detail=f"AI服务异常: {str(e)}")

    # 4. 验证格式
    validated = validate_explanation(ai_result)

    # 5. 组装响应（复用原始缓存的 similar_questions）
    original_similar = previous_data.get("similar_questions") if previous_data else None

    response_data = {
        "response_id": str(uuid.uuid4()),
        "simple_explanation": validated["simple_explanation"],
        "step_by_step": validated["step_by_step"],
        "similar_questions": original_similar,  # 复用！
        "question_type": previous_data.get("question_type") if previous_data else classify_question(question_text),
        "from_cache": False,
        "is_rephrase": True,
    }

    return response_data


@app.post("/api/ocr", response_model=OCRResponse)
async def ocr_endpoint(file: UploadFile = File(...)):
    """
    上传图片进行OCR识别

    支持格式：JPG, PNG, BMP, WEBP
    最大文件大小：10MB（可在config.py调整）

    返回识别出的文字，可直接用于 /api/explain
    """
    if not OCR_ENABLED:
        raise HTTPException(status_code=503, detail="OCR功能未启用，请在config.py中设置 OCR_ENABLED=true")

    # 验证文件类型
    allowed_types = ["image/jpeg", "image/png", "image/bmp", "image/webp"]
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {file.content_type}。支持: JPEG, PNG, BMP, WEBP"
        )

    # 读取文件
    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    # 检查文件大小
    if len(image_bytes) > OCR_MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"图片太大（{len(image_bytes) / 1024 / 1024:.1f}MB），请压缩到10MB以内"
        )

    # 验证图片数据
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="图片为空，请重新上传")

    # 调用OCR
    from ocr import recognize_text, init_ocr

    try:
        # 确保OCR引擎已初始化
        init_ocr(OCR_BACKEND)
        text, confidence = recognize_text(image_bytes, backend=OCR_BACKEND)
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"OCR引擎未安装: {str(e)}"
        )
    except Exception as e:
        logger.error(f"OCR识别失败: {e}")
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="图片中没有识别到文字，请确保图片清晰、文字正对镜头"
        )

    logger.info(f"OCR识别成功, 置信度: {confidence:.2f}, 文字长度: {len(text)}")

    return OCRResponse(text=text.strip(), confidence=round(confidence, 4))


@app.post("/api/ocr_base64", response_model=OCRResponse)
async def ocr_base64(request: OCRRequest):
    """
    通过Base64提交图片进行OCR识别

    适用于前端无法使用FormData的场景（如某些小程序环境）
    """
    if not OCR_ENABLED:
        raise HTTPException(status_code=503, detail="OCR功能未启用")

    from ocr import decode_base64_image, recognize_text, init_ocr

    try:
        image_bytes = decode_base64_image(request.image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64解码失败: {str(e)}")

    if len(image_bytes) > OCR_MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"图片太大（{len(image_bytes) / 1024 / 1024:.1f}MB），请压缩到10MB以内"
        )

    try:
        init_ocr(OCR_BACKEND)
        text, confidence = recognize_text(image_bytes, backend=OCR_BACKEND)
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"OCR引擎未安装: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR识别失败: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="图片中没有识别到文字")

    return OCRResponse(text=text.strip(), confidence=round(confidence, 4))


@app.get("/api/wechat/config")
async def wechat_config(url: str = Query(..., description="当前页面完整URL（不含#）")):
    """
    获取微信 JS-SDK 配置（签名）
    前端在微信浏览器中调用此接口获取 wx.config 所需参数

    使用方式（前端）：
      const cfg = await fetch('/api/wechat/config?url=' + encodeURIComponent(location.href.split('#')[0]));
      wx.config(await cfg.json());
    """
    from wechat import get_js_sdk_config
    config = await get_js_sdk_config(url)
    if config is None:
        raise HTTPException(status_code=503, detail="微信未配置（缺少WECHAT_APPID/APPSECRET）")
    return config


# ── 生产模式：托管前端静态文件 ───────────────────────────────

# 前端文件目录（相对于 backend/ 运行目录）
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

if PRODUCTION and WEB_DIR.exists():
    # 挂载静态资源（CSS/JS/图片等）
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_frontend(full_path: str = ""):
        """
        SPA fallback：非 /api/ 路径全部返回 index.html
        让前端路由（如直接访问 / 子路径）也能正常工作
        """
        # API路径不处理
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)

        index_path = WEB_DIR / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="前端文件未找到")

    @app.on_event("startup")
    async def log_production():
        logger.info("🌐 生产模式：前端已托管，访问根路径即可使用")


# ── 全局异常处理 ────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一错误响应格式"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """捕获未预期的异常"""
    logger.error(f"未预期异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "detail": "服务器内部错误，请稍后重试",
            "status_code": 500,
        },
    )


# ── 启动入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
