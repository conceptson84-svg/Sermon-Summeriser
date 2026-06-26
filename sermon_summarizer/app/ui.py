"""Media-room control panel (primary screen).

A dark, sectioned control surface: service controls, audio device + level meter,
AI provider + API key, display theme/size/background, and a live slide preview
with navigation and PDF export. The fullscreen SlideWindow lives on the second
screen (the TV).

Buttons are built from styled Labels rather than native tk.Button so colors
render consistently across macOS, Windows, and Linux.
"""

from __future__ import annotations

import logging

from .events import ServiceState

log = logging.getLogger(__name__)

# Cohesive dark palette (matches the slide display's Midnight theme).
UI = {
    "bg": "#10141f",
    "panel": "#181d2c",
    "border": "#28304a",
    "fg": "#e8ecf6",
    "muted": "#8a95b2",
    "accent": "#6c8cff",
    "field": "#1f2638",
    "green": "#3ddc84",
    "amber": "#ffb74d",
    "red": "#ff6b6b",
}
FONT = "Helvetica"


def _lighten(hex_color: str, amt: int = 20) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (min(255, c + amt) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class ControlPanel:
    _SIZE_CHOICES = {"Small": 0.8, "Medium": 1.0, "Large": 1.25, "X-Large": 1.5}
    # How often the AI summarizes, and how much recent speech it reads each time.
    _INTERVAL_CHOICES = {"15 sec": 15, "30 sec": 30, "1 min": 60, "2 min": 120, "5 min": 300}
    _WINDOW_CHOICES = {"1 min": 60, "2 min": 120, "5 min": 300, "10 min": 600}

    def __init__(self, controller, slide_window, config, export_dir="exports"):
        import tkinter as tk

        self._tk = tk
        self._controller = controller
        self._slide_window = slide_window
        self._cfg = config
        self._export_dir = export_dir

        self.root = tk.Tk()
        self.root.title("Sermon Summarizer — Control")
        self.root.geometry("600x720")
        self.root.minsize(520, 420)
        self.root.configure(bg=UI["bg"])

        self._status = tk.StringVar(value="Stopped")
        self._capture = None
        self._meter = None
        self._meter_after = None
        self._service_after = None
        self._key_show = False
        self._view_index = None
        self._dev_labels = {}
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_scroll(self):
        """Wrap all controls in a vertically scrollable area so every button is
        reachable even when the window is small / not maximized."""
        tk = self._tk
        from tkinter import ttk

        container = tk.Frame(self.root, bg=UI["bg"])
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=UI["bg"], highlightthickness=0)
        vbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=UI["bg"])
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

        def _wheel(e):
            step = -1 if (getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0) else 1
            canvas.yview_scroll(step, "units")

        canvas.bind_all("<MouseWheel>", _wheel)   # macOS / Windows
        canvas.bind_all("<Button-4>", _wheel)      # Linux scroll up
        canvas.bind_all("<Button-5>", _wheel)      # Linux scroll down
        self._content = inner

    # --- styled widget helpers --------------------------------------------
    def _section(self, title):
        tk = self._tk
        card = tk.Frame(self._content, bg=UI["panel"], highlightbackground=UI["border"],
                        highlightthickness=1)
        card.pack(fill="x", padx=12, pady=(0, 9))
        tk.Label(card, text=title.upper(), bg=UI["panel"], fg=UI["accent"],
                 font=(FONT, 10, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        body = tk.Frame(card, bg=UI["panel"])
        body.pack(fill="x", padx=12, pady=(4, 10))
        return body

    def _btn(self, parent, text, command, kind="default", **pack):
        tk = self._tk
        palette = {
            "primary": (UI["accent"], "#ffffff"),
            "danger": ("#3a2230", UI["red"]),
            "default": (UI["field"], UI["fg"]),
        }
        bg, fg = palette.get(kind, palette["default"])
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=(FONT, 11, "bold"),
                     padx=14, pady=7, cursor="hand2")
        b._base_bg = bg
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg=_lighten(b._base_bg)))
        b.bind("<Leave>", lambda e: b.config(bg=b._base_bg))
        if pack:
            b.pack(**pack)
        return b

    def _label(self, parent, text, **kw):
        tk = self._tk
        kw.setdefault("bg", UI["panel"])
        kw.setdefault("fg", UI["muted"])
        kw.setdefault("font", (FONT, 11))
        return tk.Label(parent, text=text, **kw)

    def _combo(self, parent, values, on_select, width=18):
        from tkinter import ttk
        cb = ttk.Combobox(parent, values=list(values), state="readonly", width=width)
        cb.bind("<<ComboboxSelected>>", lambda e: on_select(cb.get()))
        return cb

    def _style_combos(self):
        from tkinter import ttk

        style = ttk.Style()
        try:
            style.theme_use("clam")  # honors custom colors on all platforms
        except Exception:  # noqa: BLE001
            pass
        style.configure("TCombobox", fieldbackground=UI["field"], background=UI["field"],
                        foreground=UI["fg"], arrowcolor=UI["fg"], bordercolor=UI["border"],
                        relief="flat", padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", UI["field"])],
                  foreground=[("readonly", UI["fg"])],
                  selectbackground=[("readonly", UI["field"])],
                  selectforeground=[("readonly", UI["fg"])])
        # Popup list colors
        self.root.option_add("*TCombobox*Listbox.background", UI["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", UI["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", UI["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def _build(self):
        tk = self._tk
        self._style_combos()
        self._build_scroll()

        # Header
        header = tk.Frame(self._content, bg=UI["bg"])
        header.pack(fill="x", padx=14, pady=(12, 10))
        tk.Label(header, text="Sermon Summarizer", bg=UI["bg"], fg=UI["fg"],
                 font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(header, textvariable=self._status, bg=UI["bg"], fg=UI["muted"],
                 font=(FONT, 11)).pack(anchor="w", pady=(2, 0))

        # Service
        svc = self._section("Service")
        self._btn(svc, "▶ Start", self._start, kind="primary", side="left")
        self._btn(svc, "Pause", self._pause, side="left", padx=6)
        self._btn(svc, "Stop", self._stop, kind="danger", side="left")
        self._btn(svc, "Summarize now", self._summarize_now, side="left", padx=6)

        # Audio
        au = self._section("Audio input")
        row1 = tk.Frame(au, bg=UI["panel"]); row1.pack(fill="x")
        self._dev_cb = self._combo(row1, ["Default input"], self._select_device, width=34)
        self._dev_cb.pack(side="left")
        self._btn(row1, "↻", self._refresh_devices, side="left", padx=6)
        self._refresh_devices()

        row2 = tk.Frame(au, bg=UI["panel"]); row2.pack(fill="x", pady=(8, 0))
        self._test_btn = self._btn(row2, "Test audio", self._toggle_audio_test, side="left")
        self._meter_w, self._meter_h = 220, 18
        self._meter_canvas = tk.Canvas(row2, width=self._meter_w, height=self._meter_h,
                                       bg=UI["field"], highlightthickness=1,
                                       highlightbackground=UI["border"])
        self._meter_canvas.pack(side="left", padx=8)
        self._meter_hint = tk.StringVar(value="")
        self._label(row2, "", textvariable=self._meter_hint).pack(side="left")

        # AI engine
        ai = self._section("AI engine")
        from ..summarize.providers import SUPPORTED_PROVIDERS
        prow = tk.Frame(ai, bg=UI["panel"]); prow.pack(fill="x")
        self._label(prow, "Provider:").pack(side="left")
        self._provider_cb = self._combo(prow, SUPPORTED_PROVIDERS, self._on_provider_change, width=16)
        self._provider_cb.set(self._cfg.provider or "anthropic")
        self._provider_cb.pack(side="left", padx=6)

        krow = tk.Frame(ai, bg=UI["panel"]); krow.pack(fill="x", pady=(8, 0))
        self._label(krow, "API key:").pack(side="left")
        self._key_var = tk.StringVar(value=self._current_provider_key())
        self._key_entry = tk.Entry(krow, textvariable=self._key_var, show="•", width=26,
                                   bg=UI["field"], fg=UI["fg"], insertbackground=UI["fg"],
                                   relief="flat", highlightthickness=1,
                                   highlightbackground=UI["border"])
        self._key_entry.pack(side="left", padx=6, ipady=4)
        self._key_show_btn = self._btn(krow, "Show", self._toggle_key_visibility, side="left")
        self._btn(krow, "Save key", self._save_key, kind="primary", side="left", padx=6)

        # Church name (shows on the slide header and exported PDF).
        ch = self._section("Church")
        crow = tk.Frame(ch, bg=UI["panel"]); crow.pack(fill="x")
        self._label(crow, "Name:").pack(side="left")
        self._church_var = tk.StringVar(value=self._cfg.church_name or "")
        church_entry = tk.Entry(crow, textvariable=self._church_var, width=28,
                                bg=UI["field"], fg=UI["fg"], insertbackground=UI["fg"],
                                relief="flat", highlightthickness=1,
                                highlightbackground=UI["border"])
        church_entry.pack(side="left", padx=6, ipady=4)
        church_entry.bind("<Return>", lambda e: self._apply_church())
        self._btn(crow, "Apply", self._apply_church, kind="primary", side="left")

        # Display
        from ..slides.renderer import THEMES
        disp = self._section("Display")
        drow = tk.Frame(disp, bg=UI["panel"]); drow.pack(fill="x")
        self._label(drow, "Theme:").pack(side="left")
        self._theme_cb = self._combo(drow, THEMES.keys(), self._on_theme_change, width=13)
        self._theme_cb.set(self._cfg.theme or "Midnight")
        self._theme_cb.pack(side="left", padx=(4, 12))
        self._label(drow, "Text size:").pack(side="left")
        self._size_cb = self._combo(drow, self._SIZE_CHOICES.keys(), self._on_size_change, width=10)
        self._size_cb.set(self._scale_label(self._cfg.font_scale))
        self._size_cb.pack(side="left", padx=4)

        brow = tk.Frame(disp, bg=UI["panel"]); brow.pack(fill="x", pady=(8, 0))
        self._btn(brow, "Set background…", self._set_background, side="left")
        self._btn(brow, "Clear", self._clear_background, side="left", padx=6)
        self._btn(brow, "⤢ Fullscreen", self._fullscreen_slide, side="left")

        brow2 = tk.Frame(disp, bg=UI["panel"]); brow2.pack(fill="x", pady=(6, 0))
        self._blank_btn = self._btn(brow2, "⬛ Blank screen", self._toggle_blank,
                                    kind="danger", side="left")
        self._btn(brow2, "Set logo…", self._set_logo, side="left", padx=6)
        self._btn(brow2, "Clear logo", self._clear_logo, side="left")

        # Timing
        tm = self._section("Timing")
        trow = tk.Frame(tm, bg=UI["panel"]); trow.pack(fill="x")
        self._label(trow, "Summarize every:").pack(side="left")
        self._interval_cb = self._combo(trow, self._INTERVAL_CHOICES.keys(),
                                        self._on_interval_change, width=8)
        self._interval_cb.set(self._label_for(self._INTERVAL_CHOICES,
                                              self._cfg.summarize_interval_seconds))
        self._interval_cb.pack(side="left", padx=(4, 12))
        self._label(trow, "Context window:").pack(side="left")
        self._window_cb = self._combo(trow, self._WINDOW_CHOICES.keys(),
                                      self._on_window_change, width=8)
        self._window_cb.set(self._label_for(self._WINDOW_CHOICES,
                                            self._cfg.transcript_window_seconds))
        self._window_cb.pack(side="left", padx=4)

        # Current slide + navigation
        sl = self._section("Current slide")
        self._listbox = tk.Listbox(sl, height=10, font=(FONT, 13), bg=UI["field"],
                                   fg=UI["fg"], selectbackground=UI["accent"],
                                   selectforeground="#ffffff", relief="flat",
                                   highlightthickness=1, highlightbackground=UI["border"],
                                   borderwidth=0)
        self._listbox.pack(fill="x", pady=(0, 8))
        self._listbox.bind("<Double-Button-1>", lambda e: self._edit_selected())

        # Manual point editor: add a new point, or select one + Edit to change it.
        self._edit_index = None
        erow = tk.Frame(sl, bg=UI["panel"]); erow.pack(fill="x")
        self._label(erow, "Point:").pack(side="left")
        self._point_var = tk.StringVar()
        tk.Entry(erow, textvariable=self._point_var, width=24, bg=UI["field"],
                 fg=UI["fg"], insertbackground=UI["fg"], relief="flat",
                 highlightthickness=1, highlightbackground=UI["border"]).pack(
                     side="left", padx=4, ipady=3)
        self._label(erow, "Verse:").pack(side="left")
        self._verse_var = tk.StringVar()
        tk.Entry(erow, textvariable=self._verse_var, width=10, bg=UI["field"],
                 fg=UI["fg"], insertbackground=UI["fg"], relief="flat",
                 highlightthickness=1, highlightbackground=UI["border"]).pack(
                     side="left", padx=4, ipady=3)

        erow2 = tk.Frame(sl, bg=UI["panel"]); erow2.pack(fill="x", pady=(6, 0))
        self._add_btn = self._btn(erow2, "Add point", self._add_or_update_point,
                                  kind="primary", side="left")
        self._btn(erow2, "Edit selected", self._edit_selected, side="left", padx=6)
        self._btn(erow2, "Delete bullet", self._delete_selected, side="left")
        self._btn(erow2, "Clear field", self._clear_point_editor, side="left", padx=6)

        nrow = tk.Frame(sl, bg=UI["panel"]); nrow.pack(fill="x", pady=(8, 0))
        self._btn(nrow, "◀ Prev", self._nav_prev, side="left")
        self._btn(nrow, "Next ▶", self._nav_next, side="left", padx=6)
        self._btn(nrow, "⤓ Live", self._nav_live, side="left")
        self._nav_label = tk.StringVar(value="LIVE")
        tk.Label(nrow, textvariable=self._nav_label, bg=UI["panel"], fg=UI["green"],
                 font=(FONT, 11, "bold")).pack(side="left", padx=10)

        # Export & share
        ex = self._section("Export & share")
        xrow = tk.Frame(ex, bg=UI["panel"]); xrow.pack(fill="x")
        self._btn(xrow, "End Service → PDF", self._end_service, kind="primary", side="left")
        srow = tk.Frame(ex, bg=UI["panel"]); srow.pack(fill="x", pady=(6, 0))
        self._btn(srow, "Copy", self._copy_summary, side="left")
        self._btn(srow, "Save .txt…", self._save_summary_text, side="left", padx=6)
        self._btn(srow, "Email", self._email_summary, side="left")
        self._btn(srow, "WhatsApp", self._whatsapp_summary, side="left", padx=6)

    def _on_close(self):
        try:
            if self._meter is not None:
                self._stop_audio_test()
            self._stop_service_meter()
            self._controller.stop()
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()

    # --- callbacks ---------------------------------------------------------
    def set_status(self, msg: str):
        self.root.after(0, lambda: self._status.set(msg))

    def on_deck_update(self, deck):
        self.root.after(0, lambda: self._on_deck_update_ui(deck))

    def _on_deck_update_ui(self, deck):
        self._refresh(deck)
        if self._view_index is None:
            self._render_view()
        else:
            self.set_status(f"New content on slide {deck.slide_count} — press Live to catch up")

    def _refresh(self, deck):
        self._listbox.delete(0, "end")
        for pt in deck.latest_slide().points:
            label = pt.text + (f"   ({pt.scripture})" if pt.scripture else "")
            self._listbox.insert("end", label)

    # --- slide navigation --------------------------------------------------
    def _nav_prev(self):
        self._navigate(-1)

    def _nav_next(self):
        self._navigate(+1)

    def _nav_live(self):
        self._view_index = None
        self._render_view()

    def _navigate(self, delta):
        deck = self._controller.deck
        total = deck.slide_count
        cur = self._view_index if self._view_index is not None else total - 1
        new = max(0, min(total - 1, cur + delta))
        self._view_index = None if new == total - 1 else new
        self._render_view()

    def _render_view(self):
        deck = self._controller.deck
        total = deck.slide_count
        live = self._view_index is None
        idx = (total - 1) if live else self._view_index
        if total == 0:
            return
        slide = deck.slides[idx]
        self._slide_window.render(slide, index=idx, total=total, live=live)
        self._nav_label.set("LIVE" if live else f"REVIEW {idx + 1}/{total}")

    def _on_provider_change(self, provider: str):
        from ..summarize.summarizer import Summarizer
        from ..summarize.providers import ProviderError

        self._cfg.provider = provider
        self._persist()
        self._key_var.set(self._current_provider_key())
        if not self._cfg.has_key_for_provider():
            self.set_status(f"Enter an API key for '{provider}' below, then Save key")
            return
        try:
            self._controller.set_summarizer(Summarizer.from_config(self._cfg))
            self.set_status(f"Provider set to {provider}")
        except ProviderError as e:
            self.set_status(f"Could not switch to {provider}: {e}")

    # --- API key -----------------------------------------------------------
    def _current_provider_key(self) -> str:
        provider = (self._cfg.provider or "anthropic").lower()
        return getattr(self._cfg, f"{provider}_api_key", "") or self._cfg.api_key or ""

    def _toggle_key_visibility(self):
        self._key_show = not self._key_show
        self._key_entry.config(show="" if self._key_show else "•")
        self._key_show_btn.config(text="Hide" if self._key_show else "Show")

    def _save_key(self):
        from ..summarize.summarizer import Summarizer
        from ..summarize.providers import ProviderError

        provider = (self._cfg.provider or "anthropic").lower()
        value = self._key_var.get().strip()
        setattr(self._cfg, f"{provider}_api_key", value)
        self._persist()
        if not value:
            self.set_status(f"API key cleared for {provider}")
            return
        try:
            self._controller.set_summarizer(Summarizer.from_config(self._cfg))
            self.set_status(f"API key saved for {provider}")
        except ProviderError as e:
            self.set_status(f"Key saved but provider error: {e}")

    # --- audio device picker ----------------------------------------------
    def _refresh_devices(self):
        from ..audio.capture import list_input_devices

        try:
            devices = list_input_devices()
        except Exception as e:  # noqa: BLE001
            devices = []
            log.warning("could not list audio devices: %s", e)

        self._dev_labels = {"Default input": None}
        for d in devices:
            self._dev_labels[f"[{d['index']}] {d['name']}  ({d['channels']}ch)"] = d["index"]

        self._dev_cb["values"] = list(self._dev_labels.keys())
        current = "Default input"
        for label, idx in self._dev_labels.items():
            if idx == self._cfg.audio_device_index:
                current = label
                break
        self._dev_cb.set(current)

    def _select_device(self, label):
        idx = self._dev_labels.get(label)
        self._cfg.audio_device_index = idx
        self._persist()
        if self._capture is not None:
            self._capture.set_device(idx)
        if self._meter is not None:
            self._stop_audio_test()
            self._start_audio_test()
        if self._controller.state is ServiceState.RUNNING:
            self.set_status(f"Input set to {label} — applies after Stop/Start")
        else:
            self.set_status(f"Audio input: {label}")

    # --- audio test meter --------------------------------------------------
    def _toggle_audio_test(self):
        if self._meter is not None:
            self._stop_audio_test()
        else:
            self._start_audio_test()

    def _start_audio_test(self):
        from ..audio.meter import AudioMeter
        from tkinter import messagebox

        if self._controller.state is ServiceState.RUNNING:
            self.set_status("Service is running — the meter already shows live audio")
            return
        try:
            self._meter = AudioMeter(device_index=self._cfg.audio_device_index)
            self._meter.start()
        except Exception as e:  # noqa: BLE001
            self._meter = None
            messagebox.showerror(
                "Audio test failed",
                f"Could not open the audio device.\n\n{e}\n\n"
                f"Run `python run.py --devices` to check the device index in config.json.",
            )
            return
        self._test_btn.config(text="Stop test")
        self._meter_hint.set("Speak / play into the mixer…")
        self._poll_meter()

    def _stop_audio_test(self):
        if self._meter_after is not None:
            self.root.after_cancel(self._meter_after)
            self._meter_after = None
        if self._meter is not None:
            self._meter.stop()
            self._meter = None
        self._test_btn.config(text="Test audio")
        self._meter_hint.set("")
        self._draw_meter(0.0)

    def _poll_meter(self):
        if self._meter is None:
            return
        level = self._meter.level()
        self._draw_meter(level)
        self._meter_hint.set("Signal OK" if level > 0.02 else "No signal — check the mixer")
        self._meter_after = self.root.after(50, self._poll_meter)

    def _draw_meter(self, level):
        c = self._meter_canvas
        c.delete("all")
        w, h = self._meter_w, self._meter_h
        fill_w = int(max(0.0, min(1.0, level)) * w)
        color = UI["green"] if level < 0.7 else (UI["amber"] if level < 0.9 else UI["red"])
        if fill_w > 0:
            c.create_rectangle(0, 0, fill_w, h, fill=color, width=0)
        for frac in (0.7, 0.9):
            x = int(frac * w)
            c.create_line(x, 0, x, h, fill=UI["border"])

    def _summarize_now(self):
        """Force one summary cycle immediately (for testing or to push an update
        without waiting for the 5-minute timer). Runs off the UI thread."""
        import threading

        if self._controller.state is not ServiceState.RUNNING:
            self.set_status("Press Start first, then speak before summarizing")
            return
        if not self._cfg.has_key_for_provider():
            self.set_status(f"No API key for '{self._cfg.provider}' — add one in AI engine")
            return
        self.set_status("Summarizing now…")

        def work():
            try:
                n = self._controller.run_summary_cycle()
                msg = (f"Added {n} new point(s)" if n
                       else "No new points yet — speak more, then try again")
                self.set_status(msg)
            except Exception as e:  # noqa: BLE001
                self.set_status(f"Summarize failed: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _start(self):
        if self._meter is not None:
            self._stop_audio_test()
        if not self._cfg.has_key_for_provider():
            self.set_status(f"No API key for '{self._cfg.provider}' — add one in AI engine below")
        self._controller.start()
        self._start_service_meter()

    def _pause(self):
        if self._controller.state is ServiceState.PAUSED:
            self._controller.resume()
            self._start_service_meter()
        else:
            self._controller.pause()
            self._stop_service_meter()
            self._draw_meter(0.0)
            self._meter_hint.set("Paused")

    def _stop(self):
        self._controller.stop()
        self._stop_service_meter()
        self._draw_meter(0.0)
        self._meter_hint.set("")

    # --- live activity meter (during service) ------------------------------
    def _start_service_meter(self):
        if self._capture is None:
            return
        self._stop_service_meter()
        self._poll_service_meter()

    def _stop_service_meter(self):
        if self._service_after is not None:
            self.root.after_cancel(self._service_after)
            self._service_after = None

    def _poll_service_meter(self):
        if self._controller.state is not ServiceState.RUNNING:
            return
        level = self._capture.level() if self._capture else 0.0
        self._draw_meter(level)
        self._meter_hint.set("● Audio live" if level > 0.02 else "● Audio live (quiet)")
        self._service_after = self.root.after(50, self._poll_service_meter)

    def _delete_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        slide = self._controller.deck.latest_slide()
        if 0 <= idx < len(slide.points):
            del slide.points[idx]
            self._refresh(self._controller.deck)
            self._slide_window.update_slide(slide)
        self._clear_point_editor()

    # --- manual point add / edit ------------------------------------------
    def _validated_verse(self, raw: str):
        from ..slides.scripture import validate_reference
        raw = (raw or "").strip()
        if not raw:
            return None, False  # no verse given
        ref = validate_reference(raw)
        return ref, (ref is None)  # (normalized ref or None, was_invalid)

    def _add_or_update_point(self):
        from ..slides.deck import Point

        text = self._point_var.get().strip()
        if not text:
            self.set_status("Type a point first")
            return
        verse, invalid = self._validated_verse(self._verse_var.get())
        slide = self._controller.deck.latest_slide()

        if self._edit_index is not None and 0 <= self._edit_index < len(slide.points):
            slide.points[self._edit_index] = Point(text=text, scripture=verse)
            action = "updated"
        else:
            self._controller.deck.add_point(Point(text=text, scripture=verse), force=True)
            action = "added"

        self._refresh(self._controller.deck)
        if self._view_index is None:
            self._render_view()
        else:
            self._slide_window.update_slide(slide)
        note = " (verse not recognized, omitted)" if invalid else ""
        self.set_status(f"Point {action}{note}")
        self._clear_point_editor()

    def _edit_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            self.set_status("Select a point in the list to edit")
            return
        idx = sel[0]
        slide = self._controller.deck.latest_slide()
        if not (0 <= idx < len(slide.points)):
            return
        pt = slide.points[idx]
        self._point_var.set(pt.text)
        self._verse_var.set(pt.scripture or "")
        self._edit_index = idx
        self._add_btn.config(text="Update point")
        self.set_status("Editing — change the text and click Update point")

    def _clear_point_editor(self):
        self._point_var.set("")
        self._verse_var.set("")
        self._edit_index = None
        self._add_btn.config(text="Add point")

    def _fullscreen_slide(self):
        if self._slide_window is not None:
            self._slide_window.toggle_fullscreen()

    # --- display controls --------------------------------------------------
    def _scale_label(self, scale) -> str:
        for label, val in self._SIZE_CHOICES.items():
            if abs(val - float(scale or 1.0)) < 0.01:
                return label
        return "Medium"

    def _on_theme_change(self, name):
        if self._slide_window is not None:
            self._slide_window.set_theme(name)
        self._cfg.theme = name
        self._persist()

    def _on_size_change(self, label):
        scale = self._SIZE_CHOICES.get(label, 1.0)
        if self._slide_window is not None:
            self._slide_window.set_font_scale(scale)
        self._cfg.font_scale = scale
        self._persist()

    def _apply_church(self):
        name = self._church_var.get().strip()
        self._cfg.church_name = name
        if self._slide_window is not None:
            self._slide_window.set_church_name(name)
        self._persist()
        self.set_status(f"Church name set to “{name}”" if name else "Church name cleared")

    # --- timing controls ---------------------------------------------------
    def _label_for(self, choices: dict, seconds) -> str:
        for label, val in choices.items():
            if val == seconds:
                return label
        return f"{seconds} sec"

    def _on_interval_change(self, label):
        secs = self._INTERVAL_CHOICES.get(label, 300)
        self._cfg.summarize_interval_seconds = secs
        self._persist()
        self.set_status(f"Summarizing every {label}")

    def _on_window_change(self, label):
        secs = self._WINDOW_CHOICES.get(label, 300)
        self._cfg.transcript_window_seconds = secs
        try:
            self._controller.window.set_window_seconds(secs)
        except Exception as e:  # noqa: BLE001
            log.warning("could not apply window change: %s", e)
        self._persist()
        self.set_status(f"Context window: {label}")

    def _set_background(self):
        from tkinter import filedialog, messagebox

        path = filedialog.askopenfilename(
            title="Choose a background image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._slide_window.set_background_image(path)
            self._cfg.background_image = path
            self._persist()
            self.set_status("Background image set")
        except ImportError:
            messagebox.showerror(
                "Pillow needed",
                "Background images need the Pillow library.\n\nInstall it with:\n    pip install pillow",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Could not load image", str(e))

    def _clear_background(self):
        if self._slide_window is not None:
            self._slide_window.clear_background_image()
        self._cfg.background_image = ""
        self._persist()
        self.set_status("Background cleared")

    # --- blank screen / logo ----------------------------------------------
    def _toggle_blank(self):
        if self._slide_window is None:
            return
        on = not self._slide_window.is_blank()
        self._slide_window.set_blank(on)
        self._blank_btn.config(text="▶ Show slide" if on else "⬛ Blank screen")
        self.set_status("Screen blanked" if on else "Showing live slide")

    def _set_logo(self):
        from tkinter import filedialog, messagebox

        path = filedialog.askopenfilename(
            title="Choose a logo image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self._slide_window.set_logo(path)
            self._cfg.logo_image = path
            self._persist()
            self.set_status("Logo set — shows on the blank screen")
        except ImportError:
            messagebox.showerror(
                "Pillow needed",
                "Logo images need the Pillow library.\n\nInstall it with:\n    pip install pillow",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Could not load logo", str(e))

    def _clear_logo(self):
        if self._slide_window is not None:
            self._slide_window.clear_logo()
        self._cfg.logo_image = ""
        self._persist()
        self.set_status("Logo cleared")

    def _persist(self):
        try:
            self._cfg.save()
        except Exception as e:  # noqa: BLE001
            log.warning("could not save config: %s", e)

    def _end_service(self):
        from ..slides.pdf_export import export_service
        from tkinter import filedialog, messagebox

        folder = filedialog.askdirectory(
            title="Save the summary to…", initialdir=self._export_dir, mustexist=False)
        out_dir = folder or self._export_dir  # cancel = default exports/ folder

        self._controller.stop()
        self._stop_service_meter()
        try:
            result = export_service(self._controller.deck, out_dir, self._cfg.church_name)
            msg = f"Saved:\n{result['pptx']}"
            if result["pdf"]:
                msg += f"\n{result['pdf']}"
            else:
                msg += "\n(PDF skipped — LibreOffice not installed)"
            messagebox.showinfo("Service exported", msg)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Export failed", str(e))

    # --- shareable summary -------------------------------------------------
    def _summary_text(self) -> str:
        from ..slides.pdf_export import build_text_summary
        return build_text_summary(self._controller.deck, self._cfg.church_name)

    def _has_points(self) -> bool:
        if not self._controller.deck.all_points():
            self.set_status("No summary yet — nothing to share")
            return False
        return True

    def _copy_summary(self):
        if not self._has_points():
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._summary_text())
        self.set_status("Summary copied to clipboard")

    def _save_summary_text(self):
        from tkinter import filedialog

        if not self._has_points():
            return
        path = filedialog.asksaveasfilename(
            title="Save summary text", defaultextension=".txt",
            initialdir=self._export_dir, initialfile="sermon-summary.txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._summary_text())
            self.set_status(f"Saved {path}")
        except Exception as e:  # noqa: BLE001
            self.set_status(f"Could not save: {e}")

    def _email_summary(self):
        import webbrowser
        import urllib.parse

        if not self._has_points():
            return
        subject = (f"{self._cfg.church_name} — Sermon Summary" if self._cfg.church_name
                   else "Sermon Summary")
        url = ("mailto:?subject=" + urllib.parse.quote(subject)
               + "&body=" + urllib.parse.quote(self._summary_text()))
        webbrowser.open(url)
        self.set_status("Opening your email app…")

    def _whatsapp_summary(self):
        import webbrowser
        import urllib.parse

        if not self._has_points():
            return
        webbrowser.open("https://wa.me/?text=" + urllib.parse.quote(self._summary_text()))
        self.set_status("Opening WhatsApp — pick a contact or group")

    def run(self):
        self.root.mainloop()
