"""Fullscreen slide display on the second screen (the TV).

A Tkinter Toplevel that draws the latest slide with a clean, high-contrast
theme tuned for a big screen seen from across a sanctuary: gradient or
background-image backdrop, accent-bar bullets, scripture rendered as a pill so
references pop, auto-fitting + size-adjustable text, and a footer with a
LIVE / REVIEW indicator + slide counter.

OBS captures THIS window via Window Capture and exposes it over NDI.

Themes, text size, and an optional background image are all changeable live from
the control panel.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Status colors are theme-independent (always readable).
LIVE = "#3ddc84"
REVIEW = "#ffb74d"

# Preset themes. Each: gradient top/bottom (rgb tuples) + text/accent/pill/muted.
THEMES = {
    "Midnight": {
        "top": (0x0a, 0x0e, 0x1d), "bottom": (0x16, 0x1d, 0x38),
        "fg": "#f6f8fc", "accent": "#8aa6ff",
        "pill_bg": "#1d2c5c", "pill_fg": "#cfe0ff", "muted": "#7e8bb0",
    },
    "Royal Purple": {
        "top": (0x1a, 0x0b, 0x2e), "bottom": (0x35, 0x16, 0x55),
        "fg": "#f8f4ff", "accent": "#c9a0ff",
        "pill_bg": "#3d1f63", "pill_fg": "#e6d4ff", "muted": "#9b86c0",
    },
    "Deep Teal": {
        "top": (0x05, 0x1f, 0x21), "bottom": (0x0c, 0x3a, 0x3d),
        "fg": "#f0fbfa", "accent": "#4fd6c4",
        "pill_bg": "#0f4a4a", "pill_fg": "#c8f5ef", "muted": "#6fa6a0",
    },
    "Warm Gold": {
        "top": (0x14, 0x10, 0x08), "bottom": (0x2c, 0x21, 0x0d),
        "fg": "#fff9ec", "accent": "#f3c563",
        "pill_bg": "#4a3a14", "pill_fg": "#ffe9b8", "muted": "#b39a6a",
    },
    "Crimson": {
        "top": (0x1f, 0x07, 0x0a), "bottom": (0x49, 0x12, 0x18),
        "fg": "#fff2f3", "accent": "#ff8a93",
        "pill_bg": "#5e1820", "pill_fg": "#ffd2d6", "muted": "#c08a8e",
    },
    "Pure Light": {
        "top": (0xf7, 0xf8, 0xfb), "bottom": (0xe7, 0xeb, 0xf3),
        "fg": "#16203a", "accent": "#3a5bd6",
        "pill_bg": "#dce6ff", "pill_fg": "#1c2f73", "muted": "#6b7591",
    },
}
DEFAULT_THEME = "Midnight"


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % rgb


def _lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


class SlideWindow:
    def __init__(self, tk_root, screen_index: int = 1, church_name: str = "",
                 theme: str = DEFAULT_THEME, font_scale: float = 1.0,
                 background_image: str = "", logo_image: str = ""):
        import tkinter as tk

        self._tk = tk
        self._church = church_name
        self._screen_index = screen_index
        self._fullscreen = False
        self._on_prev = None
        self._on_next = None

        self._theme = THEMES.get(theme, THEMES[DEFAULT_THEME])
        self._font_scale = float(font_scale) if font_scale else 1.0
        self._bg_pil = None
        self._bg_tk = None  # keep a ref so Tk doesn't GC the image
        self._blank = False
        self._logo_pil = None
        self._logo_tk = None

        self._win = tk.Toplevel(tk_root)
        self._win.configure(bg=_hex(self._theme["top"]))
        self._win.title("Sermon Summary  (F = fullscreen, ←/→ = navigate, Esc = exit)")
        self._win.geometry("1000x620+80+80")

        self._ff = self._resolve_font_family()
        self._canvas = tk.Canvas(self._win, bg=_hex(self._theme["top"]), highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        self._win.bind("<f>", lambda e: self.toggle_fullscreen())
        self._win.bind("<F11>", lambda e: self.toggle_fullscreen())
        self._win.bind("<Escape>", lambda e: self.set_fullscreen(False))
        self._win.bind("<Left>", lambda e: self._on_prev and self._on_prev())
        self._win.bind("<Right>", lambda e: self._on_next and self._on_next())
        self._win.bind("<Configure>", lambda e: self._redraw())

        self._state = None  # (slide, index, total, live)
        if background_image:
            try:
                self.set_background_image(background_image)
            except Exception as e:  # noqa: BLE001
                log.warning("could not load background image: %s", e)
        if logo_image:
            try:
                self.set_logo(logo_image)
            except Exception as e:  # noqa: BLE001
                log.warning("could not load logo image: %s", e)
        self._win.after(80, self._draw_placeholder)

    def _resolve_font_family(self) -> str:
        """Pick the best clean sans-serif available on this OS (Mac: Helvetica
        Neue, Windows: Segoe UI, Linux: DejaVu/Arial)."""
        try:
            import tkinter.font as tkfont
            available = set(tkfont.families(self._win))
        except Exception:  # noqa: BLE001
            return "Helvetica"
        for fam in ("Helvetica Neue", "Segoe UI", "Helvetica", "Arial", "DejaVu Sans"):
            if fam in available:
                return fam
        return "Helvetica"

    # --- public API --------------------------------------------------------
    def bind_nav(self, on_prev, on_next) -> None:
        self._on_prev = on_prev
        self._on_next = on_next

    def render(self, slide, index: int, total: int, live: bool) -> None:
        self._state = (slide, index, total, live)
        self._win.after(0, self._redraw)

    def set_church_name(self, name: str) -> None:
        self._church = name or ""
        self._redraw()

    def set_blank(self, on: bool) -> None:
        """Blank the screen (show only background + logo) without stopping the
        service. Toggle off to return to the live slide."""
        self._blank = on
        self._redraw()

    def is_blank(self) -> bool:
        return self._blank

    def set_logo(self, path: str) -> None:
        """Set a logo shown centered on the blank screen. Raises if Pillow is
        missing or the file can't be read."""
        from PIL import Image  # raises ImportError -> caller surfaces it

        self._logo_pil = Image.open(path).convert("RGBA")
        self._redraw()

    def clear_logo(self) -> None:
        self._logo_pil = None
        self._logo_tk = None
        self._redraw()

    def set_theme(self, name: str) -> None:
        self._theme = THEMES.get(name, self._theme)
        self._canvas.configure(bg=_hex(self._theme["top"]))
        self._redraw()

    def set_font_scale(self, scale: float) -> None:
        self._font_scale = max(0.5, min(2.5, float(scale)))
        self._redraw()

    def set_background_image(self, path: str) -> None:
        """Load an image to use as the slide backdrop. Raises if Pillow is
        missing or the file can't be read."""
        from PIL import Image  # raises ImportError -> caller surfaces it

        self._bg_pil = Image.open(path).convert("RGB")
        self._redraw()

    def clear_background_image(self) -> None:
        self._bg_pil = None
        self._bg_tk = None
        self._redraw()

    def set_fullscreen(self, on: bool) -> None:
        self._fullscreen = on
        try:
            self._win.attributes("-fullscreen", on)
        except Exception as e:  # noqa: BLE001
            log.debug("fullscreen toggle failed: %s", e)
        self._win.after(60, self._redraw)

    def toggle_fullscreen(self) -> None:
        self.set_fullscreen(not self._fullscreen)

    # --- drawing -----------------------------------------------------------
    def _dims(self):
        w = self._win.winfo_width() or 1000
        h = self._win.winfo_height() or 620
        return max(w, 320), max(h, 240)

    def _draw_background(self, w, h):
        c = self._canvas
        if self._bg_pil is not None:
            try:
                self._bg_tk = self._cover_image(self._bg_pil, w, h)
                c.create_image(0, 0, anchor="nw", image=self._bg_tk)
                c.create_rectangle(0, 0, w, max(4, int(h * 0.006)),
                                  fill=self._theme["accent"], width=0)
                return
            except Exception as e:  # noqa: BLE001
                log.warning("background image render failed, using gradient: %s", e)
        self._draw_gradient(w, h)

    def _cover_image(self, pil, w, h):
        """Resize+center-crop to fill (w,h), then darken for text legibility."""
        from PIL import Image, ImageTk

        iw, ih = pil.size
        scale = max(w / iw, h / ih)
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        img = pil.resize((nw, nh))
        x, y = (nw - w) // 2, (nh - h) // 2
        img = img.crop((x, y, x + w, y + h))
        # Dark scrim so white text stays readable over any photo. Light themes
        # get a lighter scrim with dark text already, so darken less.
        amount = 0.30 if self._theme["fg"].lower() in ("#16203a",) else 0.50
        overlay = Image.new("RGB", (w, h), (0, 0, 0))
        img = Image.blend(img, overlay, amount)
        return ImageTk.PhotoImage(img)

    def _draw_gradient(self, w, h):
        c = self._canvas
        steps = 64
        band = h / steps
        for i in range(steps):
            color = _hex(_lerp(self._theme["top"], self._theme["bottom"], i / (steps - 1)))
            c.create_rectangle(0, int(i * band), w, int((i + 1) * band) + 1,
                               fill=color, width=0)
        c.create_rectangle(0, 0, w, max(4, int(h * 0.006)),
                          fill=self._theme["accent"], width=0)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        c = self._canvas
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return c.create_polygon(pts, smooth=True, **kw)

    def _redraw(self):
        if self._blank:
            self._draw_blank()
            return
        if self._state is None:
            self._draw_placeholder()
            return
        slide, index, total, live = self._state
        if not getattr(slide, "points", None):
            self._draw_placeholder()
            return
        c = self._canvas
        c.delete("all")
        w, h = self._dims()
        self._draw_background(w, h)
        self._draw_header(w, h)
        self._draw_points(w, h, slide.points)
        self._draw_footer(w, h, index, total, live)

    def _fs(self, px):
        """Apply the operator's text-size multiplier."""
        return max(12, int(px * self._font_scale))

    def _draw_header(self, w, h):
        if self._church:
            self._canvas.create_text(
                int(w * 0.06), int(h * 0.075), anchor="w", fill=self._theme["accent"],
                font=(self._ff, self._fs(int(h * 0.040)), "bold"),
                text=self._church.upper(),
            )

    def _draw_points(self, w, h, points):
        """Flow layout: measure each point's real height (with wrapping), place
        its scripture pill directly beneath it, stack with gaps, and shrink the
        font until the whole block fits the available height. Nothing overlaps
        regardless of text size or line wrapping."""
        c = self._canvas
        n = len(points)
        top = h * 0.17
        bottom = h * 0.90
        avail = bottom - top
        left = int(w * 0.08)
        bar_w = max(5, int(w * 0.006))
        text_x = left + int(w * 0.04)
        wrap = int(w * 0.80)

        base = {1: 0.10, 2: 0.088, 3: 0.076, 4: 0.066, 5: 0.058, 6: 0.05}
        font_px = self._fs(int(h * base.get(n, 0.045)))

        # Shrink-to-fit: re-measure the stacked block until it fits vertically.
        layout, total = self._measure_points(points, font_px, wrap)
        while total > avail and font_px > 14:
            font_px = max(14, int(font_px * 0.92))
            layout, total = self._measure_points(points, font_px, wrap)

        y = top + max(0, (avail - total) / 2)  # vertically center the block
        for item in layout:
            self._round_rect(left, y, left + bar_w, y + item["text_h"],
                            int(bar_w / 2), fill=self._theme["accent"], width=0)
            c.create_text(text_x, y, anchor="nw", fill=self._theme["fg"],
                          font=(self._ff, font_px), text=item["text"], width=wrap)
            yy = y + item["text_h"]
            if item["ref"]:
                yy += item["gap_pill"]
                self._draw_pill(text_x, yy, item["ref"], item["ref_px"])
                yy += item["pill_h"]
            y = yy + item["gap_after"]

    def _measure_points(self, points, font_px, wrap):
        """Compute per-point heights and the total stack height for a font size."""
        ref_px = max(13, int(font_px * 0.48))
        gap_pill = int(font_px * 0.30)
        gap_after = int(font_px * 0.55)
        layout = []
        total = 0.0
        for i, pt in enumerate(points):
            text_h = self._measure_text(pt.text, font_px, wrap)
            ref = pt.scripture or ""
            pill_h = self._pill_height(ref, ref_px) if ref else 0
            block = text_h + ((gap_pill + pill_h) if ref else 0)
            after = gap_after if i < len(points) - 1 else 0
            layout.append({
                "text": pt.text, "ref": ref, "text_h": text_h, "pill_h": pill_h,
                "ref_px": ref_px, "gap_pill": gap_pill, "gap_after": after,
            })
            total += block + after
        return layout, total

    def _measure_text(self, text, font_px, wrap):
        c = self._canvas
        tid = c.create_text(-10000, -10000, text=text, anchor="nw", width=wrap,
                            font=(self._ff, font_px))
        bbox = c.bbox(tid)
        c.delete(tid)
        return (bbox[3] - bbox[1]) if bbox else font_px

    def _pill_height(self, text, ref_px):
        pad_y = int(ref_px * 0.35)
        th = self._measure_text(text, ref_px, 100000)
        return th + 2 * pad_y

    def _draw_pill(self, x, y_top, text, ref_px):
        """Draw a scripture pill with its top-left at (x, y_top)."""
        c = self._canvas
        pad_x = int(ref_px * 0.7)
        pad_y = int(ref_px * 0.35)
        tid = c.create_text(-10000, -10000, text=text, anchor="nw",
                            font=(self._ff, ref_px, "bold"))
        bbox = c.bbox(tid)
        c.delete(tid)
        tw = (bbox[2] - bbox[0]) if bbox else ref_px * len(text) // 2
        th = (bbox[3] - bbox[1]) if bbox else ref_px
        self._round_rect(x, y_top, x + tw + pad_x * 2, y_top + th + pad_y * 2,
                        int((th + pad_y * 2) * 0.42), fill=self._theme["pill_bg"], width=0)
        c.create_text(x + pad_x, y_top + pad_y, anchor="nw", fill=self._theme["pill_fg"],
                      font=(self._ff, ref_px, "bold"), text=text)

    def _draw_footer(self, w, h, index, total, live):
        c = self._canvas
        y = int(h * 0.95)
        dot = max(6, int(h * 0.012))
        x = int(w * 0.06)
        c.create_oval(x, y - dot, x + dot * 2, y + dot,
                      fill=(LIVE if live else REVIEW), width=0)
        c.create_text(x + dot * 3, y, anchor="w", fill=(LIVE if live else REVIEW),
                      font=(self._ff, max(13, int(h * 0.022)), "bold"),
                      text=("LIVE" if live else "REVIEW"))
        if total > 1:
            c.create_text(int(w * 0.94), y, anchor="e", fill=self._theme["muted"],
                          font=(self._ff, max(13, int(h * 0.022))),
                          text=f"Slide {index + 1} of {total}")

    def _draw_blank(self):
        c = self._canvas
        c.delete("all")
        w, h = self._dims()
        self._draw_background(w, h)
        if self._logo_pil is not None:
            try:
                from PIL import ImageTk
                lw, lh = self._logo_pil.size
                scale = min((w * 0.5) / lw, (h * 0.5) / lh)
                resized = self._logo_pil.resize((max(1, int(lw * scale)),
                                                 max(1, int(lh * scale))))
                self._logo_tk = ImageTk.PhotoImage(resized)
                c.create_image(w // 2, h // 2, image=self._logo_tk)
            except Exception as e:  # noqa: BLE001
                log.warning("logo render failed: %s", e)

    def _draw_placeholder(self):
        c = self._canvas
        c.delete("all")
        w, h = self._dims()
        self._draw_background(w, h)
        self._draw_header(w, h)
        # Small, unobtrusive footer note instead of a large center message —
        # the control panel's audio meter already shows that input is live.
        c.create_text(int(w * 0.06), int(h * 0.95), anchor="w", fill=self._theme["muted"],
                      font=(self._ff, max(13, int(h * 0.022))),
                      text="Listening to the message…")

    # Back-compat: old callers used update_slide(slide).
    def update_slide(self, slide) -> None:
        self.render(slide, index=0, total=1, live=True)
