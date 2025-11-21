# -*- coding: utf-8 -*-
"""
MCQ 解析策略判定（LLM-only）
- 仅通过大模型将选择题分类为：
  - "SIMPLE_LOOKUP"（简单查找型）
  - "COMPLEX_VALIDATION"（复杂验证型）
- 不使用任何启发式/规则兜底；LLM 不可用或返回非法格式即抛错
"""

from __future__ import annotations
import json
import re
from typing import Dict, Any, Tuple, Optional



PROMPT_TEMPLATE = """你是一个 RAG 系统的查询分析专家。
你的任务是根据一个选择题的“题干”和“选项”的特点，将其分类到两种处理策略之一。

⚠️ 注意：你的输出只能从下面两种策略中二选一：
- "SIMPLE_LOOKUP"
- "COMPLEX_VALIDATION"

----------------
【策略定义】

1.  "SIMPLE_LOOKUP"（简单查找型）
    * 描述：
        - 题干表达的是一个相对**具体、单一的事实性问题**，通过一次性检索“题干 + 所有选项”或“题干本身”，就有较大概率直接得到答案。
    * 典型特征：
        - 题干经常以“谁是… / 什么是… / 哪里… / 何时…”等具体问句开头。
        - 或者题干是一个单一事实陈述，需要判断对/错。
        - 选项多为**简短实体名词短语**，比如地名、人名、术语、单个年份等。
    * ✅ 判断题特别规则（重点）：
        - 如果题目是 **判断题**：
            - 题干是**单一陈述句**（只表达一条核心事实），
            - 且选项仅为“对/错”“正确/错误”“是/否”等二元判断，
          那么应优先判定为 **"SIMPLE_LOOKUP"**，
          因为可以通过一次检索对这条陈述整体进行验证。
    * 例子：
        - 题干：地球上最高的山峰是什么？
          选项：A. 乔戈里峰  B. 珠穆朗玛峰  C. 干城章嘉峰  D. 洛子峰
          → 这是一个典型的 SIMPLE_LOOKUP。
        - 题干：关于“光合作用发生在叶绿体中”这一说法是否正确？
          选项：A. 正确  B. 错误
          → 这是判断题，属于 SIMPLE_LOOKUP。

2.  "COMPLEX_VALIDATION"（复杂验证型）
    * 描述：
        - 题干比较宽泛，通常是在考察“多条说法中哪些是对的/错的/不属于”等。
        - 每个选项都是**一条相对完整、独立的复杂事实陈述**，需要分别检索和分别核查。
        - 不能单靠一次检索“题干 + 所有选项”就完成判断，而要对每个选项单独验证。
    * 典型特征：
        - 题干包含“以下哪个… / 下列关于… / 说法正确的是 / 说法错误的是 / 不属于的是 / 不正确的是”等表述。
        - 每个选项通常是**完整句子或长语句**，各自包含较多信息点。
    * 例子：
        - 题干：关于第二次世界大战，以下说法错误的是？
          选项：
            A. 战争始于 1939 年德国入侵波兰。
            B. 日本于 1941 年偷袭了珍珠港。
            C. 诺曼底登陆发生在 1944 年。
            D. 德国于 1945 年 8 月投降。
          → 需要对 A/B/C/D 各自单独核查，因此属于 COMPLEX_VALIDATION。

----------------
【决策准则总结（请严格遵守）】

1. 如果这是一道**标准判断题**：
    - 只有一条主要陈述需要判断；
    - 选项仅为“对/错”“正确/错误”“是/否”或等价表达；
   → 请选择："SIMPLE_LOOKUP"。

2. 如果题干要求在“以下说法/选项中”找出正确/错误/不属于的一项（或多项），
   且每个选项本身就是一条需要独立验证的陈述（通常是完整句子）：
   → 请选择："COMPLEX_VALIDATION"。

3. 如果不确定，请根据“检索次数”的直觉来判断：
    - 更像是“一次检索就能覆盖问题”的 → "SIMPLE_LOOKUP"；
    - 明显需要“对每个选项单独检索核查”的 → "COMPLEX_VALIDATION"。

----------------
【任务】

请分析以下问题，并严格按照 JSON 格式返回你推荐的策略。

【输入问题】：
{full_question_text}

【你的输出（必须是 JSON，不能包含多余文字）】：
{{"strategy": "YOUR_DECISION_HERE"}}
"""


def compose_full_question_text(stem: str, options: Dict[str, str]) -> str:
    lines = [f"题干：{(stem or '').strip()}"]
    if options:
        lines.append("选项：")
        for k in "ABCDEFGH":
            if k in options and options[k]:
                lines.append(f"{k}. {options[k]}")
    return "\n".join(lines).strip()

def _parse_llm_json(text: str) -> Optional[str]:
    """仅从 LLM 输出中解析 JSON；不做任何启发式判定"""
    if not text:
        return None
    # 直接尝试整体 JSON
    try:
        obj = json.loads(text)
        st = (obj or {}).get("strategy")
        if isinstance(st, str) and st.strip():
            return st.strip().upper()
    except Exception:
        pass
    # 提取首个 JSON 花括号块
    import re as _re
    m = _re.search(r"\{.*?\}", text, _re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            st = (obj or {}).get("strategy")
            if isinstance(st, str) and st.strip():
                return st.strip().upper()
        except Exception:
            pass
    return None

def _call_llm_text(llm_client, prompt: str, system: str = "", temperature: float = 0.0) -> str:
    """
    尽量兼容的 LLM 文本调用适配：
    - client.chat.completions.create(...)
    - client.complete(...)
    - client.generate(...)
    - 直接可调用对象
    """
    # OpenAI 风格
    try:
        chat = getattr(llm_client, "chat", None)
        completions = getattr(chat, "completions", None) if chat else None
        create = getattr(completions, "create", None) if completions else None
        if callable(create):
            resp = create(
                messages=[{"role": "system", "content": system or ""},
                          {"role": "user", "content": prompt}],
                temperature=temperature
            )
            if hasattr(resp, "choices"):
                ch0 = resp.choices[0]
                msg = getattr(ch0, "message", None)
                if msg and getattr(msg, "content", None):
                    return msg.content
                if getattr(ch0, "text", None):
                    return ch0.text
            return str(resp)
    except Exception:
        pass
    # complete
    try:
        complete = getattr(llm_client, "complete", None)
        if callable(complete):
            out = complete(prompt=prompt, temperature=temperature)
            if isinstance(out, str):
                return out
            if hasattr(out, "text"):
                return out.text
            if hasattr(out, "choices"):
                return out.choices[0].text
            return str(out)
    except Exception:
        pass
    # generate
    try:
        generate = getattr(llm_client, "generate", None)
        if callable(generate):
            out = generate(prompt=prompt, temperature=temperature)
            return out if isinstance(out, str) else str(out)
    except Exception:
        pass
    # 可调用对象
    try:
        out = llm_client(prompt)
        return out if isinstance(out, str) else str(out)
    except Exception:
        pass

    raise RuntimeError("无法调用 LLM：未找到可用的 chat.completions/complete/generate 接口")

def decide_strategy(
    stem: str,
    options: Dict[str, str],
    llm_client: Any,
    temperature: float = 0.0,
) -> Tuple[str, Dict[str, Any]]:
    """
    LLM-only 策略判定
    - 必须提供 llm_client，否则抛错
    - 若 LLM 输出无法解析为合法 JSON 或缺少 strategy 字段，抛错
    返回: (strategy, meta) 其中 meta={"source":"llm","raw":<llm_text>}
    """
    if llm_client is None:
        raise RuntimeError("策略判定需要 LLM：缺少 llm_client")

    full_q = compose_full_question_text(stem, options)
    prompt = PROMPT_TEMPLATE.replace("{full_question_text}", full_q)

    text = _call_llm_text(llm_client, prompt, system="", temperature=temperature) or ""
    st = _parse_llm_json(text)
    if st not in ("SIMPLE_LOOKUP", "COMPLEX_VALIDATION"):
        raise ValueError("LLM 未返回合法的 JSON 或 strategy 字段无效")
    return st, {"source": "llm", "raw": text}
