# -*- coding: utf-8 -*-
"""
utils.mcq.answer_aggregator
—— “仅做抽取 + 问意对齐”的选择题答案汇总与标准答案对比 —— 可直接复用

主函数：
summarize_and_compare(stem, options, std_answer, llm_client, *,
                      strategy: str = "SIMPLE_LOOKUP",
                      per_option=None,
                      simple_explain: str = "",
                      temperature: float = 0.0) -> dict

行为约束（本版核心）：
- SIMPLE_LOOKUP：把（题干+选项）作为上下文提供，但明确提示“仅从综合解析文本中抽取答案字母”；未明确→返回空。
- COMPLEX_VALIDATION：把（题干+选项）和“分项解析”一并提供，先让模型**依据题干**判断问意是「选正确项」还是「选错误项」
  （示例关键词：正确/符合/属于/是 … vs 错误/不正确/不属于/不符合/不是/除了/except …），
  然后**仅从对应选项的“分项解析”里的判定词**抽取应被选择的选项；未出现明确结论→不选。
- 标准答案 std_answer 仅用于返回后的对比（不进入提示词，避免诱导）。
"""

import json
import re
from typing import Dict, List, Optional, Tuple, Any

_LBL_ORDER = "ABCDEFGH"

# ======================= 基础工具 =======================

def _normalize_labels(s: str) -> str:
    """只保留 A-H，去重并按 A-H 顺序合并；空则返回空串。"""
    if not s:
        return ""
    found = [ch for ch in s.upper() if ch in _LBL_ORDER]
    uniq: List[str] = []
    for ch in found:
        if ch not in uniq:
            uniq.append(ch)
    order_map = {ch: i for i, ch in enumerate(_LBL_ORDER)}
    uniq.sort(key=lambda x: order_map[x])
    return "".join(uniq)

def _allowed_labels(options: Dict[str, str]) -> List[str]:
    return [k for k in _LBL_ORDER if k in (options or {}) and (options[k] or "").strip()]

def _restrict_to_allowed(labels: str, allowed: List[str]) -> str:
    """将模型输出的 A-H 进一步限制到 allowed 集合内，保持 A-H 顺序。"""
    if not labels:
        return ""
    allowed_set = set(allowed or [])
    ordered = [ch for ch in _LBL_ORDER if ch in labels and ch in allowed_set]
    # 去重
    seen, out = set(), []
    for ch in ordered:
        if ch not in seen:
            seen.add(ch); out.append(ch)
    return "".join(out)

def _safe_json_extract(text: str) -> Tuple[str, str]:
    """
    从 LLM 文本中尽力抽出 {"final_answer": "...", "justification": "..."}。
    失败则用正则抓取 A-H 作为 final_answer，justification 留空。
    """
    text = text or ""
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            fa = _normalize_labels(obj.get("final_answer") or obj.get("final") or obj.get("labels") or "")
            just = (obj.get("justification") or obj.get("reason") or obj.get("why") or "").strip()
            return fa, just
        except Exception:
            pass
    fa = _normalize_labels("".join(re.findall(r"[A-Ha-h]", text)))
    return fa, ""

# ======================= 超兼容 LLM 调用 =======================

def _extract_text_from_resp(resp: Any) -> Optional[str]:
    """从各式响应对象里尽力提取文本。"""
    if isinstance(resp, str):
        return resp

    if isinstance(resp, dict):
        # OpenAI chat
        ch = resp.get("choices")
        if isinstance(ch, list) and ch:
            msg = ch[0].get("message") or {}
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            if isinstance(ch[0].get("text"), str):
                return ch[0]["text"]
        # 通用字段
        for k in ("output_text", "content", "text"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v
        # Ollama
        msg = resp.get("message")
        if isinstance(msg, dict):
            c = msg.get("content")
            if isinstance(c, str):
                return c
        # Anthropic
        content = resp.get("content")
        if isinstance(content, list) and content:
            texts = []
            for blk in content:
                if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                    texts.append(blk["text"])
            if texts:
                return "\n".join(texts)
        # 兜底嵌套
        for k in ("message", "data"):
            v = resp.get(k)
            if isinstance(v, dict):
                for kk in ("content", "text"):
                    vv = v.get(kk)
                    if isinstance(vv, str) and vv.strip():
                        return vv

    try:
        choices = getattr(resp, "choices", None)
        if choices:
            ch0 = choices[0]
            msg = getattr(ch0, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    return content
            t = getattr(ch0, "text", None)
            if isinstance(t, str):
                return t
    except Exception:
        pass

    for attr in ("output_text", "content", "text"):
        try:
            v = getattr(resp, attr, None)
            if isinstance(v, str) and v.strip():
                return v
        except Exception:
            pass

    try:
        v = getattr(resp, "content", None)
        if isinstance(v, str) and v.strip():
            return v
    except Exception:
        pass
    return None

def _get_model_name(llm_client: Any) -> Optional[str]:
    for attr in ("model", "model_name", "llm_model_name", "default_model"):
        try:
            v = getattr(llm_client, attr, None)
            if isinstance(v, str) and v.strip():
                return v
        except Exception:
            pass
    try:
        cfg = getattr(llm_client, "config", None)
        if cfg and isinstance(cfg, dict):
            v = cfg.get("model") or cfg.get("model_name")
            if isinstance(v, str) and v.strip():
                return v
    except Exception:
        pass
    return None

def _call_llm_chat(llm_client, prompt: str, temperature: float = 0.0) -> str:
    """
    尽最大兼容性调用若干常见接口（见下方顺序）。
    """
    model = _get_model_name(llm_client)
    msgs = [{"role": "user", "content": prompt}]

    # 1) OpenAI 新接口
    try:
        create = getattr(getattr(getattr(llm_client, "chat"), "completions"), "create")
        resp = create(model=model, messages=msgs, temperature=temperature)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 2) OpenAI 旧接口
    try:
        ChatCompletion = getattr(llm_client, "ChatCompletion")
        create = getattr(ChatCompletion, "create")
        resp = create(model=model, messages=msgs, temperature=temperature)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 3) Responses API
    try:
        create = getattr(getattr(llm_client, "responses"), "create")
        try:
            resp = create(model=model, input=prompt, temperature=temperature)
        except TypeError:
            resp = create(model=model, messages=msgs, temperature=temperature)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 4) completions
    try:
        create = getattr(getattr(llm_client, "completions"), "create")
        resp = create(model=model, prompt=prompt, temperature=temperature)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 5) chat(...)
    try:
        chat = getattr(llm_client, "chat")
        try:
            resp = chat(messages=msgs, model=model, temperature=temperature)
        except TypeError:
            try:
                resp = chat(msgs, temperature=temperature)
            except TypeError:
                resp = chat(prompt)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 6) Anthropic
    try:
        messages_api = getattr(llm_client, "messages")
        create = getattr(messages_api, "create")
        resp = create(model=model, messages=msgs, temperature=temperature)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 7) Ollama
    try:
        resp = getattr(llm_client, "chat")(model=model or "llama3", messages=msgs)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    try:
        resp = getattr(llm_client, "generate")(model=model or "llama3", prompt=prompt)
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 8) Cohere
    try:
        generate = getattr(llm_client, "generate")
        resp = generate(model=model, prompt=prompt, temperature=temperature)
        gens = getattr(resp, "generations", None) or (resp.get("generations") if isinstance(resp, dict) else None)
        if gens and len(gens) and hasattr(gens[0], "text"):
            return gens[0].text
        out = _extract_text_from_resp(resp)
        if isinstance(out, str): return out
    except Exception:
        pass
    # 9) complete / generate（仅 prompt）
    for meth in ("complete", "generate"):
        try:
            fn = getattr(llm_client, meth)
            resp = fn(prompt, temperature=temperature)
            out = _extract_text_from_resp(resp)
            if isinstance(out, str): return out
        except Exception:
            pass
    # 10) LangChain：invoke / predict
    for meth in ("invoke", "predict"):
        try:
            fn = getattr(llm_client, meth)
            resp = fn(prompt)
            out = _extract_text_from_resp(resp)
            if isinstance(out, str): return out
        except Exception:
            pass
    # 11) 可调用对象
    try:
        if callable(llm_client):
            try:
                resp = llm_client(messages=msgs)
            except TypeError:
                resp = llm_client(prompt)
            out = _extract_text_from_resp(resp)
            if isinstance(out, str): return out
    except Exception:
        pass

    try:
        attrs = [a for a in dir(llm_client) if not a.startswith("_")]
    except Exception:
        attrs = []
    raise RuntimeError(
        "LLM 客户端不兼容：未匹配已知接口。"
        f" 可用属性：{', '.join(attrs[:40])} ..."
    )

# ======================= 提示词（纯抽取版，含问意对齐） =======================

def _options_block(options: Dict[str, str]) -> str:
    lines = []
    for k in _LBL_ORDER:
        if k in (options or {}) and (options[k] or "").strip():
            lines.append(f"{k}. {options[k].strip()}")
    return "\n".join(lines) if lines else "(无)"

def _build_prompt_extract_simple(stem: str,
                                 options: Dict[str, str],
                                 explain_text: str,
                                 allowed: List[str]) -> str:
    """
    SIMPLE_LOOKUP：
    - 题干与选项仅作为上下文展示；
    - 明确：只从【解析文本】中抽取答案字母（限定集合）。
    """
    allow = "".join(allowed) or "(无)"
    opt_block = _options_block(options)
    return (
f"""你是一个“信息抽取”工具，只做基于文本本身的有限分析：
- 你可以阅读【题干】、【候选答案】和【解析文本】三部分内容；
- 不能使用外部知识或常识判断事实真伪；
- 但可以根据题干文字中“选正确/错误”的要求，以及解析中对各选项的描述，做**局部逻辑判断**；
- 你的任务是：从中抽取“最终应选择的选项字母”。

【题干】（可以用于理解题目要求是选“正确说法”还是“错误说法”等）
{stem.strip() or "（空）"}

【候选答案】（可用于了解每个字母对应的内容，例如 A. 正确 / B. 错误 等）
{opt_block}

【解析文本】（用于判断解析认为哪些选项应被选中）
{explain_text or "（空）"}

你必须严格输出 JSON（不要任何多余文字或注释）：
{{"final_answer":"", "justification":""}}

============================
【字段含义】

1. final_answer
   - 只包含 {allow} 中的**大写字母**。
   - 单选题：final_answer 为一个字母，如 "A"。
   - 多选题：若解析认为有多个应选项，收集所有应选字母，去重后按字母顺序拼成字符串，如 "ACD"。
   - 如果最终无法确定任何“应选的”选项，则 final_answer 设为 ""（空字符串）。

2. justification
   - 可为空 ""；
   - 若不为空，应尽量引用解析文本里的原句或关键词，不得编造。

============================
【决策步骤（务必按顺序执行）】

### 第 1 步：优先寻找“显式给出答案”的语句
如果【解析文本】中出现以下类似表达，直接以这些字母为准：
- “本题选 A”
- “故选 B”
- “因此选择 C”
- “最终选择 A、C”
- “答案为 AB”
- “正确答案为 D”
- “本题答案：A”
- “选 A 和 C”
- 直接复述选项内容并给出参考资料，如“A、A选项内容[业务规定X]”,
等。

处理规则：
- 收集所有在这类句子中被明确点名为“选择/答案”的字母；
- 只保留属于 {allow} 的字母；
- 去重后按字母顺序拼接成 final_answer；
- 若有明显矛盾（例如一处写“本题选 A”，另一处写“答案为 B”，且无法判断哪个是修正），则 final_answer 设为 ""。

如果在这一步已经得到明确答案，后续步骤只用于解释（justification），不要再改变 final_answer。

### 第 2 步：处理“判断题 / 对错题”（选项是“正确/错误”或“是/否”）

这种情况常见形式：
- 题干：给出一条陈述，询问“上述说法是否正确”“下列说法是否正确”等；
- 选项：如 “A. 正确  B. 错误” 或 “A. 是  B. 否”。

在这类题目中：

1）先用【候选答案】识别“判断题模式”：
   - 若某个选项文本几乎就是“正确”“错误”“是”“否”等短语（例如：“A.正确”“B.错误”），
     则可以认为是判断题或对错题。

2）再看【解析文本】对这条说法的评价，例如：
   - “该说法正确，依据……”
   - “该说法错误，与业务规定不符……”
   - “本题判断为正确”
   - “应判断为错误”
   等。

3）根据评价 + 选项文本来确定 final_answer：
   - 如果解析明确表示“该说法正确 / 属于正确说法 / 判断为正确 / 应为正确”，
     且候选答案中存在某个选项，其内容就是“正确/对/是”等：
       → final_answer 为该选项字母。
   - 如果解析明确表示“该说法错误 / 不正确 / 与规定不符 / 判断为错误”，
     且候选答案中存在某个选项，其内容就是“错误/错/否”等：
       → final_answer 为该选项字母。

⚠ 特别说明（对应你遇到的例子）：
- 若【解析文本】类似：**“A.正确[业务规定1]”**
  - 这通常表示：解析在引用“选项 A 的内容为‘正确’，并说明其依据是业务规定1”；
  - 在这种情况下：
    - 因为解析只明确提到了 A，并给出了正面依据，可以认为“选择的是 A 选项”；
    - final_answer 必须只包含 "A"，**绝不能因为题目是判断题就额外把 B（例如“错误”）也加入**。
- 也就是说：
  - 解析中**只出现且正面支持 A** 时 → final_answer = "A"；
  - 不要因为候选答案里还存在“B.错误”就把 B 也加入。

### 第 3 步：一般多选项场景（选“正确说法”还是“错误说法”等）

当题目不是简单 “正确/错误” 两个选项，而是：
- 题干类似：“下列说法正确的是”“关于××，说法错误的是”“不属于××的是”等；
- 每个选项是完整句子或短语。

此时：

1）先从【题干】判断题目要求：
   - 若出现 “正确的是 / 说法正确的是 / 属于正确说法 / 正确的一项”等：
       → 题目要求你选**被解析判定为“正确”的选项**。
   - 若出现 “错误的是 / 不正确的是 / 有误的是 / 不属于的是 / 说法错误的是”等：
       → 题目要求你选**被解析判定为“错误/不正确/不符合”的选项**。

2）再从【解析文本】里，收集对各选项的评价，例如：
   - “A 项正确，B、C 项错误”
   - “B 项说法错误，其余正确”
   - “只有 C 正确”
   - “A、D 正确，B、C 不正确”
   等，建立一个映射：每个字母 → 被描述为“正确”还是“错误”。

3）根据题目要求挑选：
   - 如果题干要求“选正确的说法”，则 final_answer 只包含在解析中被明确标为“正确/对/符合规定”等的字母；
   - 如果题干要求“选错误的说法”，则 final_answer 只包含在解析中被明确标为“错误/不正确/有误/不符合规定”等的字母。

⚠ 非常重要（修正之前“片面排除错误选项”的问题）：
- **绝对不要因为选项被解析标记为“错误/不正确”，就自动把它排除在 final_answer 之外。**
- 该选项是否应被选中，必须结合【题干要求】：
  - 题目若要求选“错误的说法”，则解析认为“错误”的选项**反而是应该被选中的**。

### 第 4 步：缺乏明确信息时的处理

如果：
- 既没有明确“本题选 A / 答案为 B”等语句，
- 也无法从解析中清楚看出各选项是“正确”还是“错误”，
- 或题干要求不清晰（无法判断是选正确还是选错误），

则：
- 不要凭个人理解或常识猜测；
- final_answer 设为 ""；
- justification 可简单留空 "" 或引用一句“解析未明确给出最终选项”的意思（但不能编造解析内容本身）。

============================
【禁止行为总结】

- 不得使用外部知识或常识判断事实真伪。
- 不得仅凭候选答案里的“正确/错误”等字样来推断答案，必须参考【解析文本】的表述。
- 不得因为解析中某选项被标记为“错误/不正确”就自动排除它，必须结合题目要求“选正确还是选错误”来判断。
- 若无法从现有文本得到明确结论，必须让 final_answer 为空字符串 ""，而不是猜测。

请严格按照以上规则，只输出一个合法 JSON：
{{"final_answer":"...", "justification":"..."}}
"""
)


def _build_prompt_extract_per_option(stem: str,
                                     options: Dict[str, str],
                                     per_option: List[Dict],
                                     allowed: List[str]) -> str:
    """
    COMPLEX_VALIDATION：
    - 先根据题干判定问意：选“正确项/符合/属于/为真/是/应选” 还是 选“错误项/不正确/不符合/不属于/为假/不是/除了（except）”
    - 然后**仅依据每个“分项解析”中的判定词**抽取应选项。若未给出明确结论（例如只做背景说明），则不选。
    - 不能使用外部知识，不要根据选项语义自行推断结论。
    """
    allow = "".join(allowed) or "(无)"
    opt_block = _options_block(options)

    subs = []
    for it in per_option or []:
        lab = (it.get("label") or "").strip() or "?"
        ex  = (it.get("explain") or "").strip() or "（空）"
        subs.append(f"{lab}. {ex}")
    sub_block = "\n".join(subs) if subs else "（无分项解析）"

    return (
    f"""你是一个“信息抽取”工具，不进行任何推断或补全，也不使用外部知识。
    你的任务：**先**根据题干判断本题的“选择目标”（选正确项/选错误项），**再**仅依据各“分项解析”的明确结论抽取应被选择的选项字母。
    
    【题干】（用于判定问意）
    {stem.strip() or "（空）"}
    
    【候选答案】
    {opt_block}
    
    【问意判定说明（仅用于确定选择目标，不得据此推断选项真假）】
    - 若题干包含“正确/符合/属于/是/应当/应选/为真/可以/能够/属于/满足”等 → 选择目标为：**选正确项**。
    - 若题干包含“错误/不正确/不符合/不属于/不是/不应/为假/不满足/除了/除…外/except/不…的是/错误的是/不正确的是/不属于的是/不符合的是”等 → 选择目标为：**选错误项（反向选择）**。
    - 若题意不明确或多义，请**谨慎**，在没有把握的情况下宁可少选也不要臆测。
    
    【分项解析】（仅供抽取应选/不选的依据；不得使用外部知识）
    {sub_block}
    
    严格输出 JSON（不要多余文字）：
    {{"final_answer":"", "justification":""}}
    
    抽取规则：
    1) 你必须先确定选择目标（选正确项 / 选错误项），该步骤**仅依据题干措辞**。
    2) 对每个选项，只能依据其“分项解析”中的明确判定词来决定是否“应选”：
       - 能选（正向）：如“正确/成立/为真/符合/属于/可以/应选/建议选择/事实/证据支持”等肯定结论；
       - 反向（当选择目标为‘选错误项’）：如“错误/不成立/为假/不符合/不属于/不应选/不推荐/被否定”等否定结论→应被选中；
       - 若分析直接给出选项和明确的参考资料，表明所给选项为应选答案，例，分析内容为“A.A选项内容[业务规定X]”，“答案A.A选项内容[业务规定X]”等；
       - 若只有背景说明或无明确判定词→不选。
    3) final_answer 只能包含限定集合 {allow} 内的字母，按字母顺序去重合并。
    4) justification：简要给出做出选择的判定词或原句引用（可留空），不得编造。
    """)

# ======================= 对外主函数（仅抽取 + 问意对齐 + 事后对比） =======================

def summarize_and_compare(stem: str,
                          options: Dict[str, str],
                          std_answer: str,
                          llm_client,
                          *,
                          strategy: str = "SIMPLE_LOOKUP",
                          per_option: Optional[List[Dict]] = None,
                          simple_explain: str = "",
                          temperature: float = 0.0) -> Dict:
    """
    - SIMPLE_LOOKUP：题干/选项仅作上下文，**只从 simple_explain 抽取**。
    - COMPLEX_VALIDATION：题干+选项用于“问意判定”；**只从 per_option[*].explain 的判定词抽取**。
    - 之后仅做：规范化 & 限定 allowed；与标准答案对比；组装 summary_block。
    """
    allowed = _allowed_labels(options)
    std_norm = _normalize_labels(std_answer or "")

    if strategy == "COMPLEX_VALIDATION":
        prompt = _build_prompt_extract_per_option(stem, options, per_option or [], allowed)
    else:
        prompt = _build_prompt_extract_simple(stem, options, simple_explain or "", allowed)

    # 调用 LLM（超兼容）
    raw = _call_llm_chat(llm_client, prompt, temperature=temperature)
    final_labels, justification = _safe_json_extract(raw)
    # 仅做格式规范 & 限制到 allowed，不做任何推断
    final_labels = _restrict_to_allowed(_normalize_labels(final_labels), allowed)

    mismatch = False
    if std_norm:
        mismatch = (final_labels != std_norm)

    status_line = "（与标准答案一致）" if (std_norm and not mismatch) else ("（与标准答案不一致）" if std_norm else "（标准答案未知）")
    summary_block = (
        f"\n\n【答案汇总（抽取·问意对齐）】\n"
        f"抽取的最终答案：{final_labels or '（空）'}\n"
        f"依据：{(justification or '（无）')}\n"
        f"对比：标准答案={std_norm or '（未知）'}，{status_line}"
    ).strip("\n")

    return {
        "final_answer": final_labels,
        "justification": justification,
        "std_answer": std_norm,
        "answer_mismatch": bool(mismatch),
        "summary_block": summary_block,
        "raw": raw,
    }
