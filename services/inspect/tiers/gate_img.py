"""Cheap pre-VLM gate (SRS Phase 2 item 3, NFR-L5): 64×64 downscale, 64-bin
colour histogram, Sobel edge density, unique-colour count.

ONE-SIDED by contract: it may only fast-pass images it is confident are benign
(natural photos with no text-like structure); it may NEVER block. Anything
text-bearing — charts, tables, screenshots, documents — falls through to T3.
The fast-pass rate is instrumented and exposed on /healthz.
"""

import base64
import io
import math
from dataclasses import dataclass

from PIL import Image

# Tunable on the day against data/images/benign + data/images/gate. Chosen
# conservative: screenshots/charts measure edge density an order of magnitude
# above these.
MAX_EDGE_DENSITY = 0.02     # fraction of pixels with strong Sobel response
MIN_UNIQUE_COLOURS = 1200   # natural photos are colour-rich; UI/charts are flat
MIN_HIST_ENTROPY = 4.0      # bits over a 64-bin luma histogram

fast_pass_count = 0
seen_count = 0


@dataclass
class GateResult:
    fast_pass: bool
    edge_density: float
    unique_colours: int
    hist_entropy: float


def _luma_grid(img):
    g = img.convert("L").resize((64, 64))
    px = list(g.tobytes())
    return [px[r * 64:(r + 1) * 64] for r in range(64)]


def _sobel_edge_density(grid):
    strong = 0
    for y in range(1, 63):
        row_a, row_b, row_c = grid[y - 1], grid[y], grid[y + 1]
        for x in range(1, 63):
            gx = (row_a[x + 1] + 2 * row_b[x + 1] + row_c[x + 1]
                  - row_a[x - 1] - 2 * row_b[x - 1] - row_c[x - 1])
            gy = (row_c[x - 1] + 2 * row_c[x] + row_c[x + 1]
                  - row_a[x - 1] - 2 * row_a[x] - row_a[x + 1])
            if gx * gx + gy * gy > 128 * 128:
                strong += 1
    return strong / (62 * 62)


def _hist_entropy(grid):
    bins = [0] * 64
    for row in grid:
        for v in row:
            bins[v >> 2] += 1
    n = 64 * 64
    return -sum((b / n) * math.log2(b / n) for b in bins if b)


def inspect_image(image_b64: str) -> GateResult:
    global fast_pass_count, seen_count
    img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
    small = img.convert("RGB").resize((64, 64))
    grid = _luma_grid(small)
    edge = _sobel_edge_density(grid)
    uniq = len(small.getcolors(maxcolors=64 * 64))
    ent = _hist_entropy(grid)
    ok = (edge < MAX_EDGE_DENSITY and uniq > MIN_UNIQUE_COLOURS
          and ent > MIN_HIST_ENTROPY)
    seen_count += 1
    if ok:
        fast_pass_count += 1
    return GateResult(ok, edge, uniq, ent)
