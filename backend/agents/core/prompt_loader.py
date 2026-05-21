"""Prompt template loader with versioning and layered loading.

Loads Jinja2 templates from disk.  Templates live in:
  - agents/customer_service/prompts/  (agent-specific)
  - agents/templates/prompts/         (shared across agents)

Layered prompt strategy (architecture: 3-tier token saving):
  Layer 'base' :  ~200 token system prompt, always loaded
  Layer 'full' :  all rules + examples, injected on demand
  Templates use `{% if layer == 'full' %}` to guard detailed sections.

Versioning:
  Filenames:  {name}.v{version}.jinja  (e.g. system.v1.jinja)
  Or:         {name}.jinja             (latest)
  The version string is logged to AgentLog for A/B testing analysis.

Usage:
    loader = PromptLoader()
    prompt = loader.render('system', layer='base')        # minimal
    prompt = loader.render('system', layer='full', product_count=5300)
"""

import os
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, Template


# ── Default template directories ────────────────────────────────
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent  # backend/agents/ (the agents package)

DEFAULT_SEARCH_PATHS = [
    str(_PROJECT_ROOT / 'templates' / 'prompts'),
    str(_PROJECT_ROOT / 'customer_service' / 'prompts'),
    str(_PROJECT_ROOT / 'ops' / 'prompts'),
    str(_PROJECT_ROOT / 'recommend' / 'prompts'),
]


class PromptLoader:
    """Load, cache, and render Jinja2 prompt templates.

    Templates use `{% if layer == 'full' %}` to control detail level.
    The render() method auto-injects `layer` into template variables.
    """

    def __init__(self, search_paths: Optional[list[str]] = None):
        paths = search_paths or DEFAULT_SEARCH_PATHS
        self._search_paths = [p for p in paths if os.path.isdir(p)]
        self._env = Environment(
            loader=FileSystemLoader(self._search_paths),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # ── public API ──────────────────────────────────────────────

    def render(self, name: str, layer: str = 'base',
               version: Optional[str] = None, **variables) -> str:
        """Render a prompt template.

        Args:
            name:      template base name (e.g. 'system', 'order_query')
            layer:     'base' (精简版) or 'full' (完整版).
                       Injected into template as `{{ layer }}`.
            version:   version tag (e.g. 'v1').  None → latest.
            **variables: additional Jinja2 template variables

        Returns:
            Rendered prompt string.
        """
        template_name = self._resolve_filename(name, version)
        tmpl = self._load_template(template_name)
        return tmpl.render(layer=layer, **variables)

    def load_raw(self, name: str, version: Optional[str] = None) -> str:
        """Load a template as raw text (no rendering). Useful for inspection."""
        template_name = self._resolve_filename(name, version)
        tmpl = self._load_template(template_name)
        # Jinja2 doesn't expose raw source easily — render with empty vars
        return tmpl.render(layer='base')

    def get_version(self, version: Optional[str] = None) -> str:
        """Return the effective version string for AgentLog prompt_version."""
        return version or 'latest'

    def list_templates(self) -> list[str]:
        """List all available template filenames."""
        return self._env.list_templates()

    def exists(self, name: str, version: Optional[str] = None) -> bool:
        """Check if a template file exists."""
        fname = self._resolve_filename(name, version)
        try:
            self._load_template(fname)
            return True
        except TemplateNotFound:
            return False

    # ── internal ────────────────────────────────────────────────

    def _resolve_filename(self, name: str, version: Optional[str]) -> str:
        """Resolve 'system' + version='v1' → 'system.v1.jinja'."""
        if version:
            return f'{name}.{version}.jinja'
        return f'{name}.jinja'

    def _load_template(self, filename: str) -> Template:
        """Load a template, searching across all configured paths."""
        try:
            return self._env.get_template(filename)
        except TemplateNotFound:
            # Brute-force search across all paths
            for path in self._search_paths:
                full = os.path.join(path, filename)
                if os.path.isfile(full):
                    self._env.loader.searchpath.append(path)
                    return self._env.get_template(filename)
            raise TemplateNotFound(filename)

    def _find_file(self, name: str, version: Optional[str]) -> Optional[str]:
        """Return the full path to a template file, or None."""
        fname = self._resolve_filename(name, version)
        for path in self._search_paths:
            full = os.path.join(path, fname)
            if os.path.isfile(full):
                return full
        return None


# ── Singleton ───────────────────────────────────────────────────

_loader: Optional[PromptLoader] = None


def get_prompt_loader(search_paths: Optional[list[str]] = None) -> PromptLoader:
    """Return the global PromptLoader singleton."""
    global _loader
    if _loader is None:
        _loader = PromptLoader(search_paths)
    return _loader


def reset_prompt_loader() -> None:
    """Reset the singleton (useful for tests)."""
    global _loader
    _loader = None
