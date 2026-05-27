import os

def load_snippet(name: str) -> str:
    """
    Loads a markdown snippet from the snippets directory.
    name: The filename (e.g., 'abstract' or 'style_guide')
    """
    # Assuming this file is at backend/app/skills/report_generation/utils.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, "snippets", f"{name}.md")
    
    if not os.path.exists(path):
        return ""
        
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()
