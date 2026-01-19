from typing import Dict
import json
from ..core.llm import LLMClient


class PlanAgent:
    """研究计划生成Agent：以LLM驱动，缺省时回退占位计划。"""

    def __init__(self):
        self.llm = LLMClient()

    def generate_plan(self, topic: str, excel_info: Dict) -> Dict:
        sheet_list = excel_info.get("sheets", []) or []
        prompt = (
            "你是一名医学真实世界研究(RWS)专家。请基于ProCARE框架，根据Excel结构与研究主题，生成初步研究计划(P0)。\n"
            "你的任务是进行高层级的可行性评估和研究设计。\n"
            "请遵循STROBE报告规范，考虑以下点：\n"
            "1. 研究设计(Study Design): 队列研究、病例对照、横断面研究等。\n"
            "2. 核心变量识别: 尝试识别暴露(Exposure)、结局(Outcome)、协变量(Covariate)。\n"
            "3. 数据可行性: 预估缺失情况、样本量是否支持研究目标。\n"
            "4. 统计分析策略: 描述性统计、关联分析、生存分析等。\n\n"
            "输出JSON字段：objective, steps, artifacts。\n"
            "steps应包含清晰的阶段：数据清洗与预处理 -> 队列构建与筛选 -> 统计描述与推断 -> 结果可视化。\n"
            "请确保步骤清晰、可执行（3~5个主要阶段）。\n"
            f"研究目标: {topic}\n"
            f"Excel结构: {json.dumps(sheet_list, ensure_ascii=False)}\n"
            "仅输出JSON，不要解释。"
        )
        buf: list[str] = []
        try:
            final_text = self.llm.generate_stream(prompt, on_chunk=lambda c: buf.append(c or ""))
        except Exception as e:
            final_text = f"[LLM错误] {e}"
        import re
        text = final_text if final_text is not None else "" + "".join(buf)
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)
        try:
            plan = json.loads(text)
        except Exception:
            plan = {
                "objective": f"围绕主题『{topic}』进行数据探索与基础统计分析",
                "steps": [
                    "加载Excel并读取所有Sheet",
                    "对每个Sheet进行描述性统计（行数、字段数、示例数据）",
                    "尝试针对关键字段生成简单的图表（柱状/折线）",
                ],
                "artifacts": {"report": "report.md", "plots": "plots/"},
            }
        plan["topic"] = topic
        return plan

    def stream_plan_iter(self, topic: str, excel_info: Dict):
        sheet_list = excel_info.get("sheets", []) or []
        prompt = (
            "你是一名医学真实世界研究(RWS)专家。请基于ProCARE框架，根据Excel结构与研究主题，生成初步研究计划(P0)。\n"
            "你的任务是进行高层级的可行性评估和研究设计。\n"
            "请遵循STROBE报告规范，考虑以下点：\n"
            "1. 研究设计(Study Design): 队列研究、病例对照、横断面研究等。\n"
            "2. 核心变量识别: 尝试识别暴露(Exposure)、结局(Outcome)、协变量(Covariate)。\n"
            "3. 数据可行性: 预估缺失情况、样本量是否支持研究目标。\n"
            "4. 统计分析策略: 描述性统计、关联分析、生存分析等。\n\n"
            "输出JSON字段：objective, steps, artifacts。\n"
            "steps应包含清晰的阶段：数据清洗与预处理 -> 队列构建与筛选 -> 统计描述与推断 -> 结果可视化。\n"
            "请确保步骤清晰、可执行（3~5个主要阶段）。\n"
            f"研究目标: {topic}\n"
            f"Excel结构: {json.dumps(sheet_list, ensure_ascii=False)}\n"
            "仅输出JSON，不要解释。"
        )
        try:
            for chunk in self.llm.stream_iter(prompt):
                yield chunk
        except Exception as e:
            yield f"[LLM错误] {e}"

    @staticmethod
    def _detect_selected_sheets(base_plan: Dict, sheets: list) -> list:
        """从计划文本中自动检测被提及的sheet名称，若未检测到则回退前若干个。"""
        mentioned = set()
        # 在 objective 与 steps 中查找直接提及的sheet名
        haystacks = []
        if isinstance(base_plan.get("objective"), str):
            haystacks.append(base_plan.get("objective", ""))
        steps = base_plan.get("steps", []) or []
        for s in steps:
            if isinstance(s, str):
                haystacks.append(s)
        # 简单包含匹配
        for name in sheets:
            for h in haystacks:
                try:
                    if name and isinstance(h, str) and name.lower() in h.lower():
                        mentioned.add(name)
                        break
                except Exception:
                    pass
        # 若无匹配，默认选取前N个
        if not mentioned:
            N = 6
            return sheets[:N]
        return list(mentioned)

    def generate_refined_plan(
        self,
        topic: str,
        excel_info: Dict,
        base_plan: Dict,
        selected_sheets: list | None = None,
    ) -> Dict:
        selected_sheets = selected_sheets
        sheets = excel_info.get("sheets", []) or []
        columns = excel_info.get("columns", {}) or {}
        normalized = excel_info.get("normalized_columns", {}) or {}
        profile = excel_info.get("profile", {}) or {}

        if selected_sheets is None:
            selected_sheets = self._detect_selected_sheets(base_plan, sheets)

        # 仅收集被选中sheet的字段与画像信息
        sheets_payload = {}
        for s in selected_sheets:
            sheets_payload[s] = {
                "columns": columns.get(s, []),
                "normalized": normalized.get(s, {}),
                "profile": profile.get(s, {}),
            }

        prompt = (
            "你是一名医学真实世界研究专家。基于初步计划(P0)和详细的数据画像(Phi)，生成详细的可执行计划(Pd)。\n"
            "请利用画像中的'knowledge'信息(变量角色、语义映射)进行字段级的操作化定义。\n"
            "要求：\n"
            "1. 语义角色标注: 明确指定每个分析步骤使用的具体字段及其角色(X, Y, Confounders)。\n"
            "2. 统计方法映射: 根据变量类型和角色选择正确的统计方法(如: 生存分析用KM/Cox, 连续变量比较用t-test/Rank-sum)。\n"
            "3. 规范化: 使用提供的标准化列名或本体映射名。\n"
            "4. 步骤细化: 将P0中的每个步骤拆解为具体的数据操作(Filter, Join, GroupBy, Test)。\n\n"
            f"研究目标: {topic}\n"
            f"初步计划(P0): {json.dumps(base_plan, ensure_ascii=False)}\n"
            f"详细画像(Phi): {json.dumps(sheets_payload, ensure_ascii=False)}\n"
            "严格输出JSON，不要解释。需包含字段：\n"
            "- objective（可精炼）\n"
            "- steps（数组，具体、可执行，明确使用哪些sheet与哪些字段）\n"
            "- artifacts（report, plots）\n"
            "- target_sheets（数组，最终聚焦的sheet名）\n"
            "- required_fields（对象：每个sheet列出关键字段数组）"
        )
        buf: list[str] = []
        try:
            final_text = self.llm.generate_stream(prompt, on_chunk=lambda c: buf.append(c or ""))
        except Exception as e:
            final_text = f"[LLM错误] {e}"
        text = final_text if final_text is not None else "" + "".join(buf)
        import re
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
        try:
            refined = json.loads(text)
        except Exception:
            print(f"LLM生成细化计划失败，回退使用初步计划: {text}")
            refined = dict(base_plan)
            refined.setdefault("target_sheets", selected_sheets)
            # 根据已知字段生成一个简单required_fields占位
            rf = {}
            for s in selected_sheets:
                rf[s] = columns.get(s, [])[:5]
            refined.setdefault("required_fields", rf)

        refined["topic"] = topic
        return refined

    def stream_refined_plan_iter(
        self,
        topic: str,
        excel_info: Dict,
        base_plan: Dict,
        selected_sheets: list | None = None,
    ):
        sheets = excel_info.get("sheets", []) or []
        columns = excel_info.get("columns", {}) or {}
        normalized = excel_info.get("normalized_columns", {}) or {}
        profile = excel_info.get("profile", {}) or {}
        if selected_sheets is None:
            selected_sheets = self._detect_selected_sheets(base_plan, sheets)
        sheets_payload = {}
        for s in selected_sheets:
            sheets_payload[s] = {
                "columns": columns.get(s, []),
                "normalized": normalized.get(s, {}),
                "profile": profile.get(s, {}),
            }
        prompt = (
            "你是一名医学真实世界研究专家。基于初步计划(P0)和详细的数据画像(Phi)，生成详细的可执行计划(Pd)。\n"
            "请利用画像中的'knowledge'信息(变量角色、语义映射)进行字段级的操作化定义。\n"
            "要求：\n"
            "1. 语义角色标注: 明确指定每个分析步骤使用的具体字段及其角色(X, Y, Confounders)。\n"
            "2. 统计方法映射: 根据变量类型和角色选择正确的统计方法(如: 生存分析用KM/Cox, 连续变量比较用t-test/Rank-sum)。\n"
            "3. 规范化: 使用提供的标准化列名或本体映射名。\n"
            "4. 步骤细化: 将P0中的每个步骤拆解为具体的数据操作(Filter, Join, GroupBy, Test)。\n\n"
            f"研究目标: {topic}\n"
            f"初步计划(P0): {json.dumps(base_plan, ensure_ascii=False)}\n"
            f"详细画像(Phi): {json.dumps(sheets_payload, ensure_ascii=False)}\n"
            "严格输出JSON，不要解释。需包含字段：\n"
            "- objective\n"
            "- steps\n"
            "- artifacts\n"
            "- target_sheets\n"
            "- required_fields"
        )
        try:
            for chunk in self.llm.stream_iter(prompt):
                yield chunk
        except Exception as e:
            yield f"[LLM错误] {e}"