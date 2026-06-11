from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agents'
    verbose_name = 'AI Agents'

    def ready(self):
        """Pre-load FAISS index on startup so first search is instant."""
        from pathlib import Path
        index_path = Path(__file__).resolve().parent.parent / 'faiss_index' / 'products.index'
        if index_path.exists():
            from agents.graph.rag.retriever import get_retriever
            get_retriever().load_index(str(index_path))
