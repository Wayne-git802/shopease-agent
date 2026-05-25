"""
Import test data from CSV into Django models using ImporterRuntime framework.

Usage:
    python manage.py import_test_data                  # Full import
    python manage.py import_test_data --resume          # Resume from checkpoint
    python manage.py import_test_data --clear-db         # Clear DB first, then import
    python manage.py import_test_data --dry-run          # Validate without writing

Architecture:
    - legacy_id on models (no in-memory id_map)
    - checkpoint/resume via import_state.json
    - batch_atomic (1000 rows/transaction)
    - 5-category error classification
    - assert_same for order aggregation
    - bulk_create for all large tables
"""

from django.core.management.base import BaseCommand
from django.db import connection

from .importers.runtime import (
    ImporterRuntime, load_checkpoint, save_checkpoint,
    clear_checkpoint, CHECKPOINT_PATH,
)


IMPORTERS = [
    # (name, module_name, description)
    ('categories', 'products.management.commands.importers.categories', 'Category hierarchy'),
    ('users',      'products.management.commands.importers.users',      'Users (admin/seller/customer)'),
    ('shops',      'products.management.commands.importers.shops',      'Online stores → Shops'),
    ('products',   'products.management.commands.importers.products',   'Products + Inventory'),
    ('carts',      'products.management.commands.importers.carts',      'Shopping carts'),
    ('orders',     'products.management.commands.importers.orders',     'Orders + OrderItems'),
    ('reviews',    'products.management.commands.importers.reviews',    'Product reviews'),
    ('refunds',    'products.management.commands.importers.refunds',    'Refund requests'),
]


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--resume', action='store_true',
                            help='Resume from last checkpoint (skip completed importers)')
        parser.add_argument('--clear-db', action='store_true',
                            help='Clear all existing imported data before import')
        parser.add_argument('--dry-run', action='store_true',
                            help='Validate without writing to database')
        parser.add_argument('--verbose', type=int, default=1,
                            help='Verbosity level (1=normal, 0=quiet, 2=detailed)')

    def handle(self, *args, **options):
        resume = options['resume']
        clear_db = options['clear_db']
        dry_run = options['dry_run']
        verbose = options['verbose']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no data will be written'))

        # ── Checkpoint ──
        checkpoint = load_checkpoint() if resume else {"completed": [], "stats": {}, "version": 1}
        completed = set(checkpoint.get("completed", []))
        if resume and completed:
            self.stdout.write(f"Resuming — already completed: {', '.join(sorted(completed))}")

        # ── Clear DB ──
        if clear_db:
            self._clear_database()
            clear_checkpoint()
            completed = set()

        # ── Import pipeline ──
        total_ok = 0
        total_fail = 0
        results = []

        for name, module_path, description in IMPORTERS:
            if name in completed:
                prev_stats = checkpoint.get("stats", {}).get(name, {})
                self.stdout.write(
                    f"[SKIP] {name} ({description}) — "
                    f"already completed: {prev_stats.get('imported', '?')} imported, "
                    f"{prev_stats.get('errors', '?')} errors"
                )
                continue

            self.stdout.write(f"[START] {name} ({description})")
            runtime = ImporterRuntime(name=name, dry_run=dry_run, verbosity=verbose)

            try:
                mod = __import__(module_path, fromlist=['import_fn'])
                import_fn_name = f'import_{name}'
                import_fn = getattr(mod, import_fn_name)
                import_fn(runtime)

                if runtime.stats.error_count == 0:
                    total_ok += 1
                    results.append(f"✅ {name}: {runtime.stats.imported} imported")
                else:
                    total_fail += 1
                    results.append(
                        f"🔴 {name}: {runtime.stats.imported} imported, "
                        f"{runtime.stats.error_count} errors: {runtime.stats.error_summary()}"
                    )
            except Exception as e:
                total_fail += 1
                results.append(f"🔴 {name}: CRASHED — {e}")
                self.stdout.write(self.style.ERROR(f"  {e}"))

        # ── Summary ──
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("IMPORT SUMMARY")
        self.stdout.write("=" * 60)
        for line in results:
            if '✅' in line:
                self.stdout.write(self.style.SUCCESS(line))
            else:
                self.stdout.write(self.style.ERROR(line))
        self.stdout.write(f"\nPassed: {total_ok}/{len(IMPORTERS)}, Failed: {total_fail}")

        if not dry_run and total_fail == 0:
            clear_checkpoint()
            self.stdout.write(self.style.SUCCESS("✓ All imports complete — checkpoint cleared"))
        elif not dry_run and total_fail > 0:
            self.stdout.write(self.style.WARNING(
                f"Checkpoint saved at {CHECKPOINT_PATH}. "
                f"Fix errors and run with --resume to continue."
            ))

    @staticmethod
    def _clear_database():
        """Clear all imported data, preserving admin/wayne superusers."""
        from admin_api.models import AuditLog
        from orders.models import Cart, RefundItem, Refund, OrderItem, Order
        from products.models import (
            Review, InventoryTransaction, Inventory, Product,
            ShopFollow, Shop, Category,
        )
        from users.models import User

        # Preserve superusers
        preserved = list(User.objects.filter(
            username__in=['admin', 'wayne']
        ).values('username', 'password', 'display_name', 'is_staff', 'is_superuser',
                  'is_active', 'phone', 'email', 'date_joined'))

        print("Clearing database...")
        for model in [
            AuditLog, RefundItem, Refund, OrderItem, Order, Cart, Review,
            InventoryTransaction, Inventory, Product, ShopFollow, Shop, Category,
        ]:
            count = model.objects.count()
            model.objects.all().delete()
            print(f"  Deleted {count} {model.__name__}")

        # Delete non-preserved users
        deleted = User.objects.exclude(username__in=['admin', 'wayne']).delete()[0]
        print(f"  Deleted {deleted} users")

        # Reset auto-increment
        tables = [
            'audit_logs', 'refund_items', 'refunds', 'order_items', 'orders',
            'carts', 'reviews', 'inventory_transactions', 'inventory',
            'products', 'shop_follows', 'shops', 'categories', 'users',
        ]
        with connection.cursor() as cursor:
            vendor = connection.vendor
            for table in tables:
                try:
                    if vendor == 'sqlite':
                        cursor.execute(
                            "DELETE FROM sqlite_sequence WHERE name = %s", [table])
                    elif vendor == 'mysql':
                        cursor.execute(f'ALTER TABLE {table} AUTO_INCREMENT = 1')
                except Exception:
                    pass  # Table might not have auto-increment

        # Restore preserved users
        for u in preserved:
            User.objects.get_or_create(username=u['username'], defaults=u)
        print(f"  Restored {len(preserved)} preserved users (admin, wayne)")

        import time
        print("Waiting 2s for DB to settle...")
        time.sleep(2)
