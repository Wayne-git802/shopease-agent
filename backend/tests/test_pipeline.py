"""
Pipeline tests — orchestrator, enrichment, data flow.
"""

import pytest
from unittest.mock import patch


class TestPipelineContext:

    def test_elapsed_ms(self):
        from agents.graph.pipeline import PipelineContext
        ctx = PipelineContext(query="test")
        ctx._start = 100.0
        import time as _time
        with patch.object(_time, 'time', return_value=100.350):
            ms = ctx.elapsed_ms()
        assert 345 <= ms <= 355, f"Expected ~350ms, got {ms}"

    def test_agent_result_all_statuses(self):
        from agents.graph.pipeline import AgentResult, Handoff, AgentCapability
        r = AgentResult(status="success", response={"reply": "hi"})
        assert r.status == "success"

        r = AgentResult(status="fallback")
        assert r.status == "fallback" and r.response is None

        r = AgentResult(status="handoff", handoff=Handoff(target=AgentCapability.PURCHASE))
        assert r.status == "handoff" and r.handoff.target == AgentCapability.PURCHASE

        r = AgentResult(status="error", response={"reply": "fail"})
        assert r.status == "error"

    def test_agent_capability_str_enum(self):
        from agents.graph.pipeline import AgentCapability
        assert AgentCapability.ORDER == "order"
        assert AgentCapability.CART == "cart"
        assert AgentCapability.ORDER.is_core()

    def test_handoff_typed(self):
        from agents.graph.pipeline import Handoff, AgentCapability
        h = Handoff(target=AgentCapability.PURCHASE, payload={"sid": "abc"})
        assert h.target == AgentCapability.PURCHASE
        assert h.payload["sid"] == "abc"


class TestEnrichResponse:

    def test_adds_missing_fields(self):
        from agents.graph.pipeline import PipelineContext
        from agents.graph.orchestrator import _enrich_response
        ctx = PipelineContext(query="test", session_id="s1", query_type="search")
        ctx._start = 100.0
        import time as _time
        with patch.object(_time, 'time', return_value=100.200):
            result = _enrich_response({"reply": "hi"}, ctx)
        assert result["session_id"] == "s1"
        assert result["query_type"] == "search"
        assert result["runtime"]["total_ms"] == 200

    def test_does_not_overwrite_existing(self):
        from agents.graph.pipeline import PipelineContext
        from agents.graph.orchestrator import _enrich_response
        ctx = PipelineContext(query="test", session_id="s1", query_type="q")
        ctx._start = 100.0
        existing = {"reply": "hi", "session_id": "original", "runtime": {"custom": True}}
        result = _enrich_response(existing, ctx)
        assert result["session_id"] == "original"
        assert result["runtime"] == {"custom": True}


class TestExecutorProtocol:

    def test_valid_passes(self):
        from agents.graph.pipeline import AgentExecutor, AgentCapability
        class G:
            capability = AgentCapability.ORDER
            priority = 10
            def can_handle(self, ctx): return True
            def execute(self, ctx):
                from agents.graph.pipeline import AgentResult
                return AgentResult(status="success")
        assert isinstance(G(), AgentExecutor)

    def test_missing_capability_fails(self):
        from agents.graph.pipeline import AgentExecutor
        class B:
            priority = 10
            def can_handle(self, ctx): return True
            def execute(self, ctx): ...
        assert not isinstance(B(), AgentExecutor)

    def test_missing_can_handle_fails(self):
        from agents.graph.pipeline import AgentExecutor, AgentCapability
        class B:
            capability = AgentCapability.ORDER
            priority = 10
            def execute(self, ctx): ...
        assert not isinstance(B(), AgentExecutor)


class TestOrchestratorImport:

    def test_all_stages_importable(self):
        from agents.graph.orchestrator import run, _run_pipeline, _enrich_response
        from agents.graph.routing import classify
        from agents.graph.execution import run as exec_run, dispatch, resolve
        from agents.graph.response import build
        assert callable(run) and callable(classify) and callable(exec_run) and callable(build)

    def test_registry_has_three_agents(self):
        from agents.graph.execution import _registry
        from agents.graph.pipeline import AgentCapability
        assert len(_registry) == 3
        for key in _registry:
            assert isinstance(key, AgentCapability)
        assert AgentCapability.ORDER in _registry
        assert AgentCapability.CART in _registry
        assert AgentCapability.PURCHASE in _registry
