"""Convert icon.png into a proper multi-size icon.ico for the .exe.

Windows needs a real ICO container with several sizes so the icon stays crisp
in the taskbar, Explorer, and small views. Run this whenever you change
icon.png, then rebuild the exe.
"""
from PIL import Image

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

im = Image.open("icon.png").convert("RGBA")

# Pad to a square so every icon size stays centered and undistorted.
side = max(im.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)

canvas.save("icon.ico", sizes=SIZES)
print("Wrote icon.ico with sizes:", [s[0] for s in SIZES])
