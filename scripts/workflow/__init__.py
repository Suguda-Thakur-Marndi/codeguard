"""CodeGuard — Phase 11: Multi-Agent Engineering Workflow Package.

Integrates Agency Agents, Serena Codebase Navigation, and Context7 Documentation.
"""

from scripts.workflow.agent_roles import (
    AgentReport,
    AgentRole,
    RoleDefinition,
    TaskInput,
    get_role_definition,
    validate_agent_report,
)
from scripts.workflow.context7_bridge import Context7Bridge
from scripts.workflow.orchestrator import (
    WorkflowOrchestrator,
    WorkflowResult,
    WorkflowStepRecord,
)
from scripts.workflow.serena_bridge import SerenaNavigator

WorkflowStep = WorkflowStepRecord

__all__ = [
    "AgentRole",
    "RoleDefinition",
    "TaskInput",
    "AgentReport",
    "get_role_definition",
    "validate_agent_report",
    "SerenaNavigator",
    "Context7Bridge",
    "WorkflowOrchestrator",
    "WorkflowStepRecord",
    "WorkflowStep",
    "WorkflowResult",
]
