"""The summarisation prompt sent to Claude.

Kept in its own module so it can be unit-tested and tuned without touching the
API client. Changes here are prompt/LLM changes — re-run the parse tests.
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a live sermon summarizer for a Pentecostal/charismatic church. "
    "A preacher is speaking right now. From a rolling transcript you pull out "
    "the truths the congregation should catch, remember, and act on, and put "
    "them on a slide. You understand how Spirit-filled preaching works: bold "
    "declarations, heavy use of scripture, repetition for emphasis, and clear "
    "calls to respond. You capture the heart of the message, not every word."
)

# The model must return STRICT JSON: a list of objects. We parse defensively
# (summarize/parsing.py) so a malformed response just skips one cycle.
_ALREADY_SHOWN_BLOCK = """\
ALREADY ON SCREEN (do NOT repeat these). Only add a point that is genuinely new. \
If the preacher restates an earlier idea in different words for emphasis but adds \
no new meaning, do NOT output it again. A fresh point is fine only when it brings \
a new truth, a new scripture, or a real new angle:
{shown}


"""


USER_TEMPLATE = """\
{already_shown}From the sermon transcript below, pull the NEW key points from \
roughly the last five minutes. These appear live on a slide for the congregation.


What to capture (in this order of priority):
- DECLARATIONS of truth the people should hold onto ("God is your provider").
- EXPLICIT SCRIPTURE citations — capture verses ONLY when the preacher explicitly names the book and chapter/verse.
- CALLS TO ACTION / application — what the congregation should do or believe now.


CRITICAL PROCESSING RULES:
1. NO INFERRED SCRIPTURE: Do NOT guess, look up, or append a "scripture" field for implicit references, idioms, or paraphrases.
  - If the preacher says: "Who the son has set free is free indeed, there is no more condemnation"
  - You output the point as text: {{"point": "We are free in Jesus and not condemned"}}
  - Do NOT guess or add: "scripture": "John 8:36" or "Romans 8:1". Leave the scripture field completely out.
2. NO PRAYERS: Completely ignore corporate prayers, openings, intercessions, or conversational prayers to God (e.g., "Heavenly Father, we just thank you right now..."). Do NOT summarize them; skip them entirely.
3. EXPLICIT CITATIONS ONLY: When a book and chapter/verse are explicitly stated (e.g., "Matthew 6:32", "Luke 3:15"), provide a punchy summary or the actual declaration of that text, and include the clean reference string in the "scripture" field.
4. FLEXIBLE DENSITY & CONSISTENCY: You do NOT have a mandatory quota of words, characters, or bullet points to fulfill per slide. Maintain structural consistency with standard outputs across cycles. However, if the current transcript chunk lacks high-quality relevant content, compress or reduce the slide summary output by roughly 10-25% for this specific slide rather than filling it with fluff or tangents.


Style rules:
- Each point is ONE punchy line, max 10 words. Make it memorable, like something \
people could shout back or write down.
- Present tense, active voice, faith-filled and direct. No hedging, no "the \
preacher says".
- Add a "scripture" field ONLY when a passage is actually explicitly stated. Use the form \
"Book Chapter:Verse" (e.g. "John 3:16"). Omit the field entirely otherwise.
- Skip greetings, announcements, jokes, tangents, and pure repetition.
- Return 0 to 4 points. Quality over quantity. If nothing new is worth showing, return [].
- Respond with ONLY a JSON array, no prose, no markdown fences.


Example response:
[
 {{"point": "You are the righteousness of God", "scripture": "2 Corinthians 5:21"}},
 {{"point": "We are free in Jesus and not condemned"}},
 {{"point": "Walk by faith, not by what you see", "scripture": "2 Corinthians 5:7"}}
]


TRANSCRIPT:
{transcript}
"""


def build_user_prompt(transcript: str, already_shown: list[str] | None = None) -> str:
    shown_block = ""
    if already_shown:
        # Cap the list so a long service doesn't bloat the prompt; the most
        # recent points are the ones most likely to be restated.
        recent = already_shown[-20:]
        bullets = "\n".join(f"- {s}" for s in recent)
        shown_block = _ALREADY_SHOWN_BLOCK.format(shown=bullets)
    return USER_TEMPLATE.format(already_shown=shown_block, transcript=transcript.strip())
