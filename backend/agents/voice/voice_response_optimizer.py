"""
Aadhya – Voice Response Optimizer
Rewrites Gemini responses for voice (Vapi + ElevenLabs TTS).
Strips markdown, enforces 60-token limit, single question only.
"""
from __future__ import annotations
import re


# ── Leading acknowledgement detection / stripping ────────────────────────────
# Live-call transcripts showed every single assistant turn opening with
# "Got it." — 9 of 10 turns — because the assistant prompt previously said
# "Always start by acknowledging..." with "Got it." as the first example.
# Over the phone this sounds like a robot. We now (a) rotate the prompt,
# and (b) post-process: if the new reply's leading acknowledgement matches
# the PREVIOUS reply's leading acknowledgement, we strip it so we never say
# the same opener twice in a row.
#
# The same helpers are used by the streaming path (vapi_handler) to keep
# what the caller HEARS consistent with what gets stored in the transcript.

# Match the first short acknowledgement sentence. Word list is tight on
# purpose — we only want to catch true filler acks, not content.
_LEADING_ACK_RE = re.compile(
    r"^(?:"
    r"Sure\s+thing"
    r"|Got\s+it"
    r"|Nice"
    r"|Thanks"
    r"|Thank\s+you"
    r"|Perfect"
    r"|Great"
    r"|Awesome"
    r"|Cool"
    r"|Alright"
    r"|Okay"
    r"|Ok"
    r"|Sure"
    r"|Understood"
    r"|Excellent"
    r"|Wonderful"
    r"|Makes\s+sense"
    r"|Sounds?\s+good"
    r"|Right"
    r"|Love\s+it"
    r")"
    r"[!,.\s\u2014\u2013-]+",
    re.IGNORECASE,
)

# Minimum length of the remainder AFTER stripping the ack. If removing the
# ack would leave a too-short tail (like a standalone "Excellent."), we keep
# the ack — otherwise we'd produce empty/meaningless replies.
_ACK_MIN_REMAINDER = 5


def detect_leading_ack(text: str) -> str:
    """
    Return the canonical lowercased acknowledgement at the start of `text`,
    or "" if there is no recognisable ack. Canonical form strips trailing
    punctuation/whitespace and collapses internal whitespace, so
    "Got it." / "got it!" / "Got  it, " all return "got it".
    """
    s = (text or "").lstrip()
    if not s:
        return ""
    m = _LEADING_ACK_RE.match(s)
    if not m:
        return ""
    raw = m.group(0)
    canonical = re.sub(r"[!,.\s\u2014\u2013-]+$", "", raw).strip().lower()
    canonical = re.sub(r"\s+", " ", canonical)
    return canonical


def strip_leading_ack(text: str) -> str:
    """
    Remove the leading acknowledgement sentence from `text` and re-capitalise
    the next sentence. Leaves `text` untouched when:
      - no ack is detected;
      - the remainder is too short (prevents pathological strips of lines
        that are purely "Excellent." style closers).
    """
    if not text:
        return text
    leading_ws = text[: len(text) - len(text.lstrip())]
    s = text.lstrip()
    m = _LEADING_ACK_RE.match(s)
    if not m:
        return text
    remainder = s[m.end():].lstrip()
    if len(remainder) < _ACK_MIN_REMAINDER:
        return text
    if remainder[0].islower():
        remainder = remainder[0].upper() + remainder[1:]
    return leading_ws + remainder


_EMOTIONAL_SIGNALS = {
    "dream": "That's exciting to hear —",
    "always wanted": "That's exciting to hear —",
    "been planning": "That's exciting to hear —",
    "just moved": "What a great time to be thinking about this —",
    "new home": "What a great time to be thinking about this —",
    "finally": "What a great time to be thinking about this —",
    "first home": "What a great time to be thinking about this —",
    "my family": "Making it right for the whole family —",
    "my kids": "Making it right for the whole family —",
    "excited": "Love that energy —",
    "anniversary": "Love that energy —",
    "birthday": "Love that energy —",
    "renovating": "Great time to make it exactly right —",
}

_GENERIC_ACKS = re.compile(
    r"^(great|perfect|got it|nice|sure|awesome|alright|okay|cool|sounds good)[.!,]?\s+",
    re.I,
)


def _replace_generic_ack_if_emotional(reply: str, caller_last_message: str) -> str:
    if not reply or not caller_last_message:
        return reply
    if not _GENERIC_ACKS.match(reply):
        return reply
    msg_lower = (caller_last_message or "").lower()
    for signal, warm_ack in _EMOTIONAL_SIGNALS.items():
        if signal in msg_lower:
            return _GENERIC_ACKS.sub(warm_ack + " ", reply)
    return reply


def optimize_for_voice(text: str, caller_last_message: str = "") -> str:
    """
    Clean and optimize a text response for spoken TTS delivery.
    """
    text = _strip_markdown(text)
    text = _fix_tts_pronunciations(text)
    # CHANGE 3: replace generic ack with warm acknowledgment if caller said something emotional
    text = _replace_generic_ack_if_emotional(text, caller_last_message)
    # FIX 6: collapse up to 2 consecutive leading acknowledgements within the same reply.
    # Example: "Nice. Thanks. What is your budget?" → "What is your budget?"
    text = strip_leading_ack(text)
    text2 = strip_leading_ack(text)
    if text2 != text:
        text = text2
    text = _ensure_single_question(text)
    text = _add_natural_pauses(text)
    text = _trim_to_token_limit(text, max_words=65)
    return text.strip()


def _fix_tts_pronunciations(text: str) -> str:
    """
    Force TTS engines to pronounce brand names correctly.
    "PropFlow" as a CamelCase run-on may be mispronounced by Cartesia/ElevenLabs.
    Split into two words for clear speech output.
    Only applied to spoken text — written text stays "PropFlow".
    """
    text = re.sub(r"\bPropFlow\b", "Prop Flow", text)
    text = re.sub(r"\bpropflow\b", "Prop Flow", text, flags=re.IGNORECASE)
    return text


def _strip_markdown(text: str) -> str:
    """Remove all markdown formatting."""
    # Remove headers
    text = re.sub(r"#{1,6}\s+", "", text)
    # Remove bold/italic
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    # Remove bullet/numbered lists — convert to prose
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Remove emojis (basic unicode range)
    text = re.sub(
        r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF]", "", text
    )
    # Replace multiple newlines with a space
    text = re.sub(r"\n+", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _ensure_single_question(text: str) -> str:
    """
    If multiple questions exist, keep only the first one.
    """
    # If there's 0 or 1 question mark, do nothing.
    if text.count("?") <= 1:
        return text

    # Hard cut at the first question mark to ensure exactly one question.
    first_q = text.find("?")
    if first_q == -1:
        return text

    trimmed = text[: first_q + 1].strip()

    # If the trimmed text is only a question with no acknowledgement,
    # keep at most one short leading sentence for context (if present).
    return trimmed


def _add_natural_pauses(text: str) -> str:
    """
    Add a soft pause before questions for natural TTS phrasing.
    """
    # Add pause before question words at mid-sentence
    text = re.sub(r"([a-z])\. (Could|Would|Can|May|What|Which|Who|How|When|Where)", r"\1, \2", text)
    return text


def _trim_to_token_limit(text: str, max_words: int = 65) -> str:
    """
    Trim to approximately max_words words at a sentence boundary.
    """
    words = text.split()
    if len(words) <= max_words:
        return text

    # Find last sentence boundary within limit
    truncated = " ".join(words[:max_words])
    # Try to cut at last sentence boundary
    last_sentence_end = max(
        truncated.rfind(". "),
        truncated.rfind("? "),
        truncated.rfind("! "),
    )
    if last_sentence_end > len(truncated) // 2:
        return truncated[:last_sentence_end + 1].strip()

    # Fallback: cut at word boundary and add ellipsis
    return truncated.rsplit(" ", 1)[0] + "."
