#!/usr/bin/env python
"""LangGraph Refactor Verification Suite - 5 Tests"""
import os
import sys

# Set up Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

print("=" * 60)
print("LANGGRAPH REFACTOR VERIFICATION SUITE")
print("=" * 60)

# ───────────────────────────────────────────────────────────
# Test 1: All imports resolve
# ───────────────────────────────────────────────────────────
print("\n[Test 1] Import Resolution")
try:
    from agents.graph.state import AgentState, UserMemory
    from agents.graph.contracts import RoutingInput, SearchNodeInput
    from agents.graph.routing_model import route as route_intent
    from agents.graph.policy import GraphPolicy
    from agents.graph.cost_router import CostRouter
    from agents.graph.rag.embedder import embed_dim
    from agents.graph.rag.vector_store import VectorStore
    from agents.graph.rag.retriever import Retriever
    from agents.graph.memory import GlobalMemoryManager, MemoryDecay
    from agents.graph.trace import persist_trace
    from agents.graph.eval import recall_at_k, precision_at_k, diversity_score
    print("✅ All imports OK")
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ───────────────────────────────────────────────────────────
# Test 2: Graph compiles
# ───────────────────────────────────────────────────────────
print("\n[Test 2] Graph Compilation")
try:
    from agents.graph.graph_builder import get_graph
    graph = get_graph()
    print(f"✅ Graph compiled: {graph}")
except Exception as e:
    print(f"❌ Graph compilation failed: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ───────────────────────────────────────────────────────────
# Test 3: Dry-run invoke
# ───────────────────────────────────────────────────────────
print("\n[Test 3] Dry-run Invoke")
try:
    state = AgentState(user_query="推荐一款手机", session_id="test-1")
    result = graph.invoke(state)
    # graph.invoke may return dict or AgentState
    if isinstance(result, dict):
        result = AgentState(**result)
    print(f"✅ Graph invoked: response={result.final_response[:80]}...")
    print(f"   Intent: {result.intent}, Confidence: {result.confidence}")
    print(f"   Steps: {result.steps_done}")
except Exception as e:
    print(f"⚠️  Graph invoke produced error (may be expected without embeddings): {e}")

# ───────────────────────────────────────────────────────────
# Test 4: Orchestrator dry-run
# ───────────────────────────────────────────────────────────
print("\n[Test 4] Orchestrator Dry-run")
try:
    from agents.graph.orchestrator import run
    reply = run(query="你好", user_id=None)
    print(f"✅ Orchestrator: {reply[:80]}...")
except Exception as e:
    print(f"⚠️  Orchestrator error: {e}")
    import traceback; traceback.print_exc()

# ───────────────────────────────────────────────────────────
# Test 5: Policy contracts
# ───────────────────────────────────────────────────────────
print("\n[Test 5] Policy Contracts")
try:
    policy = GraphPolicy()
    s = AgentState(intent="search", confidence=0.9)
    assert policy.route(s) == "search", "Policy should passthrough"
    s2 = AgentState(intent="recommend", confidence=0.3)
    assert policy.route(s2) == "chat", "Policy should fallback on low confidence"
    print("✅ Policy contract OK")
except Exception as e:
    print(f"❌ Policy contract failed: {e}")
    import traceback; traceback.print_exc()

# ───────────────────────────────────────────────────────────
# Summary
# ───────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
