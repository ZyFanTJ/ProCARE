【绘图风格规范 (Journal-Grade Style)】
所有图表必须符合高水平学术期刊（如 NEJM, Nature, Lancet）的发表标准。

1. **初始化设置**:
   - 在代码开头必须调用 `set_publication_style()`。
   - 使用 `get_palette(n, "nejm")` 获取配色方案。

2. **字体与布局**:
   - 字体必须统一使用无衬线字体（Arial 或 Helvetica）。
   - 去除顶部和右侧的边框（Spines）。
   - 坐标轴标签需加粗，刻度标签清晰。
   - 图例（Legend）应放置在图内空白处或图外右侧，避免遮挡数据。

3. **保存规范**:
   - 必须使用 `save_plot(fig, path)` 函数保存。
   - 该函数会自动保存高 DPI 的 PNG 和矢量 PDF 版本。
   - 不要手动调用 `plt.savefig()`。
