"""
多智能体系统 — 统一注册入口

所有 Agent 在此注册到 AgentRegistry, Supervisor 通过注册表自动构建路由。
新增 Agent 只需: 1) 实现 node_fn  2) 在此 register()  3) 前端 manifest 自动更新
"""

from app.agents.registry import AgentRegistry, AgentDefinition


def register_all_agents():
    """注册所有 Agent 到全局注册表 (模块加载时自动调用)"""

    # 延迟导入避免循环依赖
    from app.agents.supervisor import supervisor_node
    from app.agents.profile_agent import profile_agent_node
    from app.agents.resource_agent import resource_agent_node
    from app.agents.question_agent import question_agent_node
    from app.agents.path_agent import path_agent_node
    from app.agents.evaluation_agent import evaluation_agent_node

    from app.agents.chat_agent import chat_agent_node

    # ── Supervisor ──
    AgentRegistry.register(AgentDefinition(
        name="supervisor", display_name="调度中枢",
        description="意图理解与任务路由, 将用户请求分发给最合适的 Agent",
        icon="Guide", node_fn=supervisor_node, category="supervisor", priority=100,
        keywords=["路由", "调度", "分发"],
    ))

    # ── Chat Agent (从 supervisor 拆分的独立闲聊回复) ──
    AgentRegistry.register(AgentDefinition(
        name="chat_agent", display_name="对话助手",
        description="处理闲聊/问候/感谢等非学习意图的回复, 含画像引导追问",
        icon="ChatDotRound", node_fn=chat_agent_node,
        category="worker", priority=0, terminal=True,
        keywords=["问候", "感谢", "闲聊", "确认", "好", "嗯"],
    ))

    # ── Worker Agents ──
    AgentRegistry.register(AgentDefinition(
        name="profile_agent", display_name="画像采集 Agent",
        description="通过对话式交互构建6维学习画像",
        icon="UserFilled", node_fn=profile_agent_node,
        category="worker", priority=10, terminal=True,
        keywords=["画像", "背景", "目标", "偏好", "我是", "学过"],
    ))

    AgentRegistry.register(AgentDefinition(
        name="resource_agent", display_name="资源生成 Agent",
        description="生成5种个性化学习资源: 文档/导图/习题/视频脚本/代码案例",
        icon="Document", node_fn=resource_agent_node,
        category="worker", priority=20, terminal=True,
        keywords=["资源", "生成", "资料", "文档", "导图", "代码", "教", "什么是"],
    ))

    AgentRegistry.register(AgentDefinition(
        name="question_agent", display_name="出题评估 Agent",
        description="BKT自适应难度出题, 自动批改并更新知识掌握度",
        icon="EditPen", node_fn=question_agent_node,
        category="worker", priority=15, terminal=True,
        keywords=["题目", "做题", "测试", "出题", "考", "练习"],
    ))

    AgentRegistry.register(AgentDefinition(
        name="path_agent", display_name="路径规划 Agent",
        description="知识图谱拓扑排序 + BKT掌握度 + 艾宾浩斯遗忘曲线 → 学习路径",
        icon="Share", node_fn=path_agent_node,
        category="worker", priority=5, terminal=True,
        keywords=["路径", "计划", "学什么", "下一步", "路线", "规划"],
    ))

    AgentRegistry.register(AgentDefinition(
        name="evaluation_agent", display_name="学习评估 Agent",
        description="6维学习评估报告, 含雷达图数据与改进建议",
        icon="DataAnalysis", node_fn=evaluation_agent_node,
        category="worker", priority=5, terminal=True,
        keywords=["评估", "报告", "学得", "水平", "分析", "掌握情况"],
    ))


register_all_agents()
