"""Renders the social-share preview image for a saved search
(`/s/<id>/og.png`) — a 1200×630 PNG in the vein of Luma's share cards: a
collage of the listing photos vindje.com found, a bottom gradient, and the
wish plus match count overlaid.

This is the one place in the app that needs Pillow (see requirements.txt),
kept out of app.py on purpose to leave that file's other routes dependency-
free — the same reason mcp_server.py lives in its own file. app.py imports
this lazily and degrades to no share image at all if it's unavailable.
"""
import io
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1200, 630
INK = (17, 17, 19)
WHITE = (255, 255, 255)

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
_FONT_CACHE = {}


def _font(name, size):
    key = (name, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(os.path.join(_FONT_DIR, name), size)
    return _FONT_CACHE[key]


def _fetch_image(url, timeout=3.5):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGB")


def _fetch_or_none(url):
    try:
        return _fetch_image(url)
    except Exception:
        return None


def _cover(img, w, h):
    return ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)


def _collage(urls, w, h):
    """Fetch up to 4 listing photos in parallel and tile them to fill w×h,
    falling back to a plain dark canvas if none could be fetched."""
    imgs = []
    if urls:
        with ThreadPoolExecutor(max_workers=len(urls)) as ex:
            futures = [ex.submit(_fetch_or_none, u) for u in urls]
            for fut in futures:
                try:
                    img = fut.result(timeout=6)
                except Exception:
                    img = None
                if img is not None:
                    imgs.append(img)

    canvas = Image.new("RGB", (w, h), INK)
    if not imgs:
        return canvas
    if len(imgs) == 1:
        canvas.paste(_cover(imgs[0], w, h), (0, 0))
    elif len(imgs) == 2:
        half = w // 2
        canvas.paste(_cover(imgs[0], half, h), (0, 0))
        canvas.paste(_cover(imgs[1], w - half, h), (half, 0))
    elif len(imgs) == 3:
        big = int(w * 0.58)
        half_h = h // 2
        canvas.paste(_cover(imgs[0], big, h), (0, 0))
        canvas.paste(_cover(imgs[1], w - big, half_h), (big, 0))
        canvas.paste(_cover(imgs[2], w - big, h - half_h), (big, half_h))
    else:
        half_w, half_h = w // 2, h // 2
        canvas.paste(_cover(imgs[0], half_w, half_h), (0, 0))
        canvas.paste(_cover(imgs[1], w - half_w, half_h), (half_w, 0))
        canvas.paste(_cover(imgs[2], half_w, h - half_h), (0, half_h))
        canvas.paste(_cover(imgs[3], w - half_w, h - half_h), (half_w, half_h))
    return canvas


def _fit_lines(draw, text, font, max_width, max_lines):
    """Word-wrap `text` to at most `max_lines`, ellipsizing the last line
    if it doesn't all fit."""
    words = text.split()
    lines, cur, i = [], "", 0
    while i < len(words) and len(lines) < max_lines:
        trial = f"{cur} {words[i]}".strip()
        if not cur or draw.textlength(trial, font=font) <= max_width:
            cur = trial
            i += 1
        else:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    if i < len(words) and lines:
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = (last + "…") if last else "…"
    return lines


def _search_stats(record):
    """(checked, count, scanned): whether AI filtering ran, how many
    listings it matched (or, without AI, how many were simply found), and
    how many were scanned in total. Mirrors app.search_stats — kept as a
    local copy so this module stays importable without loading app.py."""
    results = record.get("results") or []
    checked = any(l.get("matched") or l.get("rejected") or l.get("unchecked") for l in results)
    count = sum(1 for l in results if l.get("matched")) if checked else len(results)
    scanned = record.get("scanned") or len(results)
    return checked, count, scanned


def render_share_image(record):
    """Render the 1200x630 PNG for a saved search record. May raise (network
    or font errors) — the caller is expected to catch and degrade."""
    wish = str(record.get("wish") or "").strip()
    results = record.get("results") or []
    checked, count, scanned = _search_stats(record)
    highlight = [l for l in results if l.get("matched")] if checked else results

    photo_urls = [l["image"] for l in highlight if l.get("image")][:4]
    if not photo_urls:
        photo_urls = [l["image"] for l in results if l.get("image")][:4]

    img = _collage(photo_urls, W, H).convert("RGBA")

    # Bottom gradient so the headline stays legible over any photo, plus a
    # light overall wash so wildly different listing photos still read as
    # one on-brand card.
    fade_top = int(H * 0.4)
    fade_h = H - fade_top
    gradient = Image.new("L", (1, fade_h))
    for y in range(fade_h):
        gradient.putpixel((0, y), int(235 * (y / fade_h) ** 1.3))
    alpha = gradient.resize((W, fade_h))
    shade = Image.new("RGBA", (W, fade_h), (8, 8, 10, 255))
    shade.putalpha(alpha)
    img.alpha_composite(shade, (0, fade_top))
    img.alpha_composite(Image.new("RGBA", (W, H), (8, 8, 10, 36)))

    draw = ImageDraw.Draw(img)
    pad = 64

    # brand mark, top-left: a small magnifying glass + wordmark
    cx, cy, r = pad + 13, pad + 13, 12
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=4)
    draw.line([cx + r * 0.75, cy + r * 0.75, cx + r * 1.4, cy + r * 1.4], fill=WHITE, width=4)
    draw.text((pad + 48, pad - 2), "vindje.com", font=_font("Outfit-Bold.ttf", 28), fill=WHITE)

    # stat pill, top-right
    if scanned:
        label = f"{count} MATCH{'ES' if count != 1 else ''}" if checked else f"{scanned} FOUND"
        pill_font = _font("Outfit-Bold.ttf", 23)
        tw = draw.textlength(label, font=pill_font)
        pill_w, pill_h = tw + 44, 48
        x1, y1 = W - pad - pill_w, pad - 6
        draw.rounded_rectangle([x1, y1, x1 + pill_w, y1 + pill_h], radius=pill_h / 2, fill=WHITE)
        draw.text((x1 + 22, y1 + 12), label, font=pill_font, fill=INK)

    # headline: the wish, quoted and wrapped to 2 lines
    headline_font = _font("Outfit-Bold.ttf", 50)
    max_w = W - pad * 2
    lines = _fit_lines(draw, f"“{wish}”", headline_font, max_w, 2) if wish else []
    line_h = 60

    sub_font = _font("Outfit-Regular.ttf", 26)
    if checked:
        sub = f"{count} of {scanned} listings matched · AI-filtered on vindje.com"
    else:
        sub = f"{scanned} listings found on Marktplaats · vindje.com"

    y = H - pad - 30 - line_h * max(len(lines), 1)
    for line in lines:
        draw.text((pad, y), line, font=headline_font, fill=WHITE)
        y += line_h
    draw.text((pad, y + 4), sub, font=sub_font, fill=(255, 255, 255, 210))

    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
