"""
OCR 识别模块
支持多后端：PaddleOCR / EasyOCR / 腾讯云OCR

拍照 → 后端OCR → 返回文字 → 填入输入框 → AI讲解
"""
import base64
import io
import logging
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# 后端实例（懒加载，避免启动时就加载重型模型）
_engine = None
_engine_type: Optional[str] = None


def _get_paddleocr():
    """初始化 PaddleOCR"""
    from paddleocr import PaddleOCR
    return PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)


def _get_easyocr():
    """初始化 EasyOCR（备选方案，安装更轻量）"""
    try:
        import easyocr
        return easyocr.Reader(['ch_sim', 'en'], gpu=False)
    except ImportError:
        raise ImportError(
            "请安装 EasyOCR:\n"
            "  pip install easyocr"
        )


def init_ocr(backend: str = "paddleocr"):
    """
    初始化 OCR 引擎（懒加载）
    第一次调用 OCR 时才真正加载模型
    """
    global _engine, _engine_type

    if _engine is not None:
        return

    logger.info(f"正在初始化 OCR 引擎: {backend}...")

    if backend == "paddleocr":
        _engine = _get_paddleocr()
        _engine_type = "paddleocr"
    elif backend == "easyocr":
        _engine = _get_easyocr()
        _engine_type = "easyocr"
    else:
        raise ValueError(f"不支持的 OCR 后端: {backend}")

    logger.info(f"OCR 引擎初始化完成: {_engine_type}")


def preprocess_image(image_bytes: bytes, max_size: int = 2048) -> bytes:
    """
    图片预处理
    - 过大图片缩小（加快OCR速度，减少内存）
    - 转换为RGB格式
    - 返回处理后的 JPEG 字节
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()
        # verify后需要重新打开
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        # 尝试强制转换
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = img.convert('RGB')
        except Exception as e:
            raise ValueError(f"无法识别图片格式，请重新拍照: {e}")

    # 转为 RGB（处理 PNG 透明通道、CMYK等）
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    # 如果图片尺寸过大，等比缩放
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        logger.debug(f"图片缩放: {w}x{h} → {new_size[0]}x{new_size[1]}")

    # 输出为 JPEG 字节流
    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True)
    return output.getvalue()


def recognize_text(image_bytes: bytes, backend: str = "paddleocr") -> Tuple[str, float]:
    """
    识别图片中的文字

    参数:
        image_bytes: 图片原始字节
        backend: OCR引擎选择

    返回:
        (识别文本, 平均置信度)
    """
    # 懒加载
    if _engine is None:
        init_ocr(backend)

    # 预处理
    processed_bytes = preprocess_image(image_bytes)
    img = Image.open(io.BytesIO(processed_bytes))

    if _engine_type == "paddleocr":
        return _recognize_paddleocr(img)
    elif _engine_type == "easyocr":
        return _recognize_easyocr(img)
    else:
        raise RuntimeError(f"OCR 引擎未初始化")


def _recognize_paddleocr(img: Image.Image) -> Tuple[str, float]:
    """使用 PaddleOCR 识别（支持2.x）"""
    import numpy as np

    img_array = np.array(img)

    result = _engine.ocr(img_array, cls=True)

    if not result or not result[0]:
        return "", 0.0

    texts = []
    scores = []
    for line in result[0]:
        # PaddleOCR 返回: [[[x1,y1],...], (text, confidence)]
        texts.append(line[1][0])
        scores.append(line[1][1])

    full_text = '\n'.join(texts)
    avg_conf = sum(scores) / len(scores) if scores else 0.0
    return full_text, avg_conf


def _recognize_easyocr(img: Image.Image) -> Tuple[str, float]:
    """使用 EasyOCR 识别"""
    import numpy as np

    img_array = np.array(img)

    result = _engine.readtext(img_array)

    if not result:
        return "", 0.0

    # EasyOCR 返回格式: [([x1,y1], [x2,y2], [x3,y3], [x4,y4]), text, confidence]
    texts = []
    confidences = []

    for detection in result:
        text = detection[1]
        conf = detection[2]
        texts.append(text)
        confidences.append(conf)

    full_text = '\n'.join(texts)
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return full_text, avg_conf


def decode_base64_image(data_uri: str) -> bytes:
    """
    解析 Base64 图片数据
    支持格式：
    - data:image/jpeg;base64,xxxx
    - 纯 base64（无前缀）
    """
    if ',' in data_uri:
        # data URI 格式
        header, encoded = data_uri.split(',', 1)
    else:
        encoded = data_uri

    return base64.b64decode(encoded)
