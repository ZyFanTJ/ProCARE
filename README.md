# ProCARE: A Cognitive Agent Framework for Real-World Studies

**ProCARE** (Profile-driven Cognitive Agent for RWS Evidence) 是一个专为真实世界研究（Real World Study, RWS）设计的认知智能体框架。本项目是 ProCARE 框架的官方参考实现，代码库名为 `HF_ai4research_v2`。

> 本项目基于 [docs/techreport.txt](docs/techreport.txt) 中描述的方法论构建。

---

## 核心理念 (The ProCARE Framework)

ProCARE 旨在解决 RWS 流程中对方法学严谨性、因果假设验证及合规报告的高要求。核心机制是 **基于画像的认知循环 (Profile-Driven Cognitive Loop)**，形式化为：

$$ \Phi \;\xrightarrow{}\; \mathcal{M} \;\xrightarrow{}\; (P, C, R) $$

其中：
- $\Phi$：结构化的异构数据画像（Heterogeneous Data Profile）。
- $\mathcal{M}$：与画像对齐的认知记忆系统（Profile-Aligned Cognitive Memory）。
- $(P, C, R)$：生成的研究计划（Plan）、验证过的可执行代码（Code）与科学报告（Report）。

---

## 系统模块与方法论

系统主要由以下五个核心模块组成，对应论文中的方法论设计：

### 1. 异构数据画像 (Heterogeneous Data Profiling, $\Phi$)
系统不直接处理原始数据，而是将其压缩为结构化元数据画像 $\Phi$，包含两个维度：
- **粒度 (Granularity)**：数据集级 (High) vs 字段级 (Low)。
- **抽象度 (Abstraction)**：结构性 (Structural) vs 知识驱动 (Knowledge-driven)。

| | High Granularity (Dataset/Task) | Low Granularity (Field/Instance) |
|---|---|---|
| **Structural ($\Phi^{\cdot,S}$)** | 表结构关系、统计摘要、质量指标 | 字段类型、基数、分布、缺失机制 |
| **Knowledge ($\Phi^{\cdot,K}$)** | 研究设计模式、变量角色、合规性 | 本体映射、校验状态、合理性检查 |

*代码对应：`backend/app/services/excel_analyzer.py` (ExcelAgent)*

### 2. 认知记忆架构 (Cognitive Memory Architecture, $\mathcal{M}$)
为了支持长程推理并防止幻觉，系统维护了四类与画像对齐的记忆库：
- **Episodic Memory ($\mathcal{M}^{\mathrm{epi}}$)**：动态记录执行轨迹与运行时假设，作为证据链。
- **Working Memory ($\mathcal{M}^{\mathrm{work}}$)**：维护字段级的动态上下文，确保类型一致性。
- **Semantic Memory ($\mathcal{M}^{\mathrm{sem}}$)**：存储高层研究设计原则（来自 $\Phi^{\mathrm{H,K}}$），作为方法学护栏。
- **Procedural Memory ($\mathcal{M}^{\mathrm{proc}}$)**：存储操作策略（如混杂因素调整规则）。

*代码对应：`backend/app/core/memory.py`*

### 3. 分层规划 (Hierarchical Planning)
采用两阶段规划机制，从粗粒度可行性评估到字段级操作化：
1.  **初步计划 ($P_0$)**：基于高粒度画像，制定符合 STROBE 标准的研究设计与分析策略。
2.  **详细执行计划 ($P_d$)**：结合字段级语义（如暴露 $X$、结局 $Y$ 的具体列），生成可执行的蓝图。

*代码对应：`backend/app/agents/plan_agent.py`*

### 4. 约束制导的代码合成 (Constrained Code Synthesis)
通过 **Verifier-Repair** 循环生成可执行代码 $C^*$：
- **Verifier ($V$)**：结合静态分析（Schema检查）与运行时沙箱（Sandbox Execution），检测代码是否违反约束 $\mathcal{C}$。
- **Repair ($R$)**：针对检测到的违规（如 Schema 不匹配、方法学假设未满足），应用最小化编辑进行修复。

*代码对应：`backend/app/agents/code_agent.py` 与 `backend/app/core/react_loop.py`*

### 5. 基于 DAG 的报告生成 (DAG-Based Report Generation)
报告生成被建模为依赖有向无环图 (DAG)。系统计算每个报告任务的 **支持度分数 (Support Score)**（基于变量可用性、时序有效性、样本量与方法一致性），并通过加权拓扑排序动态生成报告章节，确保结论有据可依。

*代码对应：`backend/app/services/report_builder.py`*

---

## 系统架构与目录

```
backend/
├── app/
│   ├── agents/            # 智能体核心 (实现 Plan, Code, Report 生成)
│   ├── core/              # 基础设施 (LLM Client, ReAct Loop, Memory $\mathcal{M}$)
│   ├── services/          # 业务服务
│   │   ├── excel_analyzer.py  # 实现 Heterogeneous Profiling $\Phi$
│   │   ├── executor.py        # 代码执行沙箱
│   │   └── report_builder.py  # DAG-Based Reporting
│   ├── config/            # 配置文件 (Prompt Templates)
│   └── api/               # FastAPI 接口
└── output/                # 运行时产物

frontend/                  # React + Vite 前端界面
```

---

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 16+

### 1. 后端启动

```bash
# 进入后端目录
cd backend

# 创建并激活虚拟环境
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动 API 服务 (默认端口 8000)
uvicorn app.main:app --reload
```

### 2. 前端启动

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问浏览器地址（通常为 `http://localhost:5173`）即可开始使用。

---

## 使用流程

1.  **上传数据**：上传 Excel 文件，系统自动生成 **Heterogeneous Data Profile ($\Phi$)**。
2.  **定义目标**：输入研究主题（$T_{\text{goal}}$）。
3.  **认知循环**：
    *   **Planning**：生成初步计划 $P_0$ 与详细计划 $P_d$。
    *   **Coding**：进入 ReAct 循环，通过约束制导合成代码 $C^*$。
    *   **Reporting**：基于 DAG 生成包含完整证据链的学术报告 $R$。
4.  **查看结果**：在界面查看执行日志、统计图表与 Markdown 报告。

---

## 演示

![Demo](docs/AI4RWS.mp4)

---

## 许可

本项目仅供演示与研究用途。请在合规与隐私安全的前提下使用真实世界数据。
