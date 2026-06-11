"""Tests for Knowledge RAG — KnowledgeStore + chat_node injection."""
import os
import sys
import pytest

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestKnowledgeStore:
    """Test KnowledgeStore indexing and search."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        """Create temp docs dir and KnowledgeStore for each test."""
        self.tmp_docs = tmp_path / "docs"
        self.tmp_docs.mkdir()
        # Write test documents
        (self.tmp_docs / "return_policy.md").write_text(
            "# 退货政策\n\n## 退款时效\n\n退款将在3个工作日内处理。\n\n## 退货运费\n\n质量问题由平台承担运费。\n",
            encoding="utf-8",
        )
        (self.tmp_docs / "shipping.md").write_text(
            "# 配送说明\n\n## 配送时效\n\n全国主要城市次日达。偏远地区3-5个工作日。\n\n## 运费标准\n\n满99元免运费，不满99元收取8元运费。\n",
            encoding="utf-8",
        )
        # Use temp persist dir
        persist_dir = str(tmp_path / "chroma_test")
        from agents.rag.knowledge_store import KnowledgeStore
        self.store = KnowledgeStore(persist_dir=persist_dir)
        self.store.index_documents(str(self.tmp_docs))

    def test_search_return_policy(self):
        """Search '怎么退货' should return return_policy.md results."""
        results = self.store.search("怎么退货", top_k=2)
        assert len(results) > 0, "Expected at least one result for退货 query"
        sources = [r["metadata"]["source"] for r in results]
        assert "return_policy.md" in sources, f"Expected return_policy.md in {sources}"

    def test_search_shipping(self):
        """Search '运费谁出' should return shipping-related results."""
        results = self.store.search("运费谁出", top_k=3)
        assert len(results) > 0, "Expected results for shipping query"
        # At least one result should have shipping-related content
        found = any("运费" in r["content"] or "shipping" in r["metadata"]["source"]
                    for r in results)
        assert found, f"Expected shipping content in results: {results}"

    def test_irrelevant_query_returns_empty_or_low_score(self):
        """Search '今天天气' should return empty or very low score results."""
        results = self.store.search("今天天气", top_k=2)
        # Either empty, or all scores below 0.55
        if results:
            for r in results:
                assert r["score"] < 0.55, \
                    f"Irrelevant query should have low score, got {r['score']}: {r['content'][:50]}"

    def test_metadata_has_source_and_section(self):
        """All results must have metadata with source and section."""
        results = self.store.search("退款", top_k=3)
        assert len(results) > 0, "Expected results for退款 query"
        for r in results:
            assert "source" in r["metadata"], f"Missing source in {r['metadata']}"
            assert "section" in r["metadata"], f"Missing section in {r['metadata']}"
            assert r["metadata"]["source"], "source should not be empty"
            assert r["metadata"]["section"], "section should not be empty"

    def test_chunk_count(self):
        """After indexing, chunk_count should be > 0."""
        assert self.store.chunk_count > 0, "Expected at least one chunk indexed"
