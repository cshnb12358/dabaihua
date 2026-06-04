"""
全局配置
所有敏感信息和可调参数集中管理
"""
import os
from dotenv import load_dotenv

load_dotenv()  # 从 .env 文件加载环境变量

# ── LLM API 配置（支持千问/DeepSeek/OpenAI等兼容接口）─────
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "your-api-key-here"))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
LLM_MODEL = os.getenv("LLM_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))

# 千问（阿里云百炼）配置示例：
# LLM_API_KEY=sk-xxx
# LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# LLM_MODEL=qwen-plus

# DeepSeek 配置示例：
# LLM_API_KEY=sk-xxx
# LLM_BASE_URL=https://api.deepseek.com
# LLM_MODEL=deepseek-chat

# API 调用参数
MAX_TOKENS_FIRST = 1000      # 首次讲解的最大输出 token
MAX_TOKENS_REPHRASE = 500    # 重讲时的最大输出 token（只生成解析部分）
TEMPERATURE = 0.7            # 首次讲解使用
TEMPERATURE_REPHRASE = 0.9   # 重讲使用（稍高，鼓励换个角度）
API_TIMEOUT = 30             # 秒

# ── 缓存配置 ────────────────────────────────────────────────
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
CACHE_MAX_SIZE = 10000       # 最多缓存多少条
CACHE_TTL = 86400 * 7        # 缓存有效期（秒），默认7天
# 生产环境建议用 Redis，当前用内存缓存即可

# ── OCR 配置 ────────────────────────────────────────────────
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").lower() == "true"
OCR_BACKEND = os.getenv("OCR_BACKEND", "paddleocr")  # paddleocr | easyocr
OCR_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# ── 服务器配置 ──────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"

# ── 微信公众号配置（可选，个人订阅号也需要）─────────────────
WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_APPSECRET = os.getenv("WECHAT_APPSECRET", "")
# 公众号后台 → 设置与开发 → 公众号设置 → 功能设置 → JS接口安全域名
# 把你的域名填进去即可
