from typing import Dict, List

def detect_selected_sheets(base_plan: Dict, sheets: List[str]) -> List[str]:
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
