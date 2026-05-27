from typing import Dict, Optional
import json
from ..core.llm import LLMClient
from ..core.skill_manager import SkillManager
from ..skills.research_planning.utils import detect_selected_sheets


class PlanAgent:
    """研究计划生成Agent：以LLM驱动，缺省时回退占位计划。"""

    def __init__(self):
        self.llm = LLMClient()
        self.skill_manager = SkillManager()

    def generate_plan(self, topic: str, excel_info: Dict, job_id: Optional[str] = None, mode: str = "instruction") -> Dict:
        sheet_list = excel_info.get("sheets", []) or []
        
        # 如果是发现模式，且主题是由AI生成的假设（通常包含多个），
        # 我们可以稍微调整Prompt，让它更注重验证这些假设。
        prompt_template = "research_planning"
        if mode == "discovery":
             # 可以在这里选用不同的skill，或者在render时传入参数控制
             pass

        prompt = self.skill_manager.get_skill(prompt_template).render(
            topic=topic,
            excel_structure_json=json.dumps(sheet_list, ensure_ascii=False),
            mode=mode
        )
        buf: list[str] = []
        try:
            final_text = self.llm.generate_stream(prompt, on_chunk=lambda c: buf.append(c or ""), job_id=job_id)
        except Exception as e:
            final_text = f"[LLM错误] {e}"
        import re
        text = final_text if final_text is not None else "" + "".join(buf)
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)
        try:
            plan = json.loads(text)
        except Exception as e:
            print(f"JSON解析错误: {e}")

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

    def stream_plan_iter(self, topic: str, excel_info: Dict, job_id: Optional[str] = None, mode: str = "instruction"):
        sheet_list = excel_info.get("sheets", []) or []
        prompt = self.skill_manager.get_skill("research_planning").render(
            topic=topic,
            excel_structure_json=json.dumps(sheet_list, ensure_ascii=False),
            mode=mode
        )
        try:
            for chunk in self.llm.stream_iter(prompt, job_id=job_id):
                yield chunk
        except Exception as e:
            yield f"[LLM错误] {e}"

    @staticmethod
    def _detect_selected_sheets(base_plan: Dict, sheets: list) -> list:
        """Deprecated: Use backend.app.skills.research_planning.utils.detect_selected_sheets instead."""
        return detect_selected_sheets(base_plan, sheets)

    def generate_refined_plan(
        self,
        topic: str,
        excel_info: Dict,
        base_plan: Dict,
        selected_sheets: list | None = None,
        job_id: Optional[str] = None,
    ) -> Dict:
        selected_sheets = selected_sheets
        sheets = excel_info.get("sheets", []) or []
        columns = excel_info.get("columns", {}) or {}
        profile = excel_info.get("profile", {}) or {}

        if selected_sheets is None:
            selected_sheets = self._detect_selected_sheets(base_plan, sheets)

        # 仅收集被选中sheet的字段与画像信息
        sheets_payload = {}
        for s in selected_sheets:
            sheets_payload[s] = {
                "columns": columns.get(s, []),
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
            final_text = self.llm.generate_stream(prompt, on_chunk=lambda c: buf.append(c or ""), job_id=job_id)
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

    def generate_hypotheses(self, excel_info: Dict, n: int = 10, topic: str = None) -> list[str]:
        """
        基于数据画像生成研究假设。
        """
        sheets = excel_info.get("sheets", []) or []
        columns = excel_info.get("columns", {}) or {}
        
        # 简化版画像，只包含列名和基本信息，避免Prompt过长
        simple_profile = {}
        for s in sheets:
            simple_profile[s] = columns.get(s, [])
            
        context = ""
        if topic:
            context = f"研究方向/模糊主题: {topic}\n"

        prompt = (
            "你是一名资深的医学研究顾问。请基于以下提供的数据集（包含表名和列名），"
            "结合真实世界研究（RWS）的常见范式，进行头脑风暴，提出潜在的临床研究假设。\n\n"
            f"{context}"
            f"数据集信息:\n{json.dumps(simple_profile, ensure_ascii=False)}\n\n"
            f"任务：请列出 {n} 个具有临床意义、且可以通过该数据验证的研究假设（Hypotheses）。\n"
            "输出格式要求：\n"
            "仅输出一个JSON列表，不包含Markdown格式，列表中的每个元素为字符串，描述一个假设。\n"
            "例如：[\"高血压患者服用A药后的心血管事件风险低于服用B药\", \"年龄是影响术后并发症的关键因素\"]\n"
        )
        
        try:
            text = self.llm.generate(prompt)
            import re
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                # Fallback if no JSON found
                lines = [l.strip() for l in text.split('\n') if l.strip().startswith('-') or l.strip().startswith(('1.', '2.'))]
                # Remove numbering if parsed manually
                cleaned_lines = []
                for l in lines:
                    l = re.sub(r'^[\d\-\.\s]+', '', l)
                    cleaned_lines.append(l)
                return cleaned_lines if cleaned_lines else [text]
        except Exception as e:
            print(f"[Hypothesis Generation Error] {e}")
            return ["无法生成假设，请检查数据或重试。"]

    def stream_refined_plan_iter(
        self,
        topic: str,
        excel_info: Dict,
        base_plan: Dict,
        selected_sheets: list | None = None,
        job_id: Optional[str] = None,
    ):
        sheets = excel_info.get("sheets", []) or []
        columns = excel_info.get("columns", {}) or {}
        profile = excel_info.get("profile", {}) or {}
        if selected_sheets is None:
            selected_sheets = self._detect_selected_sheets(base_plan, sheets)
        sheets_payload = {}
        for s in selected_sheets:
            sheets_payload[s] = {
                "columns": columns.get(s, []),
                "profile": profile.get(s, {}),
            }
        prompt = self.skill_manager.get_skill("research_planning_refined").render(
            topic=topic,
            base_plan_json=json.dumps(base_plan, ensure_ascii=False),
            detailed_profile_json=json.dumps(sheets_payload, ensure_ascii=False)
        )
        try:
            for chunk in self.llm.stream_iter(prompt, job_id=job_id):
                yield chunk
        except Exception as e:
            yield f"[LLM错误] {e}"