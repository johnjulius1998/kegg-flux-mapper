"""
Dash layout and callbacks for the KEGG Flux Mapper.

`build_layout()` returns the page; `register_callbacks(app)` wires behaviour.  Heavy
state lives in the analysis LRU cache (analysis.py); the browser only holds cache keys.
Visual styling lives in assets/style.css; light/dark switching in assets/theme.js.
"""

from .callbacks import register_callbacks
from .layout import build_layout

__all__ = ["build_layout", "register_callbacks"]
