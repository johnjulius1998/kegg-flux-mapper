"""
KEGG REST access with on-disk caching.

Everything here is organism-independent: reference pathways (map#####), the global
reaction→pathway and EC→reaction link tables, and per-pathway KGML coordinates plus
the static PNG map.  Bodies are cached under kegg_cache/ so each is fetched once.
KEGG images are used unmodified as a background layer (KEGG terms, non-commercial);
the flux overlay is a separate layer drawn on top.
"""

import struct
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .cache import LRUCache
from .config import KEGG_CACHE, KEGG_REST

# Module-level memo for the global tables (distinct from per-analysis results).
_globals: dict = {}
_globals_lock = threading.Lock()

_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))))


# ── Low-level cached GET ──────────────────────────────────────────────────────────

def kegg_get(rest_path: str, fname: str, binary: bool = False):
    """
    GET {KEGG_REST}/{rest_path}, caching the body under kegg_cache/<fname>.
    Empty bodies (KEGG answers 200 + "" for missing entries) are treated as a
    miss: not cached, and raised as ValueError so callers can fall back.
    """
    cache_file = KEGG_CACHE / fname
    if cache_file.exists() and cache_file.stat().st_size > 0:
        return cache_file.read_bytes() if binary else cache_file.read_text()

    r = _session.get(f"{KEGG_REST}/{rest_path}", timeout=30)
    r.raise_for_status()
    body = r.content if binary else r.text
    if not body or (not binary and not body.strip()):
        raise ValueError(f"KEGG returned an empty body for {rest_path}")

    cache_file.write_bytes(body) if binary else cache_file.write_text(body)
    return body


# ── Global link tables ─────────────────────────────────────────────────────────────

def pathway_index() -> dict:
    """
    {map_id: {"name": str, "reactions": set(R-numbers)}} for reference pathways
    that contain reactions.  Sourced from list/pathway and link/pathway/rn.
    """
    with _globals_lock:
        if "pathway_index" not in _globals:
            _globals["pathway_index"] = _load_pathway_index()
        return _globals["pathway_index"]


def _load_pathway_index() -> dict:
    names = {}
    for line in kegg_get("list/pathway", "list_pathway.txt").splitlines():
        if "\t" in line:
            pid, name = line.split("\t", 1)
            names[pid.strip()] = name.strip()

    rxn_sets: dict = {}
    for line in kegg_get("link/pathway/rn", "link_pathway_rn.txt").splitlines():
        if "\t" not in line:
            continue
        r, p = line.split("\t", 1)
        p = p.replace("path:", "").strip()
        if p.startswith("map"):
            rxn_sets.setdefault(p, set()).add(r.replace("rn:", "").strip())

    return {pid: {"name": names.get(pid, pid), "reactions": rs}
            for pid, rs in rxn_sets.items() if rs}


def ec_to_reactions() -> dict:
    """{EC number: set(R-numbers)} from link/reaction/ec."""
    with _globals_lock:
        if "ec2rn" not in _globals:
            _globals["ec2rn"] = _load_ec_to_reactions()
        return _globals["ec2rn"]


def _load_ec_to_reactions() -> dict:
    out: dict = {}
    for line in kegg_get("link/reaction/ec", "link_reaction_ec.txt").splitlines():
        if "\t" not in line:
            continue
        ec, r = line.split("\t", 1)
        ec = ec.replace("ec:", "").strip()
        r = r.replace("rn:", "").strip()
        if ec and r:
            out.setdefault(ec, set()).add(r)
    return out


def pathway_names() -> dict:
    return {pid: info["name"] for pid, info in pathway_index().items()}


# ── Per-pathway drawable map (coordinates + image) ────────────────────────────────

@dataclass(frozen=True)
class ReactionBox:
    x: float
    y: float
    w: float
    h: float
    reactions: frozenset
    label: str


@dataclass(frozen=True)
class PathwayMap:
    available: bool
    boxes: tuple = ()
    png: bytes = b""
    width: int = 0
    height: int = 0


_maps: LRUCache[PathwayMap] = LRUCache(48)


def pathway_map(map_id: str) -> PathwayMap:
    """
    Fetch the 'ko####' KGML (enzyme-box coordinates + R-numbers) and the matching
    PNG for a reference pathway.  Returns PathwayMap(available=False) when KEGG has
    no drawable map.  Parsed maps are memoised (they are immutable).
    """
    return _maps.get_or_compute(map_id, lambda: _load_pathway_map(map_id))


def _load_pathway_map(map_id: str) -> PathwayMap:
    ko_id = "ko" + map_id[3:]
    try:
        kgml = kegg_get(f"get/{ko_id}/kgml", f"kgml_{ko_id}.xml")
        root = ET.fromstring(kgml)
    except (requests.HTTPError, ValueError, ET.ParseError):
        return PathwayMap(available=False)

    boxes = []
    for entry in root.findall("entry"):
        if entry.get("type") != "ortholog" or not entry.get("reaction"):
            continue
        g = entry.find("graphics")
        if g is None or g.get("x") is None or g.get("type") != "rectangle":
            continue
        boxes.append(ReactionBox(
            x=float(g.get("x")), y=float(g.get("y")),
            w=float(g.get("width", 46)), h=float(g.get("height", 17)),
            reactions=frozenset(x.replace("rn:", "") for x in entry.get("reaction").split()),
            label=(g.get("name") or "").split(",")[0],
        ))

    try:
        png = kegg_get(f"get/{ko_id}/image", f"img_{ko_id}.png", binary=True)
        w, h = png_size(png)
    except (requests.HTTPError, ValueError):
        return PathwayMap(available=False, boxes=tuple(boxes))
    if w == 0:
        return PathwayMap(available=False, boxes=tuple(boxes))
    return PathwayMap(available=True, boxes=tuple(boxes), png=png, width=w, height=h)


def png_size(data: bytes) -> tuple[int, int]:
    """Read (width, height) from a PNG IHDR chunk without external deps."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0
    w, h = struct.unpack(">II", data[16:24])
    return w, h
