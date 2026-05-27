import os
import json

def generate_skills_visualization():
    # Define the logical stages and map skills to them
    data = {
        "name": "🌟 AI4Research Skills",
        "children": [
            {
                "name": "📊 数据与研究规划\n(Data & Planning)",
                "children": [
                    {"name": "data_profiling"},
                    {"name": "research_planning"},
                    {"name": "research_planning_refined"},
                    {"name": "sandbox_research"},
                ]
            },
            {
                "name": "💻 代码与执行\n(Code & Execution)",
                "children": [
                    {"name": "code_generation"},
                    {"name": "code_repair"},
                ]
            },
            {
                "name": "📝 报告生成\n(Reporting)",
                "children": [
                    {"name": "report_generation"},
                ]
            },
            {
                "name": "🤖 Copilot与系统辅助\n(Copilot & System)",
                "children": [
                    {"name": "copilot_domain_knowledge"},
                    {"name": "copilot_page_understanding"},
                    {"name": "copilot_system_info"},
                    {"name": "copilot_system_operations"},
                    {"name": "frontend_navigation"},
                ]
            }
        ]
    }

    # ECharts HTML template
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>AI4Research Skills 能力全景图</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #f8f9fa;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }}
            #main {{
                width: 100vw;
                height: 100vh;
            }}
            .header {{
                position: absolute;
                top: 20px;
                left: 30px;
                z-index: 10;
            }}
            .header h1 {{
                font-size: 28px;
                color: #2c3e50;
                margin: 0;
            }}
            .header p {{
                font-size: 14px;
                color: #7f8c8d;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>AI4Research Skills 全景能力图谱</h1>
            <p>展示各个核心阶段所包含的专属技能模块</p>
        </div>
        <div id="main"></div>
        <script>
            var chartDom = document.getElementById('main');
            var myChart = echarts.init(chartDom);
            
            const graphData = {json.dumps(data)};

            var option = {{
                tooltip: {{
                    trigger: 'item',
                    triggerOn: 'mousemove'
                }},
                series: [
                    {{
                        type: 'tree',
                        data: [graphData],
                        top: '10%',
                        left: '15%',
                        bottom: '10%',
                        right: '20%',
                        symbolSize: 12,
                        label: {{
                            position: 'left',
                            verticalAlign: 'middle',
                            align: 'right',
                            fontSize: 16,
                            fontWeight: 'bold',
                            color: '#34495e',
                            backgroundColor: '#fff',
                            borderColor: '#3498db',
                            borderWidth: 1,
                            borderRadius: 6,
                            padding: [8, 12]
                        }},
                        leaves: {{
                            label: {{
                                position: 'right',
                                verticalAlign: 'middle',
                                align: 'left',
                                fontSize: 14,
                                fontWeight: 'normal',
                                color: '#2c3e50',
                                backgroundColor: '#ecf0f1',
                                borderColor: '#bdc3c7',
                                borderWidth: 1,
                                borderRadius: 4,
                                padding: [6, 10],
                                shadowColor: 'rgba(0, 0, 0, 0.1)',
                                shadowBlur: 3
                            }}
                        }},
                        emphasis: {{
                            focus: 'descendant'
                        }},
                        expandAndCollapse: true,
                        animationDuration: 550,
                        animationDurationUpdate: 750,
                        initialTreeDepth: 2,
                        lineStyle: {{
                            color: '#bdc3c7',
                            width: 2,
                            curveness: 0.5
                        }}
                    }}
                ]
            }};

            option && myChart.setOption(option);
            
            // Auto resize
            window.addEventListener('resize', function() {{
                myChart.resize();
            }});
        </script>
    </body>
    </html>
    """
    
    output_path = os.path.join(os.path.dirname(__file__), "skills_visualization.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✅ 可视化图表已生成: {output_path}")
    print("您可以直接在浏览器中打开此 HTML 文件来查看。")

if __name__ == "__main__":
    generate_skills_visualization()
