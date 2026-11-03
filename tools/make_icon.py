"""Рисует app/icon.ico: скруглённый градиентный квадрат с буквой-«M»-галочкой, как в шапке интерфейса."""
import os

from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S))
px = img.load()
for y in range(S):
    for x in range(S):
        k = (x + y) / (2 * S)
        px[x, y] = (int(139 + (34 - 139) * k), int(108 + (211 - 108) * k), int(255 + (238 - 255) * k), 255)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * .28), fill=255)
img.putalpha(mask)
d = ImageDraw.Draw(img)
u = S / 32
pts = [(9 * u, 21 * u), (9 * u, 11 * u), (16 * u, 17 * u), (23 * u, 11 * u), (23 * u, 21 * u)]
d.line(pts, fill="white", width=int(2.6 * u), joint="curve")
for p in (pts[0], pts[-1], pts[1], pts[3]):
    r = 1.3 * u
    d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill="white")
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "icon.ico")
img.save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(out)
