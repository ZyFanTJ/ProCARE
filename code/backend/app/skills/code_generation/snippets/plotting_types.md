【图表类型规范 (Chart Requirements)】

1. **生存分析 (Kaplan-Meier)**:
   - **必须**显示 Number at Risk 表格（可使用 `lifelines` 库的 `add_at_risk_counts` 或手动绘制）。
   - **必须**在图中标注 Log-rank P-value。
   - 曲线需带有置信区间阴影（Confidence Intervals）。
   - 时间轴单位明确（如 Months, Years）。

2. **箱线图 (Boxplots)**:
   - **必须**叠加原始数据点（Strip plot / Swarm plot），展示数据分布密度。
   - 箱体颜色需透明度适当，数据点颜色需加深。
   - 若进行组间比较，**必须**标注统计检验 P 值（使用 `add_stat_annotation`）。

3. **柱状图 (Bar Charts)**:
   - **必须**包含误差线（Error Bars），明确标注是 SD 还是 SE 或 CI。
   - 推荐叠加数据点（Jitter points）。
   - 显示样本量（n=...）。

4. **散点图 (Scatter Plots)**:
   - 若展示相关性，**必须**添加回归线及置信带。
   - **必须**标注相关系数（Pearson/Spearman r）和 P 值。

5. **通用要求**:
   - 避免使用饼图（Pie Charts）。
   - 避免使用 3D 图表。
   - 所有统计检验结果（P值）需保留 3 位小数，P<0.001 标为 "<0.001"。
