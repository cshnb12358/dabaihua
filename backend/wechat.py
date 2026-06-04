"""
微信公众号 JS-SDK 签名模块
用于在微信内置浏览器中获取 JS-SDK 配置（分享、隐藏菜单等）

注意：个人订阅号的 JS-SDK 权限有限，
基础功能（隐藏菜单按钮、自定义分享）可用。
"""
import hashlib
import json
import time
import logging
from typing import Optional, Dict, Any

import httpx

from config import WECHAT_APPID, WECHAT_APPSECRET

logger = logging.getLogger("kaogong-wechat")

# 内存缓存 access_token 和 jsapi_ticket（避免频繁请求微信API）
_token_cache: Dict[str, Any] = {}


def _is_token_valid(token_type: str) -> bool:
    """检查缓存的token是否还有效（提前5分钟刷新）"""
    entry = _token_cache.get(token_type)
    if not entry:
        return False
    return time.time() < entry["expires_at"] - 300


async def _get_access_token() -> str:
    """获取微信公众号 access_token"""
    if _is_token_valid("access_token"):
        return _token_cache["access_token"]["value"]

    if not WECHAT_APPID or not WECHAT_APPSECRET:
        raise RuntimeError("未配置 WECHAT_APPID 或 WECHAT_APPSECRET")

    url = (
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential"
        f"&appid={WECHAT_APPID}"
        f"&secret={WECHAT_APPSECRET}"
    )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        data = resp.json()

    if "access_token" not in data:
        logger.error(f"获取access_token失败: {data}")
        raise RuntimeError(f"微信API错误: {data.get('errmsg', '未知错误')}")

    _token_cache["access_token"] = {
        "value": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 7200),
    }

    logger.info("access_token 已刷新")
    return data["access_token"]


async def _get_jsapi_ticket() -> str:
    """获取 jsapi_ticket（用于JS-SDK签名）"""
    if _is_token_valid("jsapi_ticket"):
        return _token_cache["jsapi_ticket"]["value"]

    access_token = await _get_access_token()

    url = (
        "https://api.weixin.qq.com/cgi-bin/ticket/getticket"
        f"?access_token={access_token}&type=jsapi"
    )

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        data = resp.json()

    if data.get("errcode") != 0:
        logger.error(f"获取jsapi_ticket失败: {data}")
        raise RuntimeError(f"微信API错误: {data.get('errmsg', '未知错误')}")

    _token_cache["jsapi_ticket"] = {
        "value": data["ticket"],
        "expires_at": time.time() + data.get("expires_in", 7200),
    }

    logger.info("jsapi_ticket 已刷新")
    return data["ticket"]


async def get_js_sdk_config(url: str) -> Optional[Dict[str, Any]]:
    """
    生成微信 JS-SDK 初始化配置

    参数:
        url: 当前页面的完整URL（不含#后面的hash）

    返回:
        {appId, timestamp, nonceStr, signature} 或 None（未配置时）
    """
    if not WECHAT_APPID or not WECHAT_APPSECRET:
        logger.warning("微信未配置，跳过JS-SDK签名")
        return None

    try:
        ticket = await _get_jsapi_ticket()
    except RuntimeError as e:
        logger.error(f"获取ticket失败: {e}")
        return None

    timestamp = str(int(time.time()))
    nonce_str = hashlib.md5(f"{timestamp}{ticket}".encode()).hexdigest()[:16]

    # 签名规则：按字典序拼接 key=value
    sign_str = (
        f"jsapi_ticket={ticket}"
        f"&noncestr={nonce_str}"
        f"&timestamp={timestamp}"
        f"&url={url}"
    )

    signature = hashlib.sha1(sign_str.encode()).hexdigest()

    return {
        "appId": WECHAT_APPID,
        "timestamp": timestamp,
        "nonceStr": nonce_str,
        "signature": signature,
    }
