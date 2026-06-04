"""
Pydantic 数据模型
定义所有 API 的请求体和响应体
"""
from pydantic import BaseModel, Field
from typing import Optional, List


# ── 请求体 ──────────────────────────────────────────────────

class QuestionRequest(BaseModel):
    """提交题目讲解请求"""
    question_text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="题目的完整文本",
        examples=["甲、乙两人从相距100公里的两地同时出发相向而行，甲的速度是6公里/小时，乙的速度是4公里/小时，问几小时后两人相遇？"]
    )
    rephrase: bool = Field(
        default=False,
        description="是否为重新讲解模式"
    )
    correct_answer: Optional[str] = Field(
        default=None,
        max_length=200,
        description="用户提供的正确答案（如'D'或'10小时'），AI不需要自己算答案，只需解释为什么这个对",
        examples=["D", "10小时"]
    )
    previous_response_id: Optional[str] = Field(
        default=None,
        description="上次讲解的response_id，用于追踪讲解链"
    )


class RephraseRequest(BaseModel):
    """重新讲解请求（换个角度再讲一遍）"""
    question_text: str = Field(..., min_length=1, max_length=5000)
    previous_response_id: str = Field(..., description="要重讲的原始response_id")
    stuck_reason: Optional[str] = Field(
        default=None,
        description="用户卡住的原因：number / logic / formula / other",
        examples=["logic"]
    )
    custom_question: Optional[str] = Field(
        default=None,
        max_length=500,
        description="用户自主输入的问题，如'第二步为什么用乘法而不是除法？'",
        examples=["第二步为什么用乘法而不是除法？"]
    )


class OCRRequest(BaseModel):
    """OCR 识别请求"""
    image_base64: str = Field(
        ...,
        description="Base64编码的图片数据（不含data:image前缀）"
    )


# ── 响应体 ──────────────────────────────────────────────────

class SimilarQuestion(BaseModel):
    """举一反三中的相似题"""
    question: str = Field(..., description="相似题题干")
    answer: str = Field(..., description="正确答案")


class ExplanationResponse(BaseModel):
    """讲解响应"""
    response_id: str = Field(..., description="本次讲解的唯一ID，用于追踪和重讲")
    simple_explanation: str = Field(
        ...,
        description="大白话题意重述：一句话说清题目在问什么"
    )
    step_by_step: List[str] = Field(
        ...,
        min_items=2,
        max_items=4,
        description="分步解析，每步一句话，解释为什么这么想"
    )
    similar_questions: Optional[List[SimilarQuestion]] = Field(
        default=None,
        description="举一反三的2-3道相似题（仅题目+答案，不解析）"
    )
    question_type: Optional[str] = Field(
        default=None,
        description="自动识别出的题型分类",
        examples=["数量关系-行程问题"]
    )
    exam_point: Optional[str] = Field(
        default=None,
        description="具体考点，如'行程问题·相遇追及·求相遇时间'",
        examples=["行程问题·相遇追及·求相遇时间"]
    )
    difficulty: Optional[str] = Field(
        default=None,
        description="难度评级：⭐/⭐⭐/⭐⭐⭐/⭐⭐⭐⭐/⭐⭐⭐⭐⭐",
        examples=["⭐⭐"]
    )
    common_mistake: Optional[str] = Field(
        default=None,
        description="常见易错陷阱，如'很多人会直接用(6+4)/2=5，但这是速度的平均，不是平均速度'",
        examples=["很多人会直接用(6+4)/2=5，但平均速度不是速度的平均"]
    )
    exam_tip: Optional[str] = Field(
        default=None,
        description="考场秒杀技巧，如'选项里有个10，直接看有没有10的倍数关系'",
        examples=["选项中如果两个数成倍数关系，答案往往在它们之间"]
    )
    from_cache: bool = Field(default=False, description="是否来自缓存")
    is_rephrase: bool = Field(default=False, description="是否为重新讲解")


class OCRResponse(BaseModel):
    """OCR 识别响应"""
    text: str = Field(..., description="识别出的文字")
    confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="识别置信度"
    )


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    cache_size: int = 0
    ocr_backend: Optional[str] = None


class CacheStatsResponse(BaseModel):
    """缓存统计"""
    total_entries: int
    max_entries: int
    ttl_seconds: int
