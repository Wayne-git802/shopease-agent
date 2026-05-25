"""Tool registration for CustomerServiceAgent.

Import this module once at startup to register all customer service tools.
"""

from agents.core.tool_registry import get_tool_registry, Tool
from agents.customer_service.tools import (
    search_products, get_user_orders, get_return_policy, get_product_categories,
)
from agents.core.repos import find_products  # fallback


def _search_products_handler(args: dict, user_id=None) -> str:
    import json
    result = search_products(args.get('query', ''), args.get('limit', 5))
    return f"商品搜索结果: {json.dumps(result, ensure_ascii=False)}"


def _search_products_fallback(args: dict, user_id=None) -> str:
    """Fallback: simple keyword match without DB."""
    query = args.get('query', '')
    if not query:
        return "请提供搜索关键词"
    return f"搜索功能暂时不可用，请稍后再试。您想找的是「{query}」相关商品吗？"


def _get_orders_handler(args: dict, user_id=None) -> str:
    import json
    if not user_id:
        return "需要登录才能查询订单"
    result = get_user_orders(user_id, args.get('limit', 5))
    return f"用户订单: {json.dumps(result, ensure_ascii=False)}"


def _get_orders_fallback(args: dict, user_id=None) -> str:
    return "订单查询暂时不可用，请稍后再试"


def _return_policy_handler(args: dict, user_id=None) -> str:
    return get_return_policy()


def _categories_handler(args: dict, user_id=None) -> str:
    import json
    cats = get_product_categories()
    return f"商品分类: {json.dumps(cats, ensure_ascii=False)}"


def register_cs_tools() -> None:
    """Register all customer service tools."""
    registry = get_tool_registry()

    registry.register(Tool(
        name='search_products',
        description='搜索商品，按名称或描述匹配',
        parameters={
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '搜索关键词'},
                'limit': {'type': 'integer', 'default': 5},
            },
            'required': ['query'],
        },
        handler=_search_products_handler,
        fallback=_search_products_fallback,
    ))

    registry.register(Tool(
        name='get_user_orders',
        description='查询用户的最近订单列表',
        parameters={
            'type': 'object',
            'properties': {
                'limit': {'type': 'integer', 'default': 5},
            },
        },
        handler=_get_orders_handler,
        fallback=_get_orders_fallback,
    ))

    registry.register(Tool(
        name='get_return_policy',
        description='获取退货政策说明',
        parameters={'type': 'object', 'properties': {}},
        handler=_return_policy_handler,
        # No fallback — this is static text, always works
    ))

    registry.register(Tool(
        name='get_product_categories',
        description='获取所有商品分类列表',
        parameters={'type': 'object', 'properties': {}},
        handler=_categories_handler,
    ))
