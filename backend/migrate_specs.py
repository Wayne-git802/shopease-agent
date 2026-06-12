"""Migrate existing product specs to Phase B schema.

Converts:
  pros/cons: comma-string → list
  review_sentiment: "positive"/"neutral"/"negative" → 0.85/0.50/0.15
  review_count: ensure int
  review_text: generate 3 Chinese review sentences if missing
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
django.setup()

from products.models import Product

SENTIMENT_MAP = {'positive': 0.85, 'neutral': 0.50, 'negative': 0.15}


def normalize_specs(specs):
    if not specs:
        return specs, False
    specs = dict(specs)  # copy
    changed = False

    for key in ('pros', 'cons'):
        val = specs.get(key, '')
        if isinstance(val, str):
            specs[key] = [s.strip() for s in val.split(',') if s.strip()]
            changed = True

    sentiment = specs.get('review_sentiment', 'positive')
    if isinstance(sentiment, str):
        specs['review_sentiment'] = SENTIMENT_MAP.get(sentiment.lower(), 0.50)
        changed = True

    if 'review_count' in specs:
        specs['review_count'] = int(specs['review_count'])

    if 'review_text' not in specs:
        pros_list = specs.get('pros', [])
        cons_list = specs.get('cons', [])
        reviews = []
        if pros_list:
            reviews.append(f"{pros_list[0]}，真的很不错")
        else:
            reviews.append("产品质量很好，值得购买")
        if len(pros_list) > 1:
            reviews.append(f"{pros_list[1]}，体验很好")
        elif cons_list:
            reviews.append(f"除了{cons_list[0]}，其他都挺满意")
        else:
            reviews.append("使用体验不错，推荐购买")
        if cons_list:
            reviews.append(f"{cons_list[0]}，希望能改进")
        else:
            reviews.append("整体满意，会回购")
        specs['review_text'] = reviews
        changed = True

    return specs, changed


print("Fetching products with old-format specs...")

# Only update products where pros is still a string (not yet converted)
products = Product.objects.all()
total = products.count()
updated = 0
batch = []
batch_size = 200

for i, p in enumerate(products.iterator(chunk_size=500)):
    new_specs, changed = normalize_specs(p.specs)
    if changed:
        p.specs = new_specs
        batch.append(p)
    
    if len(batch) >= batch_size:
        Product.objects.bulk_update(batch, ['specs'])
        updated += len(batch)
        batch = []
        print(f"  [{updated}/{total}] updated...")

if batch:
    Product.objects.bulk_update(batch, ['specs'])
    updated += len(batch)

print(f"\nDone: {updated} products updated (of {total} total).")

# Verify
sample = Product.objects.first()
if sample:
    specs = sample.specs or {}
    print(f"\nVerification — first product: {sample.name}")
    print(f"  pros: {specs.get('pros')} (type={type(specs.get('pros')).__name__})")
    print(f"  cons: {specs.get('cons')} (type={type(specs.get('cons')).__name__})")
    print(f"  review_sentiment: {specs.get('review_sentiment')} (type={type(specs.get('review_sentiment')).__name__})")
    print(f"  review_count: {specs.get('review_count')} (type={type(specs.get('review_count')).__name__})")
    print(f"  review_text: {specs.get('review_text')}")
