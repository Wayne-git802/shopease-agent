"""
Routing Model — Two-tier intent classification.

FastRouter: embedding similarity → 5-way classifier (fast path).
LLMFallback: LLM-based classification (slow path, when FastRouter confidence < 0.85).

Top-level route(query, history) → RoutingOutput with intent, confidence, routing_method.
"""

import json
import logging
import re
from typing import Optional

from .state import AgentState, ChatMessage
from .contracts import RoutingInput, RoutingOutput
from agents.core.llm_client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

INTENTS = ["search", "recommend", "order", "ops", "chat"]

# Intent descriptions used for embedding similarity
INTENT_DESCRIPTIONS: dict[str, str] = {
    "search":    "find products, search catalog, look up items, browse inventory, keyword search",
    "recommend": "get recommendations, suggest products, personalized picks, what should I buy, trending",
    "order":     "check order status, cancel order, refund, return, track shipment, order detail, purchase history",
    "ops":       "system health, alerts, monitoring, operational status, reports, metrics, diagnostics",
    "chat":      "general conversation, chitchat, help, how are you, small talk, greetings, thank you",
}

FAST_CONFIDENCE_THRESHOLD = 0.85


# ── Embedding helpers ──────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Simple tokenization: lowercase + split on non-alphanumeric."""
    return set(re.findall(r"\w+", text.lower()))


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ── FastRouter ─────────────────────────────────────────────────────

class FastRouter:
    """Embedding-based fast-path intent classifier.

    Uses keyword overlap (Jaccard similarity) with keyword boosting
    to classify user queries into 5 intent categories.

    Production upgrade path: replace Jaccard with cosine similarity
    over real embeddings (e.g., OpenAI text-embedding-3-small).
    """

    def __init__(self) -> None:
        # Pre-compute token sets for each intent description
        self._intent_tokens: dict[str, set[str]] = {
            intent: _tokenize(desc)
            for intent, desc in INTENT_DESCRIPTIONS.items()
        }
        # Intent-specific keyword boosters
        self._keyword_boost: dict[str, list[str]] = {
            "search":    ["search", "find", "look", "show", "product", "item",
                          "catalog", "price", "available", "buy"],
            "recommend": ["recommend", "suggest", "popular", "trending", "best",
                          "top", "pick", "for me", "gift", "like"],
            "order":     ["order", "cancel", "refund", "return", "ship", "track",
                          "status", "delivery", "bought", "purchase"],
            "ops":       ["health", "alert", "monitor", "system", "metric",
                          "report", "status", "check", "diagnostic"],
            "chat":      ["hello", "hi", "hey", "help", "thanks", "bye",
                          "how are you", "what's up", "good morning"],
        }

    def classify(
        self, query: str, history: list[ChatMessage] | None = None
    ) -> tuple[str, float, str]:
        """Fast-path classification via Jaccard similarity + keyword boosting.

        Returns:
            (intent, confidence, routing_method)
        """
        query_tokens = _tokenize(query)

        # Compute Jaccard similarity with each intent
        scores: dict[str, float] = {}
        for intent in INTENTS:
            base_score = _jaccard_similarity(query_tokens, self._intent_tokens[intent])
            # Apply keyword boosting
            keywords = self._keyword_boost.get(intent, [])
            keyword_hits = sum(1 for kw in keywords if kw in query.lower())
            boost = min(keyword_hits * 0.08, 0.24)  # cap boost at 0.24
            scores[intent] = base_score + boost

        # Normalize to [0, 1]
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        # Pick best intent
        best_intent = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = scores[best_intent]

        # Determine routing method
        if confidence >= FAST_CONFIDENCE_THRESHOLD:
            return best_intent, confidence, "fast"
        else:
            return best_intent, confidence, "fast"  # method is still "fast" — caller decides fallback

    def route(
        self, query: str, history: list[ChatMessage] | None = None
    ) -> RoutingOutput:
        """Route a query through the fast path. Returns RoutingOutput."""
        intent, confidence, method = self.classify(query, history)
        return RoutingOutput(
            intent=intent,
            confidence=confidence,
            routing_method=method,
        )


# ── LLMFallback ────────────────────────────────────────────────────

class LLMFallback:
    """LLM-based intent classifier for the slow path.

    Used when FastRouter confidence is below FAST_CONFIDENCE_THRESHOLD.
    Uses the OpenAI-compatible API via the existing LLMClient.
    """

    SYSTEM_PROMPT = (
        "You are an intent classifier for an e-commerce assistant. "
        "Classify the user's query into exactly one of these intents:\n\n"
        "- search: Finding/searching for products, browsing catalog, looking up items\n"
        "- recommend: Asking for recommendations, suggestions, personalized picks\n"
        "- order: Order management (status, cancel, refund, return, tracking)\n"
        "- ops: System operations, health checks, alerts, monitoring, reports\n"
        "- chat: General conversation, chitchat, help, greetings, small talk\n\n"
        "Respond with ONLY a JSON object:\n"
        '{"intent": "<intent>", "confidence": <float 0-1>, "reasoning": "<brief reason>"}'
    )

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm: LLMClient = llm_client or get_llm_client()

    def classify(
        self, query: str, history: list[ChatMessage] | None = None
    ) -> tuple[str, float, str]:
        """LLM-based classification.

        Returns:
            (intent, confidence, routing_method) — routing_method is always "slow".
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]

        # Include recent history for context (last 4 turns)
        if history:
            for msg in history[-4:]:
                role = msg.role if isinstance(msg, ChatMessage) else msg.get("role", "user")
                content = msg.content if isinstance(msg, ChatMessage) else msg.get("content", "")
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": query})

        # Build single prompt for LLMClient.chat interface
        prompt = self._build_prompt(messages)

        try:
            response = self._llm.chat(prompt, max_tokens=200)
            text = response.text.strip()

            result = self._parse_response(text)
            intent = result.get("intent", "chat")
            confidence = float(result.get("confidence", 0.5))

            # Validate intent
            if intent not in INTENTS:
                logger.warning(f"LLM returned unknown intent '{intent}', defaulting to 'chat'")
                intent = "chat"
                confidence = 0.3

            confidence = min(max(confidence, 0.0), 1.0)
            logger.info(f"LLM fallback: intent={intent}, confidence={confidence:.2f}")
            return intent, confidence, "slow"

        except Exception as e:
            logger.error(f"LLM fallback classification failed: {e}")
            return "chat", 0.3, "slow"

    @staticmethod
    def _build_prompt(messages: list[dict[str, str]]) -> str:
        """Build a single prompt string from message list."""
        parts: list[str] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        parts.append("Assistant (respond with JSON only):")
        return "\n\n".join(parts)

    @staticmethod
    def _parse_response(text: str) -> dict[str, object]:
        """Extract JSON from LLM response, handling markdown fences."""
        # Try direct JSON parse first
        try:
            return json.loads(text)  # type: ignore[return-value]
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fence
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())  # type: ignore[return-value]
            except json.JSONDecodeError:
                pass

        # Try extracting any JSON object with regex
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))  # type: ignore[return-value]
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse LLM response as JSON: {text[:200]}")
        return {"intent": "chat", "confidence": 0.3}


# ── Unified Router ─────────────────────────────────────────────────

def route(
    query: str, history: list[ChatMessage] | None = None
) -> RoutingOutput:
    """Two-tier routing: fast path first, LLM fallback if confidence < threshold.

    Args:
        query: User's query string.
        history: Optional list of ChatMessage objects for context.

    Returns:
        RoutingOutput with intent, confidence, and routing_method.
    """
    fast_router = FastRouter()

    # Try fast path first
    output = fast_router.route(query, history)

    if output.confidence >= FAST_CONFIDENCE_THRESHOLD:
        logger.debug(
            "Fast router: intent=%s, confidence=%.2f, method=%s",
            output.intent, output.confidence, output.routing_method,
        )
        return output

    # Fall back to LLM
    logger.info(
        "Fast router confidence %.2f < %.2f, using LLM fallback",
        output.confidence, FAST_CONFIDENCE_THRESHOLD,
    )
    fallback = LLMFallback()
    intent, confidence, method = fallback.classify(query, history)

    return RoutingOutput(
        intent=intent,
        confidence=confidence,
        routing_method=method,
    )
