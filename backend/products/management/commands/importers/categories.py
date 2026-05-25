"""
Category importer — CSV Category.csv with 2-level hierarchy simulation.

Strategy:
- Read Category.csv (131 flat categories)
- Map names to a curated 2-level hierarchy (4 parent + 1 "其他" parent)
- Parent categories get legacy_id=legacy_id (from CSV)
- Child categories get legacy_id from CSV, parent FK set to their logical parent
"""

from products.models import Category
from .runtime import ImporterRuntime, ErrorKind, read_csv, BATCH_SIZE


# ── 2-level hierarchy map ─────────────────────────────────────────
# Maps CSV category_name substring → (parent_name, parent_slug)
CATEGORY_HIERARCHY = [
    # Electronics
    ("电子产品", "electronics", [
        "Phone", "Mobile", "Smartphone", "Tablet", "Laptop", "Computer", "PC",
        "Camera", "Headphone", "Speaker", "Audio", "TV", "Television",
        "Electronic", "Gaming", "Console",
    ]),
    # Clothing & Fashion
    ("服装鞋帽", "clothing-fashion", [
        "Clothing", "Fashion", "Men", "Women", "Kid", "Baby", "Shoe",
        "Shirt", "Jeans", "T-Shirt", "Western", "Ethnic", "Innerwear",
        "Lingerie", "Sportswear", "Dress", "Watch", "Jewellery", "Jewelry",
        "Sunglass", "Ballerina", "Sandal", "Bag", "Handbag", "Luggage",
        "Suitcase", "Rucksack", "Backpack", "Wallet", "Accessories",
    ]),
    # Home & Kitchen
    ("家居厨房", "home-kitchen", [
        "Home", "Kitchen", "Furniture", "Décor", "Decor", "Garden",
        "Furnishing", "Storage", "Bedroom", "Lighting", "Appliance",
        "Refrigerator", "Washing", "Air Conditioner", "Heating", "Cooling",
        "Home Improvement", "Household", "Sewing", "Craft",
    ]),
    # Health & Beauty
    ("健康美妆", "health-beauty", [
        "Health", "Beauty", "Grooming", "Make-Up", "Makeup", "Personal Care",
        "Diet", "Nutrition", "Baby", "Nursing", "Feeding", "Diaper",
        "Luxury Beauty",
    ]),
    # Sports & Outdoors
    ("运动户外", "sports-outdoors", [
        "Sport", "Fitness", "Exercise", "Yoga", "Running", "Cycling",
        "Football", "Cricket", "Badminton", "Camping", "Hiking",
        "Car", "Motorbike", "Bike", "Cardio", "Strength",
    ]),
    # Grocery & Food
    ("食品杂货", "grocery-food", [
        "Grocery", "Gourmet", "Food", "Snack", "Coffee", "Pet Supplie",
    ]),
    # Books & Toys
    ("图书玩具", "books-toys", [
        "Toy", "Book", "Music", "Instrument", "Game",
    ]),
    # Industrial
    ("工业用品", "industrial", [
        "Industrial", "Scientific", "Lab", "Janitorial", "Sanitation",
        "Security Camera",
    ]),
]


def _find_parent(name: str) -> tuple:
    """Return (parent_name, parent_slug) or (None, None)."""
    name_lower = name.lower()
    for parent_name, parent_slug, keywords in CATEGORY_HIERARCHY:
        for kw in keywords:
            if kw.lower() in name_lower:
                return parent_name, parent_slug
    return None, None


def import_categories(runtime: ImporterRuntime):
    runtime.log("Starting category import...")

    rows = read_csv('Category.csv')
    existing = set(Category.objects.values_list('legacy_id', flat=True))

    # Phase 1: build parent categories
    parent_slugs = {}
    parent_objs = []
    parent_legacy_ids = {}
    next_legacy = 90000  # synthetic IDs for parent categories

    seen_parents = set()
    for parent_name, parent_slug, _ in CATEGORY_HIERARCHY:
        if parent_slug in seen_parents:
            continue
        seen_parents.add(parent_slug)
        parent_slugs[parent_name] = parent_slug
        parent_objs.append(Category(
            name=parent_name,
            slug=parent_slug,
            legacy_id=next_legacy,
            is_active=True,
            parent=None,
        ))
        parent_legacy_ids[parent_name] = next_legacy
        next_legacy += 1

    # "其他" catch-all parent
    parent_objs.append(Category(
        name="其他",
        slug="other",
        legacy_id=next_legacy,
        is_active=True,
        parent=None,
    ))
    parent_legacy_ids["其他"] = next_legacy

    runtime.bulk_create(parent_objs)
    # Reload parent IDs
    parent_id_map = {}
    for p in Category.objects.filter(legacy_id__gte=90000):
        parent_id_map[p.name] = p.id
    runtime.log(f"Created {len(parent_id_map)} parent categories")

    # Phase 2: build child categories with numeric legacy_id from CSV id like 'CAT0001'
    child_objs = []
    for i, row in enumerate(rows):
        row_num = i + 2
        cat_id = row['category_id']  # e.g. 'CAT0001'
        legacy_id = int(cat_id.replace('CAT', '').lstrip('0') or '0')  # → 1
        if legacy_id in existing:
            runtime.stats.skipped += 1
            continue

        name = row['category_name'][:100]
        parent_name, parent_slug = _find_parent(name)
        parent_id = parent_id_map.get(parent_name) if parent_name else parent_id_map.get("其他")

        child_objs.append(Category(
            name=name,
            slug=f"{parent_slug or 'other'}-{legacy_id}",
            legacy_id=legacy_id,
            is_active=True,
            parent_id=parent_id or parent_id_map["其他"],
        ))

    runtime.bulk_create(child_objs)

    # Phase 3: also handle Parent_of.csv if it exists (override our simulation)
    from .runtime import csv_exists as _csv_exists
    if _csv_exists('Parent_of.csv'):
        runtime.log("Parent_of.csv found — applying explicit parent links...")
        parent_of_rows = read_csv('Parent_of.csv')
        updates = []
        for row in parent_of_rows:
            try:
                child_cat_id = int(row['child_category_id'].replace('CAT', '').lstrip('0') or '0')
                parent_cat_id = int(row['father_category_id'].replace('CAT', '').lstrip('0') or '0')
                child = Category.objects.get(legacy_id=child_cat_id)
                parent = Category.objects.get(legacy_id=parent_cat_id)
                child.parent_id = parent.id
                updates.append(child)
            except Category.DoesNotExist:
                pass
        if updates:
            Category.objects.bulk_update(updates, ['parent_id'], batch_size=BATCH_SIZE)
            runtime.log(f"Applied {len(updates)} Parent_of links")

    runtime.finish()
    return parent_id_map
