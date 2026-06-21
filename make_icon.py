"""Build icon.ico for the .exe.

Composites the (white, transparent) Omnivert mark onto a dark rounded tile so
the icon stays visible on any background (taskbar, light Explorer, etc.), then
exports a proper multi-size ICO. Run after changing the source art, then rebuild.
"""
from PIL import Image, ImageDraw
import os

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
S = 1024                      # supersample canvas for smooth corners
TILE_COLOR = (26, 26, 31, 255)  # #1a1a1f dark tile
RADIUS = int(S * 0.23)        # rounded-square corner radius
MARK_FRACTION = 0.62          # how much of the tile the mark fills

# Source art for the mark.
SRC = "ico_test.png" if os.path.exists("ico_test.png") else "icon.png"
mark = Image.open(SRC).convert("RGBA")

# Trim transparent margins so the mark is sized by its actual content.
bbox = mark.getbbox()
if bbox:
    mark = mark.crop(bbox)

# Scale the mark to fit centered within the target area.
target = int(S * MARK_FRACTION)
w, h = mark.size
scale = min(target / w, target / h)
mark = mark.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

# Dark rounded tile.
tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(tile).rounded_rectangle([0, 0, S - 1, S - 1], radius=RADIUS,
                                       fill=TILE_COLOR)

# Center the mark on the tile.
ox, oy = (S - mark.width) // 2, (S - mark.height) // 2
tile.alpha_composite(mark, (ox, oy))

tile.save("icon.ico", sizes=SIZES)
tile.resize((512, 512), Image.LANCZOS).save("icon_preview.png")
print(f"Wrote icon.ico from {SRC} on a dark rounded tile; sizes:",
      [s[0] for s in SIZES])
