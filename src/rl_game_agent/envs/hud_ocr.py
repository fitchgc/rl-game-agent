"""Template OCR for the ruggrogue HUD (fixed pixel font, 1280x800 viewport).

Reuses the proven approach from `.scratch/ruggrogue-v1/probes/b2_probe.py`:
glyph cells are split by column projection and matched against binarized
digit templates. A field is `certain` only if every cell matches within
tolerance; otherwise it is `uncertain` and callers must not use the value.

Templates ship as package data (extracted from real screenshots).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PIL import Image

# Value regions: (x0, x1, y0, y1) per field, measured on 1280x800 canvas shots.
FIELDS: dict[str, tuple[int, int, int, int]] = {
    "Level": (1100, 1130, 13, 27),
    "Experience": (1100, 1130, 28, 41),
    "Health": (1100, 1160, 41, 55),  # "30/30" incl. slash
    "Depth": (1100, 1130, 97, 111),
    "Turn": (1100, 1130, 112, 125),
}

# Label column used for HUD-presence detection (phase classification).
LABEL_REGION = (1000, 1100, 0, 130)
LABEL_BRIGHT_PIXELS = 200

TPL_SIZE = (12, 18)
MATCH_TOL = 0.18  # max mean-abs-diff for a certain match (b2-calibrated)


def _template_dir() -> Path:
    return files("rl_game_agent.envs.data.templates")


def load_templates() -> dict[str, Image.Image]:
    tpls: dict[str, Image.Image] = {}
    for p in sorted(_template_dir().glob("*.png")):
        tpls[p.stem] = Image.open(p).convert("L")
    return tpls


def binarize(im: Image.Image) -> Image.Image:
    return im.convert("L").point(lambda v: 255 if v > 90 else 0)


def cells_of(region: Image.Image) -> list[Image.Image]:
    """Split a value region into glyph cells via column projection."""
    g = binarize(region)
    px = g.load()
    w, h = g.size
    assert px is not None
    cols = [sum(1 for y in range(h) if px[x, y] > 128) for x in range(w)]
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, c in enumerate(cols):
        if c > 0 and start is None:
            start = i
        if c == 0 and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, w))
    out = []
    for x0, x1 in runs:
        ys = [y for y in range(h) if any(px[x, y] > 128 for x in range(x0, x1))]
        if not ys:
            continue
        out.append(g.crop((x0, min(ys), x1, max(ys) + 1)))
    return out


def match_cell(cell: Image.Image, tpls: dict[str, Image.Image]) -> tuple[str | None, float]:
    c = cell.resize(TPL_SIZE, Image.LANCZOS).convert("L")
    best: str | None = None
    best_d = 1e9
    for name, t in tpls.items():
        diff = sum(abs(a - b) for a, b in zip(c.tobytes(), t.tobytes())) / (
            255 * TPL_SIZE[0] * TPL_SIZE[1]
        )
        if diff < best_d:
            best, best_d = name, diff
    if best_d > MATCH_TOL:
        return None, best_d
    return best, best_d


class HudReader:
    """Reads HUD fields from a canvas screenshot with certain/uncertain flags."""

    def __init__(self) -> None:
        self.templates = load_templates()
        if not self.templates:
            raise RuntimeError("no OCR digit templates found in package data")

    def read_field(self, img: Image.Image, field: str) -> tuple[str, bool]:
        """Return (value, certain) for one HUD field."""
        x0, x1, y0, y1 = FIELDS[field]
        region = img.crop((x0, y0, x1, y1))
        chars: list[str] = []
        certain = True
        for cell in cells_of(region):
            name, _ = match_cell(cell, self.templates)
            if name is None:
                certain = False
                chars.append("?")
            else:
                chars.append("/" if name == "slash" else name)
        value = "".join(chars)
        if field == "Health" and "/" not in value:
            certain = False
        if not chars:
            certain = False
        return value, certain

    def read_hud(self, img: Image.Image) -> dict[str, dict]:
        """Return {field: {"value": str, "certain": bool}} for all fields."""
        return {f: {"value": v, "certain": c} for f in FIELDS for v, c in [self.read_field(img, f)]}

    def hud_labels_present(self, img: Image.Image) -> bool:
        """Heuristic: right-side HUD label column contains text pixels.

        True on the dungeon screen; false on title / game-over screens.
        Used for phase classification (never for reward/observation).
        """
        x0, x1, y0, y1 = LABEL_REGION
        region = img.crop((x0, y0, x1, y1)).convert("L")
        bright = sum(1 for v in region.tobytes() if v > 90)
        return bright > LABEL_BRIGHT_PIXELS
