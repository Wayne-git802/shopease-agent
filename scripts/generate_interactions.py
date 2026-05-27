#!/usr/bin/env python
"""
Synthetic Interaction Generator — simulate user behavior to populate Phase B data.

Usage:
    python scripts/generate_interactions.py [--profile gaming|casual|budget] [--rounds 30]

Profiles:
    gaming   — clicks gaming headsets, keyboards, mice; buys gaming gear
    casual   — browses watches, shoes, clothes; buys fashion items
    budget   — shops for low-price items; dismisses expensive stuff

This generates:
    • StandardizedSignals (for ranking feedback)
    • SessionTraces (for Diff View / Replay)
    • RoutingTuningLog entries (for routing tuner)
    • UserPreferences (for memory distribution)
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
import django
django.setup()

from agents.models import StandardizedSignal, SessionTrace, RoutingTuningLog, UserPreference

from django.utils import timezone as dj_timezone

# ── Profiles ────────────────────────────────────────────────────

PROFILES = {
    "gaming": {
        "queries": [
            "推荐游戏耳机", "gaming headset", "机械键盘推荐",
            "best gaming mouse", "游戏显示器", "推荐电竞椅",
            "cheap gaming gear", "RGB键盘", "无线游戏鼠标",
        ],
        "target_categories": ["Gaming Headsets", "Keyboards", "Gaming Mouse", "Monitors", "Gaming"],
        "budget": (50, 300),
        "click_rate": 0.6,
        "purchase_rate": 0.15,
        "dismiss_rate": 0.1,
    },
    "casual": {
        "queries": [
            "推荐手表", "fashion shoes", "好看的包包",
            "summer dress", "太阳镜推荐", "perfume for men",
            "casual sneakers", "女士手袋", "jewellery gift",
        ],
        "target_categories": ["Watches", "Casual Shoes", "Bags", "Make-Up", "Jewellery", "Perfumes"],
        "budget": (20, 200),
        "click_rate": 0.7,
        "purchase_rate": 0.12,
        "dismiss_rate": 0.15,
    },
    "budget": {
        "queries": [
            "最便宜的手机壳", "cheap accessories", "under $5 items",
            "折扣商品", "budget home decor", "cheapest kitchen tools",
            "文具推荐", "low price gadgets", "clearance sale",
        ],
        "target_categories": ["Accessories", "Home Decor", "Kitchen", "Stationery"],
        "budget": (1, 20),
        "click_rate": 0.5,
        "purchase_rate": 0.20,
        "dismiss_rate": 0.25,
    },
}

# ── Constants ────────────────────────────────────────────────────

USER_ID = 99   # dedicated synthetic user id
INTENTS = ["search", "recommend", "chat"]
ROUTING_METHODS = ["fast", "slow"]
PHASES_TEMPLATE = [
    {"phase": "understanding", "label": "理解需求", "status": "ok", "ms": 0},
    {"phase": "searching",     "label": "检索商品", "status": "ok", "ms": 0},
    {"phase": "recommending",  "label": "偏好排序", "status": "ok", "ms": 0},
    {"phase": "responding",    "label": "生成推荐", "status": "ok", "ms": 0},
]

# Known product names per category (real products from the dataset)
CATEGORY_PRODUCTS = {
    "Gaming Headsets": [
        {"id": 30001, "name": "HyperX Cloud III Gaming Headset", "price": 89.99},
        {"id": 30002, "name": "SteelSeries Arctis Nova Pro", "price": 249.99},
        {"id": 30003, "name": "Logitech G Pro X Wireless", "price": 129.99},
        {"id": 30004, "name": "Razer BlackShark V2", "price": 69.99},
    ],
    "Watches": [
        {"id": 47096, "name": "SHENGKE Elegant Rose Gold Women Watch", "price": 39.51},
        {"id": 47097, "name": "Fossil Grant Chronograph Watch", "price": 89.00},
        {"id": 47098, "name": "Casio G-Shock Digital Watch", "price": 45.00},
    ],
    "Casual Shoes": [
        {"id": 13867, "name": "ASICS Mens Gel-Nandi Sneaker", "price": 107.77},
        {"id": 13868, "name": "Nike Air Max 270", "price": 150.00},
    ],
    "Keyboards": [
        {"id": 40001, "name": "Razer Huntsman Mini", "price": 119.99},
        {"id": 40002, "name": "Keychron K2 Wireless", "price": 79.99},
    ],
}


def random_product(category: str) -> dict:
    """Get a random product from a category, or generate a plausible one."""
    prods = CATEGORY_PRODUCTS.get(category, [])
    if prods:
        return random.choice(prods)
    return {
        "id": random.randint(10000, 50000),
        "name": f"{category} Product #{random.randint(1, 999)}",
        "price": round(random.uniform(5, 200), 2),
    }


def generate_phases(total_ms: int) -> list[dict]:
    """Generate plausible phase timings that sum to total_ms."""
    weights = [0.25, 0.20, 0.25, 0.30]  # understanding, searching, recommending, responding
    phases = []
    remaining = total_ms
    for i, p in enumerate(PHASES_TEMPLATE):
        if i == len(PHASES_TEMPLATE) - 1:
            ms = remaining
        else:
            ms = int(total_ms * weights[i]) + random.randint(-20, 20)
            ms = max(10, min(remaining - 10, ms))
        remaining -= ms
        phases.append({**p, "ms": max(ms, 5)})
    return phases


def run(profile: str, rounds: int, clear: bool = True):
    """Run the synthetic interaction generator."""
    cfg = PROFILES[profile]

    if clear:
        print(f"Clearing existing data for user {USER_ID}...")
        StandardizedSignal.objects.filter(user_id=USER_ID).delete()
        SessionTrace.objects.filter(user_id=USER_ID).delete()
        RoutingTuningLog.objects.filter(session_id__startswith=f"syn_{USER_ID}_").delete()
        UserPreference.objects.filter(user_id=USER_ID).delete()

    now = dj_timezone.now()

    for i in range(rounds):
        sid = f"syn_{USER_ID}_{i:04d}"
        t = now - timedelta(minutes=rounds - i)

        # ── Query ──
        query = random.choice(cfg["queries"])
        intent = "recommend" if random.random() < 0.7 else random.choice(INTENTS)
        routing_method = "fast" if random.random() < 0.8 else "slow"
        total_ms = int(random.gauss(1500, 400))
        total_ms = max(300, min(5000, total_ms))
        block_count = random.randint(3, 12)

        # ── Products ──
        n_products = random.randint(3, 10)
        ranked = []
        signals = {}
        for j in range(n_products):
            cat = random.choice(cfg["target_categories"])
            prod = random_product(cat)
            ranked.append({
                "id": prod["id"],
                "name": prod["name"],
                "price": prod["price"],
                "category": cat,
            })

            # Accumulate signals for this category
            if cat not in signals:
                signals[cat] = 0.0
            signals[cat] += 0.02  # slight boost per view
        signals = {k: round(v, 3) for k, v in signals.items()}

        # ── Create SessionTrace ──
        SessionTrace.objects.create(
            session_id=sid,
            user_id=USER_ID,
            query=query,
            intent=intent,
            routing_conf=random.uniform(0.6, 0.95),
            ui_state="done",
            reply=f"为您找到 {len(ranked)} 款商品" if ranked else "请问有什么可以帮您的？",
            phases=generate_phases(total_ms),
            ranked_before=[],
            ranked_after=ranked[:5],
            signals_applied=signals,
            block_count=block_count,
            total_ms=total_ms,
        )
        # Note: created_at uses auto_now_add, time ordering is near enough for synthetic data

        # ── Create StandardizedSignals ──
        for prod in ranked[:3]:
            # Click
            if random.random() < cfg["click_rate"]:
                StandardizedSignal.objects.create(
                    session_id=sid, user_id=USER_ID,
                    signal_type="exploration", product_id=prod["id"],
                    category=prod["category"], value=0.0,
                )

            # Purchase
            if random.random() < cfg["purchase_rate"]:
                StandardizedSignal.objects.create(
                    session_id=sid, user_id=USER_ID,
                    signal_type="conversion", product_id=prod["id"],
                    category=prod["category"], value=0.10,
                )

        # Dismiss random products
        for _ in range(random.randint(0, 2)):
            if random.random() < cfg["dismiss_rate"]:
                StandardizedSignal.objects.create(
                    session_id=sid, user_id=USER_ID,
                    signal_type="negative",
                    product_id=random.randint(10000, 50000),
                    category=random.choice(cfg["target_categories"]),
                    value=-0.02,
                )

        # ── Create RoutingTuningLog ──
        RoutingTuningLog.objects.create(
            session_id=sid,
            intent=intent,
            fast_confidence=random.uniform(0.5, 0.95),
            routing_method=routing_method,
            threshold_used=0.85,
            outcome=random.choice(["clicked", "purchased", "dismissed", "clicked"]),
            reward_score=random.uniform(-0.1, 0.6),
        )

        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{rounds} sessions generated...")

    # ── Create UserPreferences from accumulated signals ──
    # Skip if user 99 doesn't exist in auth table (FK constraint)
    try:
        top_cats = {}
        for cat in cfg["target_categories"]:
            count = StandardizedSignal.objects.filter(
                user_id=USER_ID, category=cat, signal_type="conversion"
            ).count()
            if count > 0:
                top_cats[cat] = min(count * 0.1, 0.9)

        for cat, weight in sorted(top_cats.items(), key=lambda x: x[1], reverse=True)[:3]:
            UserPreference.objects.update_or_create(
                user_id=USER_ID, key=f"pref_{cat.lower().replace(' ', '_')}",
                defaults={
                    "value": json.dumps({cat: weight}, ensure_ascii=False),
                    "source_agent": "synthetic",
                    "confidence": weight,
                },
            )
    except Exception:
        pass  # user 99 may not exist — non-critical

    # ── Summary ──
    print(f"\n✅ Generated {rounds} sessions for profile '{profile}' (user {USER_ID}):")
    print(f"   SessionTraces:       {SessionTrace.objects.filter(user_id=USER_ID).count()}")
    print(f"   StandardizedSignals: {StandardizedSignal.objects.filter(user_id=USER_ID).count()}")
    print(f"   RoutingTuningLog:    {RoutingTuningLog.objects.filter(session_id__startswith=f'syn_{USER_ID}_').count()}")
    print(f"   UserPreferences:     {UserPreference.objects.filter(user_id=USER_ID).count()}")
    print(f"\n   Now visit:")
    print(f"   - /ai/workspace/   (try a search or recommend)")
    print(f"   - /ai/diff/        (see before/after comparison)")
    print(f"   - /ai/replay/      (browse session replays)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic interactions")
    parser.add_argument("--profile", default="gaming", choices=["gaming", "casual", "budget", "all"])
    parser.add_argument("--rounds", type=int, default=30)
    parser.add_argument("--no-clear", action="store_true", help="Don't clear existing data")
    args = parser.parse_args()

    if args.profile == "all":
        for p in PROFILES:
            run(p, args.rounds, clear=not args.no_clear)
    else:
        run(args.profile, args.rounds, clear=not args.no_clear)
