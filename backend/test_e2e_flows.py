"""
End-to-end flow tests: search, recommend, order, analytics, entry routing.
Run: cd backend && DJANGO_SETTINGS_MODULE=mysite.settings python test_e2e_flows.py
"""
import django, os, sys, io
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from agents.graph.state import AgentState
from agents.graph.nodes.search_node import search_node
from agents.graph.nodes.response_node import response_node
from agents.graph.nodes.order_node import order_node
from agents.graph.nodes.entry_router import entry_router
from agents.graph.nodes.analytics_node import analytics_node

PASS, FAIL = 0, 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  --  {detail}")

def hr(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def plan(**kw):
    """Build a _search_plan dict with defaults."""
    d = {"intent": "search", "strategy": "semantic", "method": "regex", "detail": ""}
    d.update(kw)
    return d


# ═══════════════════════════════════════════════════════════════
hr("1. SEARCH -- 'shouji 3000以下'")
state = AgentState(
    user_query="shouji 3000以下", session_id="e2e_s", intent="search", confidence=0.8,
    parallel_results={"_search_plan": plan(
        category_filter="智能手机", category_confidence=1.0,
        budget_lower=0, budget_upper=3900,
    )},
)
r = search_node(state)
prods = r.tool_results.get("products", [])
check("no error", r.error is None, str(r.error))
check("step recorded", "search" in r.steps_done)
check("has products", len(prods) >= 2, f"got {len(prods)}")
check("all have scores", all("score" in p for p in prods))
if prods:
    check("under budget margin", all(float(p.get("price",0)) <= 5100 for p in prods),
          f"max={max(float(p.get('price',0)) for p in prods)}")
    print(f"       -> {len(prods)} results, top={prods[0].get('product_name','?')} {prods[0].get('price','?')}")

resp = response_node(r)
check("has reply", bool(resp.final_response))
print(f"       -> reply: {resp.final_response[:60]}...")


# ═══════════════════════════════════════════════════════════════
hr("2. SEARCH -- '华为shouji' (brand constraint)")
state2 = AgentState(
    user_query="华为shouji", session_id="e2e_h", intent="search", confidence=0.8,
    parallel_results={"_search_plan": plan(
        category_filter="智能手机", category_confidence=1.0, brand="华为",
    )},
)
r2 = search_node(state2)
p2 = r2.tool_results.get("products", [])
relaxed2 = r2.parallel_results.get("_relaxed_constraints", [])
check("no error", r2.error is None)
check("has products", len(p2) >= 1, f"got {len(p2)}")

# Check top brands
from products.models import Product
top_brands = []
for p in p2[:5]:
    db = Product.objects.filter(id=p["product_id"]).first()
    top_brands.append(db.brand if db else "?")
has_hw = any("华为" in str(b) for b in top_brands[:3])
check("华为 in top 3", has_hw, f"brands={top_brands[:5]}")
print(f"       -> {len(p2)} results, relaxed={relaxed2}, brands={top_brands[:5]}")


# ═══════════════════════════════════════════════════════════════
hr("3. RECOMMEND -- 'tuijian 蓝牙耳机'")
state3 = AgentState(
    user_query="tuijian 蓝牙耳机", session_id="e2e_r", intent="recommend", confidence=0.8,
    parallel_results={"_search_plan": plan(
        intent="recommend", category_filter="耳机", category_confidence=1.0,
    )},
)
r3 = search_node(state3)
p3 = r3.tool_results.get("products", [])
check("no error", r3.error is None)
check(">=2 results", len(p3) >= 2, f"got {len(p3)}")
if p3:
    print(f"       -> {len(p3)} results, top={p3[0].get('product_name','?')} {p3[0].get('price','?')}")

resp3 = response_node(r3)
check("reply exists", bool(resp3.final_response))
print(f"       -> reply: {resp3.final_response[:60]}...")


# ═══════════════════════════════════════════════════════════════
hr("4. RECOMMEND -- gift query, no category filter")
state4 = AgentState(
    user_query="song gei nvpengyou de liwu", session_id="e2e_g", intent="recommend", confidence=0.6,
    parallel_results={"_search_plan": plan(intent="recommend")},
)
r4 = search_node(state4)
p4 = r4.tool_results.get("products", [])
check("no error", r4.error is None)
check("has results without category", len(p4) > 0, f"got {len(p4)}")
if p4:
    cats = set()
    for p in p4[:10]:
        db = Product.objects.filter(id=p["product_id"]).first()
        if db and db.category:
            cats.add(db.category.name)
    check("diverse categories", len(cats) >= 2, f"cats={cats}")
    print(f"       -> {len(p4)} results, {len(cats)} categories: {list(cats)[:5]}")


# ═══════════════════════════════════════════════════════════════
hr("5. ORDER -- status query")
state5 = AgentState(
    user_query="chaxun wode dingdan", session_id="e2e_o", user_id=1, intent="order", confidence=0.9,
    parallel_results={"order_action": "status"},
)
r5 = order_node(state5)
od = r5.tool_results.get("order", {})
check("no error", r5.error is None)
check("step recorded", "order" in r5.steps_done)
check("has status", "status" in od, str(od))
print(f"       -> status={od.get('status')}, data={od.get('data', od.get('error','?'))}")


# ═══════════════════════════════════════════════════════════════
hr("6. ORDER -- cancel (non-existent order)")
state6 = AgentState(
    user_query="quxiao dingdan", session_id="e2e_c", user_id=1, intent="order", confidence=0.9,
    parallel_results={"order_action": "cancel", "order_id": 99999},
)
r6 = order_node(state6)
od6 = r6.tool_results.get("order", {})
check("no crash", r6.error is None)
check("has result", "status" in od6)
print(f"       -> status={od6.get('status')} -- {od6.get('error', od6.get('data','?'))}")


# ═══════════════════════════════════════════════════════════════
hr("7. ANALYTICS -- weekly report")
state7 = AgentState(
    user_query="benzhou xiaoshou baogao", session_id="e2e_a", intent="analytics", confidence=0.8,
    parallel_results={"analytics_days": 7},
)
try:
    r7 = analytics_node(state7)
    ad = r7.tool_results.get("analytics", {})
    check("no error", r7.error is None, str(r7.error))
    check("data present", isinstance(ad, dict))
    print(f"       -> keys: {list(ad.keys())[:5] if ad else 'empty'}")
except Exception as e:
    check("analytics runs", False, str(e))


# ═══════════════════════════════════════════════════════════════
hr("8. CONSTRAINT RELAXATION -- 'suoni erji 10yuan' (impossible)")
state8 = AgentState(
    user_query="suoni erji 10yuan", session_id="e2e_i", intent="search", confidence=0.8,
    parallel_results={"_search_plan": plan(
        category_filter="耳机", category_confidence=1.0,
        brand="索尼", budget_upper=13, budget_lower=0,
    )},
)
r8 = search_node(state8)
p8 = r8.tool_results.get("products", [])
rel8 = r8.parallel_results.get("_relaxed_constraints", [])
nr8 = r8.parallel_results.get("_no_results", False)
check("no error", r8.error is None)
check("relaxation or no_results triggered", len(rel8) > 0 or nr8,
      f"products={len(p8)}, relaxed={rel8}, no_results={nr8}")
print(f"       -> {len(p8)} results, relaxed={rel8}, no_results={nr8}")


# ═══════════════════════════════════════════════════════════════
hr("9. ENTRY ROUTER -- dispatch")
# search intent + search_plan -> search node
s9a = AgentState(user_query="shouji", session_id="e2e_r1", intent="search",
    parallel_results={"_search_plan": plan(intent="search")})
cmd = entry_router(s9a)
check("search dispatch -> search", getattr(cmd, 'goto', '') == "search",
      f"goto={getattr(cmd,'goto','?')}")

# no plan, no session -> default chat
s9b = AgentState(user_query="nihao", session_id="e2e_r2", intent="chat")
cmd2 = entry_router(s9b)
check("no-plan dispatch -> chat", getattr(cmd2, 'goto', '') == "chat")

# recommend + search_plan -> search (merged node)
s9c = AgentState(user_query="tuijian", session_id="e2e_r3", intent="recommend",
    parallel_results={"_search_plan": plan(intent="recommend")})
cmd3 = entry_router(s9c)
check("recommend dispatch -> search", getattr(cmd3, 'goto', '') == "search",
      f"goto={getattr(cmd3,'goto','?')}")

# order intent via preset -> order node
s9d = AgentState(user_query="wode dingdan", session_id="e2e_r4", intent="order",
    control_context={"preset_intent": "order"})
cmd4 = entry_router(s9d)
check("order preset dispatch -> order", getattr(cmd4, 'goto', '') == "order",
      f"goto={getattr(cmd4,'goto','?')}")


# ═══════════════════════════════════════════════════════════════
hr("10. SOFT CATEGORY -- confidence=0.5")
state10 = AgentState(
    user_query="youxi xianshiqi", session_id="e2e_sc", intent="search", confidence=0.8,
    parallel_results={"_search_plan": plan(
        category_filter="显示器", category_confidence=0.5,
    )},
)
r10 = search_node(state10)
p10 = r10.tool_results.get("products", [])
check("no error", r10.error is None)
check("has results with soft category", len(p10) >= 1, f"got {len(p10)}")
print(f"       -> {len(p10)} results")


# ═══════════════════════════════════════════════════════════════
hr("SUMMARY")
print(f"  PASS: {PASS}")
print(f"  FAIL: {FAIL}")
print(f"  Total: {PASS + FAIL}")
if FAIL == 0:
    print("\n  *** All flows working! ***")
else:
    print(f"\n  *** {FAIL} checks failed ***")
