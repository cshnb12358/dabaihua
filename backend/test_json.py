"""测试 extract_json 对各种千问返回格式的兼容性"""
import sys
sys.path.insert(0, '.')
from main import extract_json


# 测试1: 带```json包裹
test1 = """```json
{
  "simple_explanation": "test",
  "step_by_step": ["步骤1", "步骤2"],
  "similar_questions": [{"question": "q", "answer": "a"}]
}
```"""
result = extract_json(test1)
print(f"测试1 (```json包裹): {'PASS' if result else 'FAIL'}")

# 测试2: 只有开头的```json但没有结尾```
test2 = """```json
{
  "simple_explanation": "test",
  "step_by_step": ["步骤1", "步骤2"],
  "similar_questions": [{"question": "q", "answer": "a"}]
}"""
result = extract_json(test2)
print(f"测试2 (无结尾```): {'PASS' if result else 'FAIL'}")

# 测试3: 直接JSON
test3 = """{
  "simple_explanation": "test",
  "step_by_step": ["步骤1"],
  "similar_questions": [{"question": "q", "answer": "a"}]
}"""
result = extract_json(test3)
print(f"测试3 (直接JSON): {'PASS' if result else 'FAIL'}")

# 测试4: 有尾部逗号
test4 = """{
  "simple_explanation": "test",
  "step_by_step": ["步骤1", "步骤2"],
  "similar_questions": [{"question": "q", "answer": "a"},],
}"""
result = extract_json(test4)
print(f"测试4 (尾部逗号): {'PASS' if result else 'FAIL'}")
