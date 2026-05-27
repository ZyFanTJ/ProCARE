【脚本能力使用指导 (Script Guidance)】
你不需要从头编写所有基础逻辑。系统已经为你预置了强大的辅助库 `backend.app.skills.code_generation.utils`。
请在生成的代码中优先导入并使用以下函数，以提高代码的稳健性：

```python
import sys
import os
from pathlib import Path

# 确保可以导入后端模块
# 1. 尝试将当前工作目录加入路径
sys.path.append(os.getcwd())
# 2. 尝试向上查找直到找到 backend 目录
current = Path(os.getcwd())
while current.name != 'backend' and current.parent != current:
    if (current / 'backend').exists():
        sys.path.append(str(current))
        break
    current = current.parent

try:
    from backend.app.skills.code_generation.utils import safe_load_sheet, resolve_columns, clean_dataframe
except ImportError:
    # Fallback: 如果无法从 backend 导入，尝试直接从 utils 导入 (假设脚本被复制到了同级目录)
    try:
        from utils import safe_load_sheet, resolve_columns, clean_dataframe
    except ImportError:
        print("[Warning] Failed to import skill utils. Defining mock functions.")
        def safe_load_sheet(path, sheet): return pd.read_excel(path, sheet_name=sheet)
        def clean_dataframe(df): return df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        def resolve_columns(df, expected): return {{c: c for c in expected if c in df.columns}}

# 1. 安全加载数据
# df = safe_load_sheet(excel_path, sheet_name)

# 2. 自动清洗
# df = clean_dataframe(df)

# 3. 稳健的列名匹配 (替代手写复杂的列名查找逻辑)
# expected = ["Age", "Gender", "Outcome"]
# mapping = resolve_columns(df, expected)
# df = df.rename(columns=mapping)
```

使用这些工具可以避免常见的“文件锁定”、“列名大小写不匹配”和“空行空列”问题。
