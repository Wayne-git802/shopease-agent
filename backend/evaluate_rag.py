"""
RAG Evaluation Harness — Product RAG recall@3 + Knowledge RAG source_accuracy.
Usage: python evaluate_rag.py
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
import django; django.setup()

from agents.graph.rag.retriever import get_retriever

# ═══════════════════════════════════════════════════════════════
# Product RAG — 30 queries with expected product IDs
# ═══════════════════════════════════════════════════════════════

# Ground truth: query → expected product IDs (ordered by relevance)
PRODUCT_TESTS = [
    # ── 蓝牙耳机 (IDs 50001-50008) ──
    ("降噪耳机", [50002, 50001, 50007]),         # 华为ANC, 小米ANC, 三星ANC
    ("百元耳机", [50006, 50004, 50003]),          # 倍思¥129, OPPO¥299, 漫步者¥499
    ("骨传导运动耳机", [50005, 50001, 50002]),    # 韶音(骨传导), 小米, 华为
    ("头戴式降噪", [50008, 50001, 50003]),         # 万魔(头戴), 小米, 漫步者(ANC)
    ("长续航蓝牙耳机", [50005, 50008, 50001]),    # 韶音10h, 万魔12h, 小米8h
    ("三星耳机", [50007, 50001, 50002]),          # 三星Buds3 Pro
    ("华为耳机", [50002, 50001, 50005]),          # 华为FreeBuds6i
    ("防水运动耳机", [50001, 50005, 50006]),      # 小米IP55, 韶音IP55, 倍思IPX5

    # ── 智能手机 (IDs 50009-50015) ──
    ("小米手机", [50009, 50013, 50015]),
    ("2000以下手机", [50015, 50013, 50014]),
    ("华为旗舰手机", [50010, 50009, 50011]),
    ("性价比手机", [50015, 50013, 50014]),
    ("快充手机", [50013, 50014, 50015]),
    ("OPPO手机", [50011, 50009, 50010]),

    # ── 智能手表 (IDs 50016-50021) ──
    ("长续航手表", [50017, 50016, 50021]),
    ("户外手表", [50019, 50016, 50017]),
    ("苹果手表", [50018, 50017, 50016]),
    ("性价比手表", [50021, 50017, 50016]),

    # ── 蓝牙音箱 (IDs 50022-50026) ──
    ("便携音箱", [50022, 50023, 50025]),
    ("桌面音箱", [50024, 50026, 50023]),
    ("防水音箱", [50022, 50023, 50025]),
    ("高音质音箱", [50024, 50026, 50023]),

    # ── 笔记本电脑 (IDs 50027-50031) ──
    ("轻薄笔记本", [50028, 50027, 50029]),
    ("苹果笔记本", [50027, 50028, 50029]),
    ("性价比笔记本", [50030, 50031, 50029]),
    ("学生笔记本", [50030, 50031, 50029]),

    # ── 平板电脑 (IDs 50032-50036) ──
    ("iPad", [50032, 50034, 50033]),
    ("华为平板", [50033, 50034, 50035]),
    ("学生平板 护眼", [50035, 50036, 50034]),

    # ── 充电宝 (IDs 50037-50041) ──
    ("大容量充电宝", [50037, 50039, 50040]),
    ("轻薄充电宝", [50038, 50041, 50037]),
    ("快充充电宝", [50039, 50037, 50038]),
]

# ═══════════════════════════════════════════════════════════════
# Knowledge RAG — 20 queries with expected document source
# ═══════════════════════════════════════════════════════════════

KNOWLEDGE_TESTS = [
    ("怎么退货", "return_policy.md"),
    ("退货流程", "return_policy.md"),
    ("退货条件", "return_policy.md"),
    ("运费谁出", "return_policy.md"),
    ("退款多久到账", "return_policy.md"),
    ("配送要多久", "shipping.md"),
    ("运费怎么算", "shipping.md"),
    ("包邮条件", "shipping.md"),
    ("快递到哪了", "shipping.md"),
    ("支付方式有哪些", "payment.md"),
    ("支持分期吗", "payment.md"),
    ("忘了密码怎么办", "FAQ.md"),
    ("怎么改收货地址", "FAQ.md"),
    ("优惠券怎么用", "FAQ.md"),
    ("积分规则", "FAQ.md"),
    ("怎么联系客服", "FAQ.md"),
    ("订单取消了能退款吗", "return_policy.md"),
    ("偏远地区送吗", "shipping.md"),
    ("账户被盗怎么办", "FAQ.md"),
    ("退货要包装吗", "return_policy.md"),
]


def evaluate_product_rag(k=3):
    """Run Product RAG evaluation with recall@k and MRR."""
    retriever = get_retriever()
    total = len(PRODUCT_TESTS)
    hits = 0          # queries with at least 1 match in top-k
    perfect = 0       # all k expected in top-k
    reciprocal_ranks = []
    recall_per_query = []

    print(f"\n{'='*60}")
    print(f"Product RAG Evaluation — recall@{k}")
    print(f"{'='*60}")

    for query, expected_ids in PRODUCT_TESTS:
        expected_set = set(expected_ids[:k])
        products, _ = retriever.search(query, top_k=k)
        retrieved_ids = [p.id for p in products]

        # recall@k: how many expected are in retrieved
        matched = expected_set & set(retrieved_ids)
        recall = len(matched) / len(expected_set)
        recall_per_query.append(recall)

        if matched:
            hits += 1
        if len(matched) == len(expected_set):
            perfect += 1

        # MRR: 1 / rank of first correct result
        rr = 0.0
        for rank, pid in enumerate(retrieved_ids, 1):
            if pid in expected_set:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        status = "✓" if recall > 0 else "✗"
        print(f"  {status} {query:20s} got:{retrieved_ids} want:{expected_ids[:k]} r={recall:.2f}")

    avg_recall = sum(recall_per_query) / total
    mrr = sum(reciprocal_ranks) / total
    hit_rate = hits / total

    print(f"\n{'─'*60}")
    print(f"  queries:     {total}")
    print(f"  recall@{k}:   {avg_recall:.3f}")
    print(f"  MRR:         {mrr:.3f}")
    print(f"  hit_rate:    {hit_rate:.3f} ({hits}/{total})")
    print(f"  perfect:     {perfect}/{total}")
    print(f"{'─'*60}")

    return {"recall": avg_recall, "mrr": mrr, "hit_rate": hit_rate, "perfect": perfect, "total": total}


def evaluate_knowledge_rag(k=3):
    """Run Knowledge RAG evaluation with source accuracy."""
    from agents.rag.knowledge_store import get_knowledge_store

    ks = get_knowledge_store()
    # Index if empty
    if ks.chunk_count == 0:
        print("Indexing knowledge docs...")
        ks.index_documents("docs")

    total = len(KNOWLEDGE_TESTS)
    correct = 0
    mrr = 0.0

    print(f"\n{'='*60}")
    print(f"Knowledge RAG Evaluation — source_accuracy")
    print(f"{'='*60}")

    for query, expected_source in KNOWLEDGE_TESTS:
        results = ks.search(query, top_k=k)
        sources = [r["metadata"]["source"] for r in results]

        # Check if expected source is in top-k
        hit = expected_source in sources
        if hit:
            correct += 1

        # MRR
        rr = 0.0
        for rank, src in enumerate(sources, 1):
            if src == expected_source:
                rr = 1.0 / rank
                break
        mrr += rr

        status = "✓" if hit else "✗"
        sections = [r["metadata"].get("section","") for r in results]
        print(f"  {status} {query:20s} expect:{expected_source} got:{sources} sec:{sections}")

    accuracy = correct / total
    mrr /= total

    print(f"\n{'─'*60}")
    print(f"  queries:        {total}")
    print(f"  source_accuracy: {accuracy:.3f} ({correct}/{total})")
    print(f"  MRR:            {mrr:.3f}")
    print(f"{'─'*60}")

    return {"accuracy": accuracy, "mrr": mrr, "correct": correct, "total": total}


if __name__ == "__main__":
    import time as _t
    t0 = _t.time()

    prod = evaluate_product_rag(k=3)
    know = evaluate_knowledge_rag(k=3)

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Product RAG:     recall@3={prod['recall']:.3f}  MRR={prod['mrr']:.3f}  hit_rate={prod['hit_rate']:.3f}")
    print(f"  Knowledge RAG:   accuracy={know['accuracy']:.3f}  MRR={know['mrr']:.3f}")
    print(f"  Total time:      {_t.time()-t0:.1f}s")
