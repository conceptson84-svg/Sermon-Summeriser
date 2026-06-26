# Church Sermon Summarizer

Listens to a live sermon (mixer audio into the media-room computer), transcribes
it locally, and on a timer uses an AI model (Claude, Gemini, DeepSeek, OpenAI,
or any model via OpenRouter) to extract short one-liner key points with biblical
references, tuned for Pentecostal preaching. Points roll onto a clean slide
shown fullscreen on the TV (second screen) and exposed to OBS over NDI. At the
end of the service it exports the full summary as a PDF.

Runs on **macOS, Windows, and Linux**. Everything is operated from a single
control panel — no file editing needed during a service.

## How it works

```
Mixer audio → computer input
      ↓
 sounddevice (5s chunks, stereo→mono)
      ↓
 faster-whisper (local, offline, CPU-capped so it never starves OBS)
      ↓
 rolling transcript window (configurable length)
      ↓
 AI model on a timer → JSON key points + scripture refs
   (already-shown points fed back so it doesn't repeat itself)
      ↓
 scripture validator (drops mis-transcribed refs — never hits the screen)
   + near-duplicate filter (collapses reworded repeats)
      ↓
 rolling deck (new slide every 6 points)
      ↓
 fullscreen window on the TV  ──capture──▶  OBS Window Capture → NDI
      ↓ (End Service)
 .pptx + .pdf (reportlab, no external tools) + share via email / WhatsApp / text
```

## Setup

Runs on **macOS, Windows, and Linux**. Use Python 3.11+ in a virtualenv.

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows** (PowerShell or Command Prompt) — use the python.org installer, which
already bundles Tkinter:
```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Or just double-click **`run.bat`** (it creates the venv, installs deps, and
launches the app the first time).

Copy the config and add an API key:

```bash
cp config.example.json config.json
# edit config.json, or set the matching env var
```

### Choosing an AI provider

You're not locked to Claude. Set `provider` in `config.json` to any of:

| `provider` | Key field (or env var) | Default model | Notes |
|-----------|------------------------|---------------|-------|
| `anthropic` | `anthropic_api_key` / `ANTHROPIC_API_KEY` | Claude Haiku | Direct |
| `openrouter` | `openrouter_api_key` / `OPENROUTER_API_KEY` | `anthropic/claude-haiku-4.5` | One key → Claude, Gemini, DeepSeek, +300 models |
| `gemini` | `gemini_api_key` / `GEMINI_API_KEY` | `gemini-2.0-flash` | Google direct (OpenAI-compat endpoint) |
| `deepseek` | `deepseek_api_key` / `DEEPSEEK_API_KEY` | `deepseek-chat` | Direct |
| `openai` | `openai_api_key` / `OPENAI_API_KEY` | `gpt-4o-mini` | Direct |

Leave `model` blank to use the provider default, or set it explicitly (e.g.
with OpenRouter: `"model": "google/gemini-2.0-flash"` to run Gemini through your
OpenRouter key). **OpenRouter is the easiest way to switch models** — one key,
change the `model` string, done. `base_url` lets you point at a proxy or
self-hosted endpoint if needed.

Everything downstream (scripture validation, slide deck, PDF export) is
provider-agnostic — only the summary text source changes.

Find your mixer's audio input device index:

```bash
python run.py --devices
```

Put that number in `config.json` as `audio_device_index`.

## Run

```bash
python run.py
```

On Windows: `python run.py` (with the venv activated), or double-click `run.bat`.

Two windows open:
- The **control panel** on your primary screen (everything is operated here).
- The **slide window** on the second screen (the TV). Press `F` to go
  fullscreen, `Esc` to exit, `←/→` to navigate slides.

## Control panel

Almost nothing needs the config file anymore — the control panel is fully
self-service, and changes save automatically:

| Section | Controls |
|---------|----------|
| **Service** | Start · Pause · Stop · **Summarize now** (force an update instantly) |
| **Audio input** | Device dropdown (↻ to rescan) · **Test audio** + live level meter |
| **AI engine** | Provider dropdown · API-key field (Show/Save) |
| **Church** | Name shown on the slide header + PDF |
| **Display** | Theme · Text size · Background image · **Blank screen** · Logo · Fullscreen |
| **Timing** | Summarize-every interval · Context-window length |
| **Current slide** | Live preview · add/edit/delete a point by hand · Prev/Next/Live |
| **Export & share** | **End Service → PDF** (pick the folder) · Copy · Save .txt · Email · WhatsApp |

**Audio meter** — click **Test audio** before the service to confirm the mixer
feed (green = good, amber = loud, red = clipping). Once you press **Start** the
same bar stays live, showing **● Audio live** so you can see audio is flowing at
a glance.

**First-time flow:** open the app → pick your provider and paste the API key →
pick the audio device → Test audio (green) → Start → speak → Summarize now.

**During a service:**
- **Blank screen** clears the TV (or shows your logo) for worship/offering, then
  **Show slide** brings the summary back — the service keeps running underneath.
- **Add/edit a point** by hand to fix an AI mishear or add something it missed
  (double-click a point in the list to edit it).
- **Prev/Next** step back through earlier slides without losing your place; the
  footer shows **LIVE** or **REVIEW**, and **Live** jumps back to the latest.

**After the service:** click **End Service → PDF** and choose a folder — it saves
both an editable `.pptx` and a printable `.pdf`. To send the summary to members,
use **Copy**, **Save .txt**, **Email**, or **WhatsApp** (these share the text;
attach the saved PDF manually if you want the formatted version).

## OBS / NDI

The slide is a normal window, so capture it in OBS with **Window Capture** and
add an **NDI Output** (OBS NDI plugin / NDI Tools). That gives you the slide as
an NDI source for your broadcast — no special integration needed.

## Configuration (`config.json`)

Most of these are also editable from the control panel (and saved back here
automatically). The file is mainly for first-time setup and the few keys with no
UI control yet.

| Key | Meaning | In UI? |
|-----|---------|--------|
| `provider` | `anthropic` / `openrouter` / `gemini` / `deepseek` / `openai` | yes |
| `model` | Model id; blank = provider default | no |
| `<provider>_api_key` | API key for the chosen provider | yes |
| `audio_device_index` | Mixer input device (`--devices` to list) | yes |
| `whisper_model_size` | `small` recommended; `base` if CPU is tight | no |
| `whisper_cpu_threads` | Hard cap so OBS keeps CPU headroom (default 2) | no |
| `summarize_interval_seconds` | How often to update the slide | yes (Timing) |
| `transcript_window_seconds` | How much recent speech the AI reads each cycle | yes (Timing) |
| `max_points_per_slide` | Roll to a new slide after this many points | no |
| `second_screen_index` | `1` = the TV; `0` = primary | no |
| `church_name` | Shown in the slide header and PDF | yes |
| `theme` / `font_scale` | Slide colour theme and text size | yes (Display) |
| `background_image` / `logo_image` | Slide backdrop and blank-screen logo | yes (Display) |

## Tests

The core logic (scripture validation, response parsing, deck overflow,
transcript window, API-failure resilience) is pure Python and runs without the
audio/AI deps:

```bash
python -m pytest tests/ -q
```

## Design notes

- **Never crashes live.** If the AI API fails, times out, or returns junk, the
  cycle is skipped and the last slide stays on screen.
- **No wrong scripture on the broadcast.** Every reference is validated against
  the 66-book canon and chapter counts; anything invalid is dropped.
- **No needless repetition.** Reworded versions of the same point are collapsed,
  while genuinely new emphasis (different words, new meaning) is kept.
- **OBS comes first.** Transcription is CPU-capped so it can't starve the
  encoder during a live stream.
- **Offline by default.** Audio is transcribed locally and never leaves the
  building; only the short text transcript goes to the AI provider.

## Optional dependencies

- **reportlab** — generates the PDF directly (no external program). Included in
  `requirements.txt`; this is the default PDF path.
- **LibreOffice** — optional fallback for PDF only if reportlab isn't installed.
  Not needed when reportlab is present.
- **Pillow** — needed for background and logo images (included in
  `requirements.txt`).
- **OBS NDI plugin / NDI Tools** — only if you want the NDI broadcast feed.

## Security note

API keys are stored in plain text in `config.json` (gitignored). That's fine for
a single trusted media-room machine. Don't commit `config.json` or share it.
