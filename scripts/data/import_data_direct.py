"""Direct import from data_new/ CSVs into MySQL. Reliable, fast, bypasses bulk_create issues."""
import csv, hashlib, os, base64, sys, re
from collections import defaultdict
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
import django; django.setup()
from django.db import connection

.
BATCH = 1000

def read_csv(fn):
    path = os.path.join(DATA, fn)
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def csv_exists(fn):
    return os.path.exists(os.path.join(DATA, fn))

def fast_hash(raw):
    algo, iters = 'pbkdf2_sha256', 1000
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac('sha256', raw.encode(), salt.encode(), iters, dklen=32)
    return f'{algo}${iters}${salt}${base64.b64encode(dk).decode().strip()}'

def slugify(v):
    s = re.sub(r'[^a-z0-9]+', '-', v.lower()).strip('-')
    return s or 'category'

def bulk_insert(table, columns, rows, batch=BATCH):
    """Insert rows using raw SQL INSERT INTO ... VALUES ..."""
    if not rows:
        return
    cols = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    sql = f'INSERT INTO {table} ({cols}) VALUES ({placeholders})'
    with connection.cursor() as cur:
        for i in range(0, len(rows), batch):
            cur.executemany(sql, rows[i:i+batch])

print("=== Phase 1: Users ===")

# Preserved: admin(id=1), wayne(id=19002) — already in DB
# Import all from CSVs
users = []  # (username, display_name, password, phone, address, is_staff, is_active, email, date_joined)
user_map = {}  # external_id -> username (lowercase)

# Customer phones & addresses
cust_phones = defaultdict(list)
if csv_exists('Customer_phone.csv'):
    for r in read_csv('Customer_phone.csv'):
        cust_phones[r['customer_id']].append(r.get('phone', ''))

cust_addresses = defaultdict(list)
if csv_exists('Customer_address.csv'):
    for r in read_csv('Customer_address.csv'):
        parts = [r.get('province',''), r.get('city',''), r.get('district',''), r.get('street_name',''), r.get('home_number','')]
        addr = ', '.join(p for p in parts if p)
        cust_addresses[r['customer_id']].append(addr)

# Columns: username, display_name, password, phone, address, is_staff, is_active, email, first_name, last_name, is_superuser, date_joined
UCOLS = ['username', 'display_name', 'password', 'phone', 'address', 'is_staff', 'is_active', 'email', 'first_name', 'last_name', 'is_superuser', 'date_joined']

for r in read_csv('Customer.csv'):
    uname = r['customer_id'].lower()
    phone = (cust_phones.get(r['customer_id'], [None])[0] or '')[:11]
    addr = (cust_addresses.get(r['customer_id'], [None])[0] or '')[:255]
    users.append((uname, r['customer_name'][:50], fast_hash(r['password']), phone, addr, 0, 1, '', '', '', 0, r.get('create_time', '')))
    user_map[r['customer_id']] = uname

# Seller phones
sell_phones = defaultdict(list)
if csv_exists('Seller_phone.csv'):
    for r in read_csv('Seller_phone.csv'):
        sell_phones[r['seller_id']].append(r.get('phone', ''))

for r in read_csv('Seller.csv'):
    uname = r['seller_id'].lower()
    phone = (sell_phones.get(r['seller_id'], [None])[0] or '')[:11]
    is_active = 1 if r.get('status','active') not in {'disabled','closed','suspended'} else 0
    users.append((uname, r['seller_name'][:50], fast_hash(r['password']), phone, '', 0, is_active, '', '', '', 0, r.get('create_time', '')))
    user_map[r['seller_id']] = uname

# Admin phones
admin_phones = defaultdict(list)
if csv_exists('Admin_phone.csv'):
    for r in read_csv('Admin_phone.csv'):
        admin_phones[r['admin_id']].append(r.get('phone', ''))

for r in read_csv('Admin.csv'):
    uname = r['admin_id'].lower()
    phone = (admin_phones.get(r['admin_id'], [None])[0] or '')[:11]
    users.append((uname, r['admin_name'][:50], fast_hash(r['password']), phone, '', 1, 1, '', '', '', 0, r.get('create_time', '')))
    user_map[r['admin_id']] = uname

print(f"  Prepared {len(users)} users, {len(user_map)} mappings")

# Check for duplicates
names = [u[0] for u in users]
assert len(names) == len(set(names)), f"DUPLICATE: {len(names)} vs {len(set(names))}"

bulk_insert('users', UCOLS, users)

# Get actual user IDs from DB
with connection.cursor() as cur:
    cur.execute("SELECT username, id FROM users")
    username_to_id = dict(cur.fetchall())

user_id_map = {ext_id: username_to_id[uname] for ext_id, uname in user_map.items() if uname in username_to_id}
print(f"  Inserted: {len(username_to_id)} users (includes preserved admin+wayne)")

print("=== Phase 2: Categories ===")

cat_rows = read_csv('Category.csv')
cats = []  # (name, slug, is_active, created_at)
slug_by_ext = {}
for r in cat_rows:
    slug = f"{slugify(r['category_name'])}-{r['category_id'].lower()}"
    slug_by_ext[r['category_id']] = slug
    cats.append((r['category_name'][:100], slug, 1, r.get('last_update', '')))

bulk_insert('categories', ['name', 'slug', 'is_active', 'created_at'], cats)

with connection.cursor() as cur:
    cur.execute("SELECT slug, id FROM categories")
    slug_to_cat_id = dict(cur.fetchall())

cat_map = {ext_id: slug_to_cat_id[slug] for ext_id, slug in slug_by_ext.items() if slug in slug_to_cat_id}
print(f"  Categories: {len(cat_map)}")

# Parent_of
parent_updates = []
for r in read_csv('Parent_of.csv'):
    child = cat_map.get(r['child_category_id'])
    parent = cat_map.get(r['father_category_id'])
    if child and parent:
        parent_updates.append((parent, child))

with connection.cursor() as cur:
    cur.executemany("UPDATE categories SET parent_id = %s WHERE id = %s", parent_updates)
print(f"  Parent links: {len(parent_updates)}")

print("=== Phase 3: Shops ===")

status_map = {'active': 'approved', 'approved': 'approved', 'pending': 'pending',
              'rejected': 'rejected', 'suspended': 'disabled', 'closed': 'disabled', 'disabled': 'disabled'}
shops = []
store_name_by_ext = {}
store_seller_map = {}
for r in read_csv('OnlineStore.csv'):
    uid = user_id_map.get(r['seller_id'])
    if not uid:
        continue
    sname = r['store_name'][:100]
    store_name_by_ext[r['store_id']] = sname
    store_seller_map[r['store_id']] = uid
    shops.append((uid, sname, status_map.get(r.get('status','active'), 'approved'), 5.00, r.get('last_update', '')))

bulk_insert('shops', ['user_id', 'shop_name', 'status', 'rating', 'created_at'], shops)

with connection.cursor() as cur:
    cur.execute("SELECT shop_id, shop_name FROM shops")
    name_to_shop_id = {name: sid for sid, name in cur.fetchall()}

shop_map = {ext_id: name_to_shop_id[name] for ext_id, name in store_name_by_ext.items() if name in name_to_shop_id}
print(f"  Shops: {len(shop_map)}")

print("=== Phase 4: Products ===")

# Belongs_to (product -> category)
leaf_by_product = {}
children_of = {r['child_category_id'] for r in read_csv('Parent_of.csv')}
prod_cats = defaultdict(list)
for r in read_csv('Belongs_to.csv'):
    prod_cats[r['product_id']].append(r['category_id'])
for pid, cids in prod_cats.items():
    leaf = next((cid for cid in cids if cid in children_of), None)
    leaf_by_product[pid] = leaf or cids[0]

prods = []
prod_name_by_ext = {}
prod_skipped = 0
for r in read_csv('Product.csv'):
    sid = shop_map.get(r['store_id'])
    seller_id = store_seller_map.get(r['store_id'])
    if not sid or not seller_id:
        prod_skipped += 1
        continue
    cid = cat_map.get(leaf_by_product.get(r['product_id']))
    is_active = 1 if r.get('status','active') in {'active','approved','pending'} else 0
    pname = r['product_name'][:200]
    ts = r.get('last_update', '')
    prods.append((pname, '', Decimal(r.get('unit_price') or 0), '', cid, seller_id, sid, is_active, ts, ts))
    prod_name_by_ext[r['product_id']] = pname

bulk_insert('products', ['name', 'description', 'price', 'image', 'category_id', 'seller_id', 'shop_id', 'is_active', 'created_at', 'updated_at'], prods)

with connection.cursor() as cur:
    cur.execute("SELECT id, name FROM products")
    name_to_prod_id = {name: pid for pid, name in cur.fetchall()}

prod_map = {ext_id: name_to_prod_id[name] for ext_id, name in prod_name_by_ext.items() if name in name_to_prod_id}
print(f"  Products: {len(prod_map)} ({prod_skipped} skipped)")

print("=== Phase 5: Inventory ===")

invs = []
inv_prod_by_ext = {}
for r in read_csv('Inventory.csv'):
    pid = prod_map.get(r['product_id'])
    if not pid:
        continue
    qty = max(0, int(Decimal(str(r.get('quantity') or 0))))
    ts = r.get('last_update', '')
    invs.append((pid, qty, ts))
    inv_prod_by_ext[r['inventory_id']] = pid

bulk_insert('inventory', ['product_id', 'quantity', 'updated_at'], invs)

with connection.cursor() as cur:
    cur.execute("SELECT inventory_id, product_id FROM inventory")
    prod_to_inv_id = {pid: iid for iid, pid in cur.fetchall()}

inv_map = {ext_id: prod_to_inv_id[pid] for ext_id, pid in inv_prod_by_ext.items() if pid in prod_to_inv_id}
print(f"  Inventory: {len(inv_map)}")

print("=== Phase 6: Inventory Transactions ===")

change_types = {'restock': 'RESTOCK', 'order_deduct': 'ORDER_DEDUCT', 'adjustment': 'ADJUSTMENT',
                'return_restock': 'RETURN_RESTOCK', 'refund_requested': 'REFUND_REQUESTED', 'refund_approved': 'REFUND_APPROVED'}
txns = []
txn_skipped = 0
for r in read_csv('InventoryTransaction.csv'):
    iid = inv_map.get(r['inventory_id'])
    if not iid:
        txn_skipped += 1
        continue
    ct = change_types.get(r.get('change_type',''), r.get('change_type','ADJUSTMENT').upper())
    qc = int(Decimal(str(r.get('quantity_change') or 0)))
    txns.append((iid, ct, qc, r.get('action_time', '')))

bulk_insert('inventory_transactions', ['inventory_id', 'change_type', 'quantity_change', 'created_at'], txns)
print(f"  Transactions: {len(txns)} ({txn_skipped} skipped)")

print("=== Phase 7: Orders ===")

# Group PurchaseRecords by purchase_id
purchase_groups = defaultdict(list)
for r in read_csv('PurchaseRecord.csv'):
    purchase_groups[r['purchase_id']].append(r)

orders_data = []
order_items = []
order_ext_map = {}
order_user_map = {}
order_skipped = 0

for purchase_id, group in purchase_groups.items():
    first = group[0]
    uid = user_id_map.get(first['customer_id'])
    if not uid:
        order_skipped += len(group)
        continue
    total = sum(Decimal(str(r.get('total_price') or 0)) for r in group)
    addr = ', '.join(filter(None, [first.get('province',''), first.get('city',''), first.get('district',''), first.get('street_name',''), first.get('home_number','')]))[:255]
    rname = (first.get('recipient_name') or '')[:100]
    rphone = (first.get('recipient_phone') or '')[:11]
    remark = first.get('remark', '')
    ptime = first.get('purchase_time', '')

    import uuid, time as _time
    order_no = f'{_time.strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:8].upper()}'

    orders_data.append((order_no, uid, total, 'paid', addr, rname, rphone, remark, 0, ptime, ptime))
    order_ext_map[purchase_id] = order_no
    order_user_map[purchase_id] = uid

    for r in group:
        pid = prod_map.get(r['product_id'])
        if not pid:
            continue
        qty = max(1, int(Decimal(str(r.get('quantity') or 1))))
        price = Decimal(str(r.get('total_price') or 0)) / Decimal(qty)
        order_items.append((order_no, pid, price, qty))

# Insert orders
bulk_insert('orders', ['order_no', 'user_id', 'total_amount', 'status', 'address', 'receiver_name', 'receiver_phone', 'remark', 'buyer_deleted', 'created_at', 'updated_at'], orders_data)

with connection.cursor() as cur:
    cur.execute("SELECT id, order_no FROM orders")
    order_no_to_id = {ono: oid for oid, ono in cur.fetchall()}

order_map = {ext_id: order_no_to_id[ono] for ext_id, ono in order_ext_map.items() if ono in order_no_to_id}

# Insert order_items with resolved order_id
oi_rows = []
for ono, pid, price, qty in order_items:
    oid = order_no_to_id.get(ono)
    if oid:
        oi_rows.append((oid, pid, price, qty))

bulk_insert('order_items', ['order_id', 'product_id', 'price', 'quantity'], oi_rows)

# Get first order_item per order for reviews/refunds
with connection.cursor() as cur:
    cur.execute("SELECT MIN(id), order_id FROM order_items GROUP BY order_id")
    first_oi = {oid: oiid for oiid, oid in cur.fetchall()}

# Get order user mapping
with connection.cursor() as cur:
    cur.execute("SELECT id, user_id FROM orders")
    db_order_user = dict(cur.fetchall())

print(f"  Orders: {len(order_map)}, Items: {len(oi_rows)} ({order_skipped} skipped)")

print("=== Phase 8: Carts ===")

cart_owner = {r['cart_id']: r['customer_id'] for r in read_csv('Cart.csv')}
carts = []
cart_seen = set()
cart_skipped = 0
for r in read_csv('CartItem.csv'):
    uid = user_id_map.get(cart_owner.get(r['cart_id']))
    pid = prod_map.get(r['product_id'])
    if not uid or not pid or (uid, pid) in cart_seen:
        cart_skipped += 1
        continue
    cart_seen.add((uid, pid))
    qty = max(1, int(Decimal(str(r.get('quantity') or 1))))
    ts = r.get('last_update', '')
    carts.append((uid, pid, qty, ts, ts))

bulk_insert('carts', ['user_id', 'product_id', 'quantity', 'created_at', 'updated_at'], carts)
print(f"  Cart items: {len(carts)} ({cart_skipped} skipped)")

print("=== Phase 9: Reviews ===")

rev_status = {'visible': 'visible', 'pending': 'hidden', 'rejected': 'deleted',
              'removed': 'deleted', 'deleted': 'deleted', 'hidden': 'hidden', 'reported': 'reported'}
reviews = []
rev_ext_ids = []
rev_skipped = 0
# Build oi→product mapping for review product_id
with connection.cursor() as cur:
    cur.execute("SELECT id, product_id FROM order_items")
    oi_to_product = dict(cur.fetchall())

for r in read_csv('Review.csv'):
    oid = order_map.get(r['purchase_id'])
    oiid = first_oi.get(oid)
    uid = db_order_user.get(oid) or order_user_map.get(r['purchase_id'])
    pid = oi_to_product.get(oiid)
    if not oid or not oiid or not uid or not pid:
        rev_skipped += 1
        continue
    rating = max(1, min(5, round(float(r.get('rating') or 5))))
    ts = r.get('last_update', '')
    reviews.append((pid, oiid, uid, rating, (r.get('comment') or '')[:1000], rev_status.get(r.get('status','visible'), 'visible'), ts, 0))
    rev_ext_ids.append(r['review_id'])

bulk_insert('reviews', ['product_id', 'order_item_id', 'user_id', 'rating', 'comment', 'status', 'created_at', 'like_count'], reviews)
with connection.cursor() as cur:
    cur.execute("SELECT review_id FROM reviews ORDER BY review_id")
    rev_ids = [r[0] for r in cur.fetchall()]

rev_map = dict(zip(rev_ext_ids, rev_ids)) if len(rev_ext_ids) == len(rev_ids) else {}
print(f"  Reviews: {len(reviews)} ({rev_skipped} skipped)")

print("=== Phase 10: Refunds ===")

refund_status = {'approve': 'approved', 'approved': 'approved', 'pending': 'pending',
                 'reject': 'rejected', 'rejected': 'rejected', 'refunded': 'refunded'}
refunds = []
ref_ext_by_no = {}
ref_item_specs = []
for r in read_csv('RefundRequest.csv'):
    oid = order_map.get(r['purchase_id'])
    if not oid:
        continue
    rno = r['refund_id']
    uid = db_order_user.get(oid) or order_user_map.get(r['purchase_id'])
    ts = r.get('last_update', '')
    refunds.append((rno, oid, uid, r.get('refund_reason','')[:500], Decimal(str(r.get('refund_money') or 0)), refund_status.get(r.get('refund_status','pending'), 'pending'), '', ts, ts))
    ref_ext_by_no[rno] = r['refund_id']
    ref_item_specs.append((rno, oid, r))

bulk_insert('refunds', ['refund_no', 'order_id', 'user_id', 'reason', 'total_amount', 'status', 'admin_remark', 'created_at', 'updated_at'], refunds)

with connection.cursor() as cur:
    cur.execute("SELECT id, refund_no FROM refunds")
    ref_no_to_id = {rno: rid for rid, rno in cur.fetchall()}

refund_map = {ext_id: ref_no_to_id[rno] for rno, ext_id in ref_ext_by_no.items() if rno in ref_no_to_id}

# Refund items
ri_rows = []
for rno, oid, row in ref_item_specs:
    oiid = first_oi.get(oid)
    rid = ref_no_to_id.get(rno)
    if not oiid or not rid:
        continue
    ri_rows.append((rid, oiid, 1, Decimal(str(row.get('refund_money') or 0))))

bulk_insert('refund_items', ['refund_id', 'order_item_id', 'quantity', 'refund_amount'], ri_rows)
print(f"  Refunds: {len(refund_map)}, Items: {len(ri_rows)}")

print("=== Phase 11: Audit Logs ===")

logs = []
def add_audit(user_ext, action, table, record_id, old='', new='', desc=''):
    uid = user_id_map.get(user_ext)
    import json
    logs.append((uid, (action or 'UPDATE').upper()[:50], table[:50], str(record_id)[:50],
                 desc or '', old or '', new or '',
                 json.dumps({'external_id': str(record_id)}, ensure_ascii=False)))

if csv_exists('Store_audit.csv'):
    for r in read_csv('Store_audit.csv'):
        add_audit(r.get('admin_id'), r.get('action_type'), 'shops', shop_map.get(r.get('store_id'), r.get('store_id')), desc=r.get('reason',''))

if csv_exists('Product_moderation.csv'):
    for r in read_csv('Product_moderation.csv'):
        add_audit(r.get('admin_id'), r.get('action_type'), 'products', prod_map.get(r.get('product_id'), r.get('product_id')), desc=r.get('reason',''))

if csv_exists('Review_moderation.csv'):
    for r in read_csv('Review_moderation.csv'):
        add_audit(r.get('admin_id'), r.get('action_type'), 'reviews', rev_map.get(r.get('review_id'), r.get('review_id')))

if csv_exists('Category_action.csv'):
    for r in read_csv('Category_action.csv'):
        add_audit(r.get('admin_id'), r.get('action_type'), 'categories', cat_map.get(r.get('category_id'), r.get('category_id')), old=r.get('old_value',''), new=r.get('new_value',''))

if csv_exists('refundAction.csv'):
    for r in read_csv('refundAction.csv'):
        actor = r.get('actor_admin_id') or r.get('actor_seller_id') or r.get('actor_customer_id')
        add_audit(actor, r.get('action_type'), 'refunds', refund_map.get(r.get('refund_id'), r.get('refund_id')))

# Fix: insert logs one at a time to handle FK correctly
with connection.cursor() as cur:
    for (user_id, action, table_name, record_id, description, old_value, new_value, detail) in logs:
        cur.execute(
            "INSERT INTO audit_logs (user_id, action, table_name, record_id, description, old_value, new_value, detail, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
            [user_id, action, table_name, record_id, description, old_value, new_value, detail]
        )
print(f"  Audit logs: {len(logs)}")

print("=== DONE ===")
