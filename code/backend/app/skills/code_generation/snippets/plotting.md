【输出与可视化要求】
- 使用 pandas/matplotlib/seaborn 作为主要数据处理与可视化工具。
- 必须导入并使用辅助函数：
  ```python
  try:
      from backend.app.skills.code_generation.utils import (
          set_publication_style, get_palette, save_plot, add_stat_annotation
      )
  except ImportError:
      # Fallback mocks if utils cannot be imported
      import matplotlib.pyplot as plt
      def set_publication_style(): plt.style.use('seaborn-v0_8-whitegrid')
      def get_palette(n=None, style=None): return None
      def save_plot(fig, path): fig.savefig(path, bbox_inches='tight')
      def add_stat_annotation(*args, **kwargs): pass
  ```
- 每个 Sheet 开始前打印：Sheet=<name> shape=<rows, cols>
- 图表保存必须打印：Saved plot: <path>
- 若完成至少一个有效分析输出图 → 打印 TASK_DONE
- 若无任何图输出或发生致命错误 → TASK_FAILED
