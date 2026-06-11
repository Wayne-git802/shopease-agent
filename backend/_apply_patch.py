"""Temporary script to apply StructuredRouter insertion to orchestrator.py."""
with open('agents/graph/orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = (
    "    # ── 0. WorkflowAffinityRouter — context-aware routing ──\n"
    "    # Two checks (both must pass for routing to occur):\n"
    "    #   1. Active OrderWorkflow (mid-cancel/refund multi-step flow)\n"
    "    #   2. Block-based affinity (order_created → OrderAgent, etc.)\n"
    "    # If neither fires, fall through to L0 state_router → L1 commerce_intent.\n"
    "    if session_id:"
)

new = (
    "    # ── L0: Structured Retrieval — 订单/购物车/历史直接 SQL ──\n"
    "    # Keyword-based detection, no LLM.  Bypasses the search graph entirely\n"
    "    # for structured queries that have a definitive DB answer.\n"
    "    from .structured_router import StructuredRouter as SR, StructuredIntent\n"
    "    sr = SR()\n"
    "    intent = sr.detect(query, user_id)\n"
    "    if intent != StructuredIntent.NONE and user_id:\n"
    "        result = sr.execute(intent, user_id, session_id)\n"
    "        return {\n"
    '            "reply": result.reply,\n'
    '            "intent": "structured",\n'
    '            "confidence": 1.0,\n'
    '            "blocks": [],\n'
    '            "ranked_items": result.data.get("items", []),\n'
    '            "tool_results": {},\n'
    '            "session_id": session_id,\n'
    '            "query_type": query_type,\n'
    '            "ui_state": "done",\n'
    '            "message": f"structured:{intent.value}",\n'
    '            "runtime": {"phases": [{"phase": "routing", "label": "结构化查询", "status": "ok", "ms": int((_time.time() - _start) * 1000)}], "total_ms": int((_time.time() - _start) * 1000)},\n'
    '            "explain": None,\n'
    '            "retrieval": None,\n'
    '            "show_budget_hint": False,\n'
    '            "show_clarify_hint": False,\n'
    "        }\n"
    "\n"
    "    # ── 0. WorkflowAffinityRouter — context-aware routing ──\n"
    "    # Two checks (both must pass for routing to occur):\n"
    "    #   1. Active OrderWorkflow (mid-cancel/refund multi-step flow)\n"
    "    #   2. Block-based affinity (order_created → OrderAgent, etc.)\n"
    "    # If neither fires, fall through to L0 state_router → L1 commerce_intent.\n"
    "    if session_id:"
)

if old in content:
    content = content.replace(old, new, 1)
    with open('agents/graph/orchestrator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK - edit applied successfully')
else:
    print('ERROR - old string not found in file')
    # Debug: show exact lines
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'WorkflowAffinityRouter' in line:
            start = max(0, i - 2)
            end = min(len(lines), i + 8)
            for j in range(start, end):
                print(f'  {j+1}: {repr(lines[j])}')
