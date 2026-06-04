"""
OCR 识别模块
PaddleOCR 2.9.1
拍照 → OCR → 文字 → 填入输入框 → AI讲解
"""
import io
import logging
from typing import Tuple

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)

_engine = None


def init_ocr():
    global _engine
    if _engine is not None:
        return
    logger.info("正在初始化 PaddleOCR...")
    _engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
    logger.info("PaddleOCR 就绪")


def preprocess_image(image_bytes: bytes, max_size: int = 2048) -> bytes:
    """缩放大图、转RGB、输出JPEG"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        img = Image.open(io.BytesIO(image_bytes)).convert('RGB')

    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True)
    return output.getvalue()


def recognize_text(image_bytes: bytes) -> Tuple[str, float]:
    """识别图片文字，返回 (文本, 置信度)"""
    if _engine is None:
        init_ocr()

    processed = preprocess_image(image_bytes)
    img = Image.open(io.BytesIO(processed))
    result = _engine.ocr(np.array(img), cls=True)

    if not result or not result[0]:
        return "", 0.0

    lines = [line[1][0] for line in result[0]]
    scores = [line[1][1] for line in result[0]]

    return '\n'.join(lines), sum(scores) / len(scores)


def decode_base64_image(data_uri: str) -> bytes:
    """解析 data:image/...;base64,xxx 或纯 base64"""
    from base64 import b64decode
    encoded = data_uri.split(',', 1)[-1] if ',' in data_uri else data_uri
    return b64decode(encoded)
