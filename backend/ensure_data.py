import base64
import csv
import hashlib
import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

import django
from django.core.management import call_command
from django.contrib.auth.hashers import check_password

django.setup()

from products.models import Product
from users.models import User


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data(1)"
PASSWORD_SYNC_MARKER = Path(__file__).resolve().parent / ".csv_passwords_synced"


def fast_password_hash(raw_password):
    algo = "pbkdf2_sha256"
    iterations = 1000
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", raw_password.encode(), salt.encode(), iterations, dklen=32)
    return f"{algo}${iterations}${salt}${base64.b64encode(dk).decode().strip()}"


def read_csv(filename):
    with (DATA_DIR / filename).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_small_demo_data():
    seed_path = Path(__file__).resolve().parent / "seed_data.py"
    namespace = {"__file__": str(seed_path), "__name__": "__main__"}
    exec(seed_path.read_text(encoding="utf-8"), namespace)


def csv_sample_passwords_match():
    samples = [
        ("Customer.csv", "customer_id"),
        ("Seller.csv", "seller_id"),
    ]
    for filename, id_field in samples:
        path = DATA_DIR / filename
        if not path.exists():
            continue
        rows = read_csv(filename)
        if not rows:
            continue
        row = rows[0]
        user = User.objects.filter(username=row[id_field].lower()).first()
        if user and not check_password(row["password"], user.password):
            return False
    return True


def sync_csv_passwords():
    if not DATA_DIR.exists():
        return

    if PASSWORD_SYNC_MARKER.exists() and csv_sample_passwords_match():
        print("CSV account passwords are ready.")
        return

    if csv_sample_passwords_match():
        PASSWORD_SYNC_MARKER.touch()
        print("CSV account passwords are ready.")
        return

    print("Syncing account passwords from CSV files...")
    specs = [
        ("Customer.csv", "customer_id", False),
        ("Seller.csv", "seller_id", False),
        ("Admin.csv", "admin_id", True),
    ]
    total = 0
    for filename, id_field, is_staff in specs:
        path = DATA_DIR / filename
        if not path.exists():
            continue
        rows = read_csv(filename)
        usernames = [row[id_field].lower() for row in rows]
        users = User.objects.in_bulk(usernames, field_name="username")
        changed = []
        for row in rows:
            user = users.get(row[id_field].lower())
            if not user:
                continue
            user.password = fast_password_hash(row["password"])
            if is_staff:
                user.is_staff = True
            changed.append(user)
        if changed:
            User.objects.bulk_update(changed, ["password", "is_staff"], batch_size=1000)
            total += len(changed)

    admin = User.objects.filter(username="admin").first()
    if admin and not check_password("admin123", admin.password):
        admin.password = fast_password_hash("admin123")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save(update_fields=["password", "is_staff", "is_superuser"])
        total += 1

    PASSWORD_SYNC_MARKER.touch()
    print(f"Synced {total} account passwords from CSV files.")


def main():
    if User.objects.exists() and Product.objects.exists():
        print("Database data is ready.")
        sync_csv_passwords()
        return

    if DATA_DIR.exists():
        print("Database is empty. Importing CSV data from data(1); this may take a few minutes on first run...")
        try:
            call_command("import_csv_data", clear=True)
            sync_csv_passwords()
            return
        except Exception as exc:
            print(f"CSV import failed: {exc}")
            print("Falling back to small demo data.")

    load_small_demo_data()


if __name__ == "__main__":
    main()
