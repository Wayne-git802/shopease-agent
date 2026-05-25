"""
ImporterRuntime — production-grade ETL framework for CSV → Django ORM.

Features:
- batch atomic transactions (1000 rows/batch)
- checkpoint/resume via import_state.json
- 5-category error classification
- bulk_create with automatic legacy_id mapping (no id_map dicts needed)
- dry-run mode
"""

import csv
import json
import os
import time
import enum
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Any, Optional

from django.db import transaction, connection


BATCH_SIZE = 1000
CHECKPOINT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'import_state.json')

# DATA_DIR = <project_root>/data(1)/  where project_root = shop_agent/
# runtime.py lives at: shop_agent/backend/products/management/commands/importers/runtime.py
from pathlib import Path
DATA_DIR = str(Path(__file__).resolve().parents[5] / 'data(1)')


# ── Error classification ──────────────────────────────────────────

class ErrorKind(enum.Enum):
    FK_MISSING       = "fk_missing"       # legacy_id can't resolve FK
    VALIDATION       = "validation"       # ORM full_clean() failed
    DUPLICATE        = "duplicate"        # legacy_id unique constraint violation
    PARSE            = "parse"            # CSV field type error
    BUSINESS         = "business"         # domain rule (assert_same, etc.)


@dataclass
class ImportError:
    kind: ErrorKind
    row: int
    detail: str
    field: str = ""


@dataclass
class ImportStats:
    imported: int = 0
    skipped: int = 0
    errors: list[ImportError] = field(default_factory=list)

    @property
    def error_count(self):
        return len(self.errors)

    def error_summary(self):
        by_kind = defaultdict(int)
        for e in self.errors:
            by_kind[e.kind.value] += 1
        return dict(by_kind)


# ── Checkpoint ─────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    """Returns {completed: [str], stats: {name: {imported, skipped, errors}}}"""
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "stats": {}, "version": 1}


def save_checkpoint(name: str, stats: ImportStats):
    ck = load_checkpoint()
    if name not in ck["completed"]:
        ck["completed"].append(name)
    ck["stats"][name] = {
        "imported": stats.imported,
        "skipped": stats.skipped,
        "errors": stats.error_count,
    }
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump(ck, f, indent=2, ensure_ascii=False)


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)


# ── CSV helpers ────────────────────────────────────────────────────

def read_csv(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def csv_exists(filename: str) -> bool:
    return os.path.exists(os.path.join(DATA_DIR, filename))


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(Decimal(str(value or default)))
    except Exception:
        return default


def parse_legacy_id(raw_id: str) -> int:
    """Strip non-digit prefix: 'CAT0001'→1, 'P0000001'→1, 'PR0000876'→876, 'ST00792'→792."""
    digits = ''.join(c for c in str(raw_id) if c.isdigit())
    return int(digits) if digits else 0


def to_decimal(value: Any, default: str = '0') -> Decimal:
    try:
        return Decimal(str(value or default))
    except Exception:
        return Decimal(default)


def clamp(value: Any, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(float(value or low))))
    except (ValueError, TypeError):
        return low


# ── ImporterRuntime ────────────────────────────────────────────────

class ImporterRuntime:
    """
    Base class for all importers. Provides:
    - batch_atomic: chunk rows, commit every BATCH_SIZE inside a transaction
    - error collection with 5-category classification
    - dry-run support
    - progress output
    - legacy_id helper: resolve FK by old CSV ID
    """

    def __init__(self, name: str, dry_run: bool = False, verbosity: int = 1):
        self.name = name
        self.dry_run = dry_run
        self.verbosity = verbosity
        self.stats = ImportStats()

    def log(self, msg: str, level: int = 1):
        if self.verbosity >= level:
            print(f"[{self.name:>12s}] {msg}")

    def error(self, kind: ErrorKind, row_num: int, detail: str, field: str = ""):
        err = ImportError(kind=kind, row=row_num, detail=detail, field=field)
        self.stats.errors.append(err)

    def batch_atomic(self, rows: list[dict], build_fn: Callable, batch_size: int = BATCH_SIZE) -> list:
        """
        Iterate over rows in batches, each wrapped in transaction.atomic().
        build_fn(row, idx) -> model_instance or None.
        Returns list of created instances.
        """
        created = []
        for start in range(0, len(rows), batch_size):
            chunk = rows[start:start + batch_size]
            batch_instances = []
            for i, row in enumerate(chunk):
                row_num = start + i + 2  # +2 for header + 1-indexed
                try:
                    obj = build_fn(row, row_num)
                    if obj is not None:
                        batch_instances.append(obj)
                except Exception as e:
                    self.error(ErrorKind.BUSINESS, row_num, str(e))

            if batch_instances and not self.dry_run:
                try:
                    with transaction.atomic():
                        model_class = type(batch_instances[0])
                        model_class.objects.bulk_create(batch_instances, batch_size=batch_size)
                    created.extend(batch_instances)
                except Exception as e:
                    self.error(ErrorKind.VALIDATION, start + 2,
                               f"Batch bulk_create failed: {e}")
            elif batch_instances and self.dry_run:
                created.extend(batch_instances)

        self.stats.imported = len(created)
        return created

    def bulk_create(self, instances: list, batch_size: int = BATCH_SIZE) -> list:
        """Simple bulk_create wrapper with error handling."""
        if not instances:
            return instances
        if self.dry_run:
            self.stats.imported = len(instances)
            return instances
        try:
            model_class = type(instances[0])
            with transaction.atomic():
                model_class.objects.bulk_create(instances, batch_size=batch_size)
            self.stats.imported = len(instances)
        except Exception as e:
            self.error(ErrorKind.VALIDATION, 0, f"bulk_create failed: {e}")
        return instances

    def legacy_resolve(self, model_class, legacy_id: Any, offset: int = 0) -> Optional[Any]:
        """Resolve FK by legacy_id field. offset adds type-specific prefix (e.g. 200000 for sellers)."""
        if legacy_id is None or legacy_id == '':
            return None
        try:
            lid = parse_legacy_id(str(legacy_id)) + offset
            return model_class.objects.get(legacy_id=lid)
        except (ValueError, model_class.DoesNotExist):
            return None

    def legacy_resolve_id(self, model_class, legacy_id: Any, offset: int = 0) -> Optional[int]:
        obj = self.legacy_resolve(model_class, legacy_id, offset)
        return obj.id if obj else None

    def finish(self):
        """Called after import completes. Returns True if no errors."""
        self.log(f"✓ imported={self.stats.imported}, skipped={self.stats.skipped}, "
                 f"errors={self.stats.error_count}")
        if self.stats.error_summary():
            self.log(f"  error breakdown: {self.stats.error_summary()}", level=0)
        if not self.dry_run:
            save_checkpoint(self.name, self.stats)
        return self.stats.error_count == 0


def assert_same(field_name: str, value_map: dict, row_num: int, runtime: ImporterRuntime):
    """Assert all values for a grouped field are the same."""
    if len(value_map) <= 1:
        return
    vals = list(value_map.values())
    first = vals[0]
    for k, v in value_map.items():
        if v != first:
            runtime.error(ErrorKind.BUSINESS, row_num,
                          f"Field '{field_name}' inconsistent across group: "
                          f"{k}={v} vs first={first}",
                          field=field_name)
