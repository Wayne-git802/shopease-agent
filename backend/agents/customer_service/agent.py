"""CustomerServiceAgent — intelligent customer support.

Architecture flow:
    1. Semantic cache check (tier 1 — 0 token cost if hit)
    2. Load layered prompt (tier 2 — base: 200 tok, full on demand)
    3. Inject user preferences (MySQL UserPreference + Hermes MemoryBridge)
    4. Call LLM with tools (product search, order lookup, return policy)
    5. Stream response via SSE (tier 3 — context compression after 6 rounds)
    6. Cache the Q&A pair for future reuse
"""

import json
import logging
from typing import Optional

from agents.core.base_agent import BaseAgent, AgentContext, AgentResult
from agents.core.prompt_loader import get_prompt_loader
from agents.core.semantic_cache import get_semantic_cache
from agents.core.memory_bridge import get_memory_bridge

logger = logging.getLogger(__name__)

# Max conversation rounds before summarization
MAX_ROUNDS_BEFORE_SUMMARY = 6


class CustomerServiceAgent(BaseAgent):
    """Intelligent customer service agent for ShopEase."""

    agent_type = 'customer_service'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._prompts = get_prompt_loader()
        self._cache = get_semantic_cache()
        self._memory = get_memory_bridge()

    # ── main logic ──────────────────────────────────────────────

    def _process(self, user_input: str, context: AgentContext) -> AgentResult:
        """Handle one customer inquiry."""
        user_id = context.user_id

        # ── Tier 1: Semantic cache ──
        cached = self._cache.lookup(user_input, agent_type=self.agent_type)
        if cached:
            self._save_conversation(user_id, context.session_id,
                                    user_input, cached, cache_hit=True)
            return AgentResult(
                status='ok', text=cached, tokens_used=0, cache_hit=True,
            )

        # ── Tier 2: Build prompt with layers ──
        use_full = len(user_input) > 20 or self._count_rounds(
            context.session_id, user_id) > 2
        layer = 'full' if use_full else 'base'

        prompt = self._build_prompt(user_input, user_id, context, layer)

        # ── Tier 3: Call LLM with tools ──
        tools = self._get_tools_spec()
        response = self._llm_chat(prompt, tools=tools)

        # Handle tool calls if the LLM requested them
        final_text = response.text
        if response.tool_calls:
            final_text = self._execute_tools(response.tool_calls, user_id)

        # ── Cache the result ──
        self._cache.store(user_input, final_text, agent_type=self.agent_type)

        # ── Persist conversation ──
        self._save_conversation(user_id, context.session_id,
                                user_input, final_text,
                                tokens_used=response.tokens_used)

        # ── Extract & store preferences ──
        self._extract_preferences(user_id, user_input, final_text)

        return AgentResult(
            status='ok',
            text=final_text,
            tokens_used=response.tokens_used,
            cache_hit=False,
        )

    # ── prompt construction ─────────────────────────────────────

    def _build_prompt(self, user_input: str, user_id: Optional[int],
                      context: AgentContext, layer: str) -> str:
        """Assemble the layered prompt with all context injected."""
        # Load user preferences from both stores
        user_name = ''
        user_prefs = {}
        if user_id:
            user_name = self._get_user_name(user_id)
            user_prefs = self._load_preferences(user_id)

        # Conversation summary (if > 6 rounds)
        summary = self._maybe_summarize(context.session_id, user_id)

        return self._prompts.render(
            'system',
            layer=layer,
            product_count=5300,
            shop_count=7000,
            user_name=user_name,
            user_preferences=json.dumps(user_prefs, ensure_ascii=False) if user_prefs else '',
            conversation_summary=summary or '',
            user_input=user_input,
        )

    # ── tools ───────────────────────────────────────────────────

    def _get_tools_spec(self) -> list[dict]:
        """Return the OpenAI-compatible tool definitions."""
        return [
            {
                'type': 'function',
                'function': {
                    'name': 'search_products',
                    'description': '搜索商品，按名称或描述匹配',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'query': {'type': 'string', 'description': '搜索关键词'},
                            'limit': {'type': 'integer', 'default': 5},
                        },
                        'required': ['query'],
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'get_user_orders',
                    'description': '查询用户的最近订单列表',
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            'limit': {'type': 'integer', 'default': 5},
                        },
                    },
                },
            },
            {
                'type': 'function',
                'function': {
                    'name': 'get_return_policy',
                    'description': '获取退货政策说明',
                    'parameters': {'type': 'object', 'properties': {}},
                },
            },
        ]

    def _execute_tools(self, tool_calls: list, user_id: Optional[int]) -> str:
        """Execute tool calls from the LLM and format the result."""
        from .tools import search_products, get_user_orders, get_return_policy

        results = []
        for tc in tool_calls:
            name = tc.get('function', {}).get('name', '')
            args = json.loads(tc.get('function', {}).get('arguments', '{}'))

            try:
                if name == 'search_products':
                    data = search_products(args.get('query', ''), args.get('limit', 5))
                    results.append(f"商品搜索结果: {json.dumps(data, ensure_ascii=False)}")
                elif name == 'get_user_orders':
                    if user_id:
                        data = get_user_orders(user_id, args.get('limit', 5))
                        results.append(f"用户订单: {json.dumps(data, ensure_ascii=False)}")
                    else:
                        results.append("需要登录才能查询订单")
                elif name == 'get_return_policy':
                    results.append(get_return_policy())
                else:
                    results.append(f"未知工具: {name}")
            except Exception as exc:
                logger.warning("Tool %s failed: %s", name, exc)
                results.append(f"工具 {name} 执行失败: {exc}")

        return '\n\n'.join(results)

    # ── preferences ─────────────────────────────────────────────

    def _load_preferences(self, user_id: int) -> dict:
        """Load user preferences from MySQL + Hermes Memory."""
        prefs = {}

        # Medium-term: MySQL UserPreference
        try:
            from agents.models import UserPreference
            for up in UserPreference.objects.filter(user_id=user_id):
                prefs[up.key] = up.value
        except Exception:
            pass

        # Long-term: Hermes Memory (cross-project)
        try:
            hermes_prefs = self._memory.get_user_preferences(user_id)
            prefs.update(hermes_prefs)  # Hermes overrides MySQL
        except Exception:
            pass

        return prefs

    def _extract_preferences(self, user_id: Optional[int],
                             user_input: str, response: str) -> None:
        """Heuristically extract user preferences from the conversation."""
        if not user_id:
            return

        # Simple keyword-based extraction (Phase 5 MetaAgent will improve this)
        preferences = {
            '喜欢红色': ['红色', '红的', '红款'],
            '喜欢简约': ['简约', '简洁', '简单'],
            '预算偏低': ['便宜', '优惠', '打折', '低价'],
            '预算偏高': ['高端', '贵的', '品质', '旗舰'],
        }

        for pref_key, keywords in preferences.items():
            if any(kw in user_input for kw in keywords):
                try:
                    from agents.models import UserPreference
                    UserPreference.objects.update_or_create(
                        user_id=user_id,
                        key=pref_key,
                        defaults={
                            'value': 'true',
                            'source_agent': self.agent_type,
                            'confidence': 0.6,
                        },
                    )
                    # Also store in Hermes long-term memory
                    self._memory.set_user_preference(
                        user_id, pref_key, 'true',
                        source_agent=self.agent_type, confidence=0.6,
                    )
                except Exception:
                    pass

    # ── conversation management ─────────────────────────────────

    def _save_conversation(self, user_id: Optional[int], session_id: str,
                           user_msg: str, assistant_msg: str,
                           cache_hit: bool = False,
                           tokens_used: int = 0) -> None:
        """Persist conversation turns to MySQL."""
        if not user_id or not session_id:
            return
        try:
            from agents.models import AgentConversation
            AgentConversation.objects.create(
                user_id=user_id, agent_type=self.agent_type,
                session_id=session_id, role='user',
                content=user_msg,
            )
            AgentConversation.objects.create(
                user_id=user_id, agent_type=self.agent_type,
                session_id=session_id, role='assistant',
                content=assistant_msg,
                tokens_used=tokens_used,
            )
        except Exception as exc:
            logger.warning("Failed to save conversation: %s", exc)

    def _count_rounds(self, session_id: str, user_id: Optional[int]) -> int:
        """Count how many rounds exist in this session."""
        if not user_id or not session_id:
            return 0
        try:
            from agents.models import AgentConversation
            user_msgs = AgentConversation.objects.filter(
                user_id=user_id, session_id=session_id, role='user',
            ).count()
            return user_msgs
        except Exception:
            return 0

    def _maybe_summarize(self, session_id: str,
                         user_id: Optional[int]) -> Optional[str]:
        """Summarize conversation if > 6 rounds (tier 3: context compression)."""
        if not user_id or not session_id:
            return None
        rounds = self._count_rounds(session_id, user_id)
        if rounds <= MAX_ROUNDS_BEFORE_SUMMARY:
            return None

        try:
            from agents.models import AgentConversation
            msgs = AgentConversation.objects.filter(
                user_id=user_id, session_id=session_id,
            ).order_by('-created_at')[:12]  # last 6 rounds

            # Simple extractive summary: take first user message as topic
            user_msgs = [m.content for m in msgs if m.role == 'user']
            if not user_msgs:
                return None

            topic = user_msgs[-1][:50]  # earliest user message
            return f"用户之前咨询了: {topic}（共 {rounds} 轮对话）"
        except Exception:
            return None

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _get_user_name(user_id: int) -> str:
        """Get the display name of a user."""
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            return getattr(user, 'username', '') or getattr(user, 'name', '') or ''
        except Exception:
            return ''
