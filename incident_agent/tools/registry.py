"""Tool registry -- the single place that knows every tool that exists and
which investigation task type(s) each one serves.

This is a small Registry/Factory: Phase 4's Tool Selection Agent and the
Phase 5 evidence-gathering nodes both need "what tools are available for
this task type" without importing 13 tool modules individually and
without hardcoding that list a second time. Adding tool #14 later means
adding it here once, not hunting through node code.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from incident_agent.models.enums import TaskType
from incident_agent.tools.calculator import calculator
from incident_agent.tools.filesystem_tool import filesystem_list_directory, filesystem_read_file
from incident_agent.tools.kafka_tool import (
    kafka_get_broker_status,
    kafka_get_consumer_lag,
    kafka_get_topic_partitions,
)
from incident_agent.tools.knowledge_base_search import knowledge_base_search
from incident_agent.tools.kubernetes_tool import (
    k8s_describe_deployment,
    k8s_get_pod_logs,
    k8s_get_pod_status,
    k8s_get_recent_events,
)
from incident_agent.tools.log_parser import log_parser
from incident_agent.tools.metrics_collector import metrics_collector
from incident_agent.tools.postgres_tool import (
    postgres_get_connection_pool_stats,
    postgres_get_replication_status,
    postgres_get_slow_queries,
)
from incident_agent.tools.python_repl import python_repl
from incident_agent.tools.redis_tool import (
    redis_get_connection_status,
    redis_get_eviction_stats,
    redis_get_memory_stats,
)
from incident_agent.tools.rest_api import rest_api_call
from incident_agent.tools.sql_query import sql_query
from incident_agent.tools.vector_search import vector_search

ALL_TOOLS: list[BaseTool] = [
    calculator,
    filesystem_list_directory,
    filesystem_read_file,
    kafka_get_broker_status,
    kafka_get_consumer_lag,
    kafka_get_topic_partitions,
    knowledge_base_search,
    k8s_describe_deployment,
    k8s_get_pod_logs,
    k8s_get_pod_status,
    k8s_get_recent_events,
    log_parser,
    metrics_collector,
    postgres_get_connection_pool_stats,
    postgres_get_replication_status,
    postgres_get_slow_queries,
    python_repl,
    redis_get_connection_status,
    redis_get_eviction_stats,
    redis_get_memory_stats,
    rest_api_call,
    sql_query,
    vector_search,
]

# Investigation-task-type -> the tools relevant to it. An agent working a
# `log_analysis` task, for instance, should only be offered log-shaped
# tools -- offering `calculator` there would just be noise for the model
# to reject. `general` holds tools any task type may reasonably need.
TOOLS_BY_TASK_TYPE: dict[TaskType, list[BaseTool]] = {
    TaskType.LOG_ANALYSIS: [k8s_get_pod_logs, k8s_get_recent_events, log_parser],
    TaskType.METRICS_ANALYSIS: [
        metrics_collector,
        k8s_get_pod_status,
        k8s_describe_deployment,
        kafka_get_broker_status,
        kafka_get_consumer_lag,
        kafka_get_topic_partitions,
        postgres_get_connection_pool_stats,
        postgres_get_replication_status,
        redis_get_memory_stats,
        redis_get_connection_status,
        redis_get_eviction_stats,
    ],
    TaskType.VECTOR_SEARCH: [knowledge_base_search, vector_search],
    TaskType.SQL_QUERY: [sql_query, postgres_get_slow_queries, postgres_get_connection_pool_stats],
    TaskType.WEB_SEARCH: [rest_api_call],
    TaskType.KNOWLEDGE_GRAPH: [k8s_describe_deployment, kafka_get_topic_partitions],
}

GENERAL_PURPOSE_TOOLS: list[BaseTool] = [calculator, python_repl, filesystem_read_file, filesystem_list_directory]

_TOOLS_BY_NAME: dict[str, BaseTool] = {t.name: t for t in ALL_TOOLS}


def get_tool_by_name(name: str) -> BaseTool:
    """Look up a tool by its `.name` (as an LLM's tool-selection output would
    reference it). Raises `KeyError` with the available names on a miss --
    deliberately not returning `None`, since a node calling this expects the
    tool it asked for to exist or wants a loud, immediate failure.
    """
    try:
        return _TOOLS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"Unknown tool '{name}'. Available tools: {sorted(_TOOLS_BY_NAME)}") from exc


def get_tools_for_task_type(task_type: TaskType) -> list[BaseTool]:
    """Tools relevant to a given investigation task type, plus the general-purpose set."""
    return TOOLS_BY_TASK_TYPE.get(task_type, []) + GENERAL_PURPOSE_TOOLS
