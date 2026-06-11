from __future__ import annotations

from products.models import Product


class ProductQuery:
    @staticmethod
    def base():
        return Product.objects.filter(is_active=True)

    @staticmethod
    def purchasable():
        return (
            ProductQuery.base()
            .filter(inventory__quantity__gt=0)
            .distinct()
        )
