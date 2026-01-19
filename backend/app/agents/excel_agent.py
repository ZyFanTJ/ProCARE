from typing import Optional, Dict
from ..services.excel_analyzer import analyze_excel_structure, refine_excel_profile, refine_excel_profile_stream


class ExcelAgent:
    """负责解析Excel结构，并融合用户补充描述。"""

    def analyze_excel(self, path: str, user_description: Optional[str] = None) -> Dict:
        return analyze_excel_structure(path, user_description=user_description)

    def refine_profile(self, path: str, excel_info: Dict, plan: Dict) -> Dict:
        """在生成计划后，按计划相关sheet进行细致画像。"""
        return refine_excel_profile(path, excel_info=excel_info, plan=plan)

    def refine_profile_stream(self, path: str, excel_info: Dict, plan: Dict):
        return refine_excel_profile_stream(path, excel_info=excel_info, plan=plan)