"""
缓存模块
对相同（或高度相似）的题目直接返回缓存结果，降低成本

策略：
1. 文本标准化后取 MD5 作为缓存键
2. 内存缓存（生产环境建议换 Redis）
3. 支持 TTL 过期和 LRU 淘汰
"""
import hashlib
import re
import time
import threading
from typing import Optional, Dict, Any


class QuestionCache:
    """
    题目缓存

    文本标准化规则：
    - 去除所有空格和换行
    - 全角符号转半角
    - 繁体字转简体（需安装 opencc，可选）
    - 统一为小写
    """

    def __init__(self, max_size: int = 10000, ttl: int = 86400 * 7):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ── 文本标准化 ──────────────────────────────────────────

    @staticmethod
    def normalize(text: str) -> str:
        """
        标准化文本，提高缓存命中率
        相同题目但格式不同 → 标准化后一致 → 命中缓存
        """
        # 1. 全角转半角
        text = text.replace('，', ',').replace('。', '.')
        text = text.replace('：', ':').replace('；', ';')
        text = text.replace('（', '(').replace('）', ')')
        text = text.replace('？', '?').replace('！', '!')
        text = text.replace('“', '"').replace('”', '"')
        text = text.replace('、', ',').replace('～', '~')

        # 2. 去除所有空白字符（空格、换行、制表符）
        text = re.sub(r'\s+', '', text)

        # 3. 统一标点前后的格式
        text = re.sub(r'\s*([,.!?;:()])\s*', r'\1', text)

        # 4. 转小写
        text = text.lower()

        # 5. 去除尾部多余标点
        text = text.strip('.,;:!?，。；：！？')

        return text

    # ── 缓存操作 ────────────────────────────────────────────

    def _make_key(self, text: str) -> str:
        """生成缓存键"""
        normalized = self.normalize(text)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def get(self, text: str) -> Optional[Dict[str, Any]]:
        """
        查询缓存
        返回 None 表示未命中
        """
        key = self._make_key(text)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]
            # 检查是否过期
            if time.time() - entry['timestamp'] > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            # 更新时间戳，实现 LRU（最近访问的更新鲜）
            entry['timestamp'] = time.time()
            return entry['data']

    def set(self, text: str, data: Dict[str, Any]):
        """
        写入缓存
        达到上限时淘汰最旧的10%
        """
        key = self._make_key(text)

        with self._lock:
            # LRU 淘汰
            if len(self._cache) >= self._max_size:
                sorted_keys = sorted(
                    self._cache.keys(),
                    key=lambda k: self._cache[k]['timestamp']
                )
                # 删除最旧的 10%
                remove_count = max(1, len(sorted_keys) // 10)
                for k in sorted_keys[:remove_count]:
                    del self._cache[k]

            self._cache[key] = {
                'data': data,
                'timestamp': time.time(),
            }

    # ── 统计信息 ────────────────────────────────────────────

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def size(self) -> int:
        return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            'size': self.size,
            'max_size': self._max_size,
            'ttl_seconds': self._ttl,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{self.hit_rate:.1%}",
        }


# 全局缓存实例
cache = QuestionCache()
