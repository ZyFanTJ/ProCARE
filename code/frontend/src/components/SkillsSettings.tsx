import React from 'react';
import './SkillsSettings.css';

export default function SkillsSettings() {
    return (
        <div className="skills-container">
            {/* Background Grid */}
            <div className="skills-bg-grid"></div>

            <div className="skills-content">
                <header className="skills-header delay-100">
                    <div className="skills-tag">Core Modules Architecture</div>
                    <h1 className="skills-title">AI4Research Skills</h1>
                    <p className="skills-subtitle">
                        能力全景图谱 - <span>四大核心阶段</span>
                    </p>
                </header>

                <div className="fishbone-grid">
                    <div className="fishbone-main-line"></div>

                    {/* Data & Planning */}
                    <div className="fishbone-node top node-1">
                        <div className="skills-glass-card delay-200">
                            <div className="skills-card-header">
                                <div className="skills-icon-box" style={{ color: '#60a5fa' }}>01</div>
                                <div>
                                    <h2 className="skills-card-title">数据与研究规划</h2>
                                    <p className="skills-card-subtitle">Data & Planning</p>
                                </div>
                            </div>
                            <div className="skills-list">
                                <div className="skill-badge">
                                    <span className="skill-name">data_profiling</span>
                                    <span className="skill-type-tag">Data</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">research_planning</span>
                                    <span className="skill-type-tag">Plan</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">research_planning_refined</span>
                                    <span className="skill-type-tag">Plan</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">sandbox_research</span>
                                    <span className="skill-type-tag">Exp</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Code & Execution */}
                    <div className="fishbone-node bottom node-2">
                        <div className="skills-glass-card delay-300">
                            <div className="skills-card-header">
                                <div className="skills-icon-box" style={{ color: '#4ade80' }}>02</div>
                                <div>
                                    <h2 className="skills-card-title">代码与执行</h2>
                                    <p className="skills-card-subtitle">Code & Execution</p>
                                </div>
                            </div>
                            <div className="skills-list">
                                <div className="skill-badge">
                                    <span className="skill-name">code_generation</span>
                                    <span className="skill-type-tag">Code</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">code_repair</span>
                                    <span className="skill-type-tag">Fix</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Reporting */}
                    <div className="fishbone-node top node-3">
                        <div className="skills-glass-card delay-400">
                            <div className="skills-card-header">
                                <div className="skills-icon-box" style={{ color: '#c084fc' }}>03</div>
                                <div>
                                    <h2 className="skills-card-title">报告生成</h2>
                                    <p className="skills-card-subtitle">Reporting</p>
                                </div>
                            </div>
                            <div className="skills-list">
                                <div className="skill-badge">
                                    <span className="skill-name">report_generation</span>
                                    <span className="skill-type-tag">Write</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Copilot & System */}
                    <div className="fishbone-node bottom node-4">
                        <div className="skills-glass-card delay-500">
                            <div className="skills-card-header">
                                <div className="skills-icon-box" style={{ color: '#f472b6' }}>04</div>
                                <div>
                                    <h2 className="skills-card-title">系统与Copilot辅助</h2>
                                    <p className="skills-card-subtitle">System & Copilot</p>
                                </div>
                            </div>
                            <div className="skills-list">
                                <div className="skill-badge">
                                    <span className="skill-name">copilot_domain_knowledge</span>
                                    <span className="skill-type-tag">Know</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">copilot_page_understanding</span>
                                    <span className="skill-type-tag">Page</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">copilot_system_info</span>
                                    <span className="skill-type-tag">Sys</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">copilot_system_operations</span>
                                    <span className="skill-type-tag">Ops</span>
                                </div>
                                <div className="skill-badge">
                                    <span className="skill-name">frontend_navigation</span>
                                    <span className="skill-type-tag">Nav</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <footer className="skills-footer delay-600">
                    <p>AI4Research v2 · Interactive Frontend View</p>
                </footer>
            </div>
        </div>
    );
}
