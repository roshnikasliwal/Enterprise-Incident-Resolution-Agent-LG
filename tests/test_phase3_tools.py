"""Phase 3 tests: every tool's structured-JSON envelope, error handling,
and the security guards on the three highest-risk tools (Python REPL,
Calculator, REST API, Filesystem).
"""

from __future__ import annotations

import json

import pytest

from incident_agent.models.enums import ToolStatus
from incident_agent.tools.calculator import calculator
from incident_agent.tools.filesystem_tool import filesystem_list_directory, filesystem_read_file
from incident_agent.tools.kafka_tool import kafka_get_broker_status, kafka_get_consumer_lag
from incident_agent.tools.knowledge_base_search import knowledge_base_search
from incident_agent.tools.kubernetes_tool import k8s_get_pod_logs, k8s_get_pod_status
from incident_agent.tools.log_parser import log_parser
from incident_agent.tools.metrics_collector import metrics_collector
from incident_agent.tools.postgres_tool import postgres_get_connection_pool_stats, postgres_get_slow_queries
from incident_agent.tools.python_repl import python_repl
from incident_agent.tools.redis_tool import redis_get_memory_stats
from incident_agent.tools.registry import ALL_TOOLS, TOOLS_BY_TASK_TYPE, get_tool_by_name, get_tools_for_task_type
from incident_agent.tools.rest_api import rest_api_call
from incident_agent.tools.sql_query import sql_query
from incident_agent.tools.vector_search import vector_search


def _parse(result_json: str) -> dict:
    payload = json.loads(result_json)
    assert set(payload) >= {"tool_name", "status", "data", "error_message", "latency_ms"}
    return payload


@pytest.mark.unit
class TestCalculator:
    def test_evaluates_arithmetic(self) -> None:
        payload = _parse(calculator.invoke({"expression": "(842.3 - 25) / 25 * 100"}))
        assert payload["status"] == ToolStatus.SUCCESS
        assert payload["data"]["result"] == pytest.approx(3269.2)

    def test_supports_allowed_functions(self) -> None:
        payload = _parse(calculator.invoke({"expression": "sqrt(16) + abs(-4)"}))
        assert payload["data"]["result"] == 8.0

    def test_rejects_dunder_escape_attempt(self) -> None:
        payload = _parse(calculator.invoke({"expression": "().__class__"}))
        assert payload["status"] == ToolStatus.ERROR
        assert "Unsupported expression" in payload["error_message"]

    def test_rejects_unknown_function(self) -> None:
        payload = _parse(calculator.invoke({"expression": "__import__('os').system('echo hi')"}))
        assert payload["status"] == ToolStatus.ERROR


@pytest.mark.unit
class TestPythonRepl:
    def test_executes_and_captures_result(self) -> None:
        payload = _parse(python_repl.invoke({"code": "result = sum(range(10))"}))
        assert payload["status"] == ToolStatus.SUCCESS
        assert payload["data"]["result"] == "45"

    def test_captures_stdout(self) -> None:
        payload = _parse(python_repl.invoke({"code": "print('hello from repl')"}))
        assert "hello from repl" in payload["data"]["stdout"]

    def test_rejects_import_statement(self) -> None:
        payload = _parse(python_repl.invoke({"code": "import os\nresult = os.getcwd()"}))
        assert payload["status"] == ToolStatus.ERROR
        assert "import" in payload["error_message"].lower()

    def test_rejects_dunder_attribute_access(self) -> None:
        payload = _parse(python_repl.invoke({"code": "result = ().__class__.__bases__"}))
        assert payload["status"] == ToolStatus.ERROR

    def test_math_module_is_available(self) -> None:
        payload = _parse(python_repl.invoke({"code": "result = math.sqrt(144)"}))
        assert payload["data"]["result"] == "12.0"


@pytest.mark.unit
class TestFilesystemTool:
    def test_reads_seeded_file(self) -> None:
        payload = _parse(filesystem_read_file.invoke({"path": "deployment_notes.txt"}))
        assert payload["status"] == ToolStatus.SUCCESS
        assert "checkout-api" in payload["data"]["content"]

    def test_lists_sandbox_directory(self) -> None:
        payload = _parse(filesystem_list_directory.invoke({"path": "."}))
        names = {entry["name"] for entry in payload["data"]["entries"]}
        assert "deployment_notes.txt" in names

    def test_rejects_path_traversal(self) -> None:
        payload = _parse(filesystem_read_file.invoke({"path": "../../requirements.md"}))
        assert payload["status"] == ToolStatus.ERROR
        assert "outside" in payload["error_message"].lower()

    def test_rejects_missing_file(self) -> None:
        payload = _parse(filesystem_read_file.invoke({"path": "does_not_exist.txt"}))
        assert payload["status"] == ToolStatus.ERROR


@pytest.mark.unit
class TestRestApiTool:
    def test_rejects_link_local_metadata_address(self) -> None:
        payload = _parse(rest_api_call.invoke({"url": "http://169.254.169.254/latest/meta-data/"}))
        assert payload["status"] == ToolStatus.ERROR
        assert "disallowed" in payload["error_message"].lower()

    def test_rejects_loopback(self) -> None:
        payload = _parse(rest_api_call.invoke({"url": "http://127.0.0.1:8000/admin"}))
        assert payload["status"] == ToolStatus.ERROR

    def test_rejects_non_http_scheme(self) -> None:
        payload = _parse(rest_api_call.invoke({"url": "file:///etc/passwd"}))
        assert payload["status"] == ToolStatus.ERROR


@pytest.mark.unit
class TestSqlQueryTool:
    def test_runs_select(self) -> None:
        payload = _parse(sql_query.invoke({"query": "SELECT * FROM connection_pool_stats LIMIT 3"}))
        assert payload["status"] == ToolStatus.SUCCESS
        assert payload["data"]["row_count"] == 3
        assert "service_name" in payload["data"]["columns"]

    def test_rejects_non_select(self) -> None:
        payload = _parse(sql_query.invoke({"query": "DELETE FROM deployments"}))
        assert payload["status"] == ToolStatus.ERROR

    def test_rejects_multiple_statements(self) -> None:
        payload = _parse(sql_query.invoke({"query": "SELECT 1; DROP TABLE deployments;"}))
        assert payload["status"] == ToolStatus.ERROR


@pytest.mark.unit
class TestLogParser:
    def test_parses_json_lines(self) -> None:
        raw = '{"timestamp": "2026-07-25T08:00:00Z", "level": "ERROR", "message": "boom"}'
        payload = _parse(log_parser.invoke({"raw_text": raw, "source": "svc"}))
        assert payload["data"]["entry_count"] == 1
        assert payload["data"]["entries"][0]["severity"] == "error"

    def test_parses_prefixed_lines(self) -> None:
        raw = "2026-07-25T08:00:00Z ERROR connection refused"
        payload = _parse(log_parser.invoke({"raw_text": raw, "source": "svc"}))
        assert payload["data"]["entries"][0]["severity"] == "error"
        assert payload["data"]["entries"][0]["message"] == "connection refused"

    def test_infers_severity_from_bare_text(self) -> None:
        raw = "panic: unrecoverable error in worker pool"
        payload = _parse(log_parser.invoke({"raw_text": raw, "source": "svc"}))
        assert payload["data"]["entries"][0]["severity"] == "critical"

    def test_skips_blank_lines(self) -> None:
        raw = "line one\n\n\nline two"
        payload = _parse(log_parser.invoke({"raw_text": raw, "source": "svc"}))
        assert payload["data"]["entry_count"] == 2


@pytest.mark.unit
class TestMetricsCollector:
    def test_generates_requested_sample_count(self) -> None:
        payload = _parse(
            metrics_collector.invoke(
                {"component": "kubernetes", "metric_name": "memory_usage_percent", "window_minutes": 10, "interval_seconds": 120}
            )
        )
        assert payload["data"]["sample_count"] == 5

    def test_deterministic_for_same_inputs(self) -> None:
        # Values/anomaly flags are seeded from the inputs and must match; only
        # `timestamp` legitimately differs between calls (derived from `now()`).
        args = {"component": "database", "metric_name": "query_latency_ms", "window_minutes": 5, "interval_seconds": 60}
        first = _parse(metrics_collector.invoke(args))
        second = _parse(metrics_collector.invoke(args))
        first_values = [(s["value"], s["is_anomalous"]) for s in first["data"]["samples"]]
        second_values = [(s["value"], s["is_anomalous"]) for s in second["data"]["samples"]]
        assert first_values == second_values


@pytest.mark.unit
class TestMockInfraTools:
    def test_kubernetes_pod_status_is_deterministic(self) -> None:
        args = {"namespace": "prod", "pod_name": "checkout-api-7f9c"}
        first = _parse(k8s_get_pod_status.invoke(args))
        second = _parse(k8s_get_pod_status.invoke(args))
        assert first["data"] == second["data"]

    def test_kubernetes_pod_logs_returns_entries(self) -> None:
        payload = _parse(k8s_get_pod_logs.invoke({"namespace": "prod", "pod_name": "checkout-api-7f9c"}))
        assert payload["data"]["entries"]

    def test_kafka_broker_status_shape(self) -> None:
        payload = _parse(kafka_get_broker_status.invoke({"cluster": "prod"}))
        assert "brokers_online" in payload["data"]
        assert "under_replicated_partitions" in payload["data"]

    def test_kafka_consumer_lag_shape(self) -> None:
        payload = _parse(kafka_get_consumer_lag.invoke({"consumer_group": "cg", "topic": "orders"}))
        assert payload["data"]["total_lag"] >= 0
        assert payload["data"]["trend"] in {"stable", "degrading"}

    def test_postgres_connection_pool_uses_seeded_data_for_known_service(self) -> None:
        payload = _parse(postgres_get_connection_pool_stats.invoke({"service_name": "checkout-api"}))
        assert payload["data"]["source"] == "observed"
        assert payload["data"]["pool_size"] == 20

    def test_postgres_slow_queries_sorted_descending(self) -> None:
        payload = _parse(postgres_get_slow_queries.invoke({"limit": 5}))
        times = [row["mean_exec_time_ms"] for row in payload["data"]["queries"]]
        assert times == sorted(times, reverse=True)

    def test_redis_memory_stats_shape(self) -> None:
        payload = _parse(redis_get_memory_stats.invoke({"instance": "cache-1"}))
        assert 0 <= payload["data"]["utilization_percent"]


@pytest.mark.unit
class TestVectorAndKnowledgeBaseSearch:
    def test_knowledge_base_search_finds_crashloop_runbook(self) -> None:
        payload = _parse(
            knowledge_base_search.invoke({"query": "pods keep restarting crash loop backoff", "top_k": 3})
        )
        assert payload["status"] == ToolStatus.SUCCESS
        doc_ids = {r["document_id"] for r in payload["data"]["results"]}
        assert "kb-k8s-crashloop" in doc_ids

    def test_knowledge_base_search_filters_by_doc_type(self) -> None:
        payload = _parse(
            knowledge_base_search.invoke({"query": "kafka broker outage", "top_k": 5, "doc_type": "runbook"})
        )
        for result in payload["data"]["results"]:
            assert result["metadata"]["doc_type"] == "runbook"

    def test_generic_vector_search_also_reaches_the_same_store(self) -> None:
        payload = _parse(vector_search.invoke({"query": "connection pool exhaustion slow query", "top_k": 3}))
        assert payload["status"] == ToolStatus.SUCCESS
        assert payload["data"]["result_count"] > 0


@pytest.mark.unit
class TestToolRegistry:
    def test_all_tools_have_unique_names(self) -> None:
        names = [t.name for t in ALL_TOOLS]
        assert len(names) == len(set(names))

    def test_get_tool_by_name_roundtrips(self) -> None:
        assert get_tool_by_name("calculator") is calculator

    def test_get_tool_by_name_raises_with_helpful_message_on_miss(self) -> None:
        with pytest.raises(KeyError, match="Unknown tool 'not_a_real_tool'"):
            get_tool_by_name("not_a_real_tool")

    def test_every_task_type_maps_to_at_least_one_tool(self) -> None:
        for tools in TOOLS_BY_TASK_TYPE.values():
            assert len(tools) > 0

    def test_get_tools_for_task_type_includes_general_purpose_tools(self) -> None:
        from incident_agent.models.enums import TaskType

        tools = get_tools_for_task_type(TaskType.SQL_QUERY)
        assert calculator in tools
        assert sql_query in tools
