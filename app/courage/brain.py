"""The brain: talks to Google Gemini through its API and turns answers into screen + speech + actions."""
import json
import re

import requests

MODEL = "gemini-flash-latest"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class KeyError_(Exception):
    """The Gemini API key is missing or wrong."""


MOODS = {
    "grumpy": "Grumpy, sarcastic and posh British, like a fed-up old attic computer. Mock the user a little first, then genuinely help.",
    "nice": "Warm, cheerful and kind, still British and a little witty. No insults.",
    "extra rude": "Extra cheeky and roasting, British. Playful insults only, never cruel, never about appearance-shaming, race, religion, disability or anything hurtful. Always still help.",
}

SYSTEM = """You are COURAGE OS, a talking computer that lives on a USB stick. You speak out loud and show text on a teal-green screen in dotted capital letters.

PERSONALITY (current mood: {mood}): {mood_text}

CURRENT INFO
- Time: {now}
- User: {user}
- What you remember about them: {memory}
- Their notes: {notes}
- Battery: {battery}. Internet: {online}. Bluetooth: {bt}.
- Weather for {city}: {weather}
- Top headlines: {news}
- Music files on the USB: {music}
- Photos on the USB: {photos}

RULES
- Keep spoken answers short: usually 1-3 sentences. Longer only for stories, homework steps or read-aloud.
- For homework, explain step by step. For spelling, spell it letter by letter. For translation, give the phrase and how to say it.
- Quizzes: ask one question at a time, check the answer next turn, keep score in your head.
- Never make up live facts: use CURRENT INFO for weather/news. If something isn't there, say so.
- If asked to draw or make a picture, put a simple, colourful SVG drawing (viewBox 0 0 200 120, no text, no scripts) in "svg".

REPLY WITH ONLY ONE JSON OBJECT, no other text:
{{
 "say": "what you say out loud (normal sentence case)",
 "head": "SHORT BIG LINE FOR THE SCREEN, CAPITALS, max 8 words",
 "body": "SMALLER SCREEN TEXT IN CAPITALS, max 40 words, can be empty",
 "image": "a 2-5 word picture search for the answer, or empty",
 "svg": "an svg drawing only when asked to draw/make a picture, else empty",
 "actions": [ ... zero or more actions ... ],
 "remember": ["short new facts about the user worth remembering, or empty list"]
}}

ACTIONS you can use (only when the user asks):
{{"type":"note_add","text":"..."}}  {{"type":"notes_clear"}}
{{"type":"music","cmd":"play|pause|resume|next|stop","query":"optional song name"}}
{{"type":"radio","cmd":"play|stop","query":"station or genre"}}
{{"type":"photos","cmd":"show|next|back|stop"}}
{{"type":"volume","value":"up|down|mute|0-100"}}  {{"type":"brightness","value":"up|down|0-100"}}
{{"type":"wifi","cmd":"scan"}}  (shows a list they pick from; always use scan for Wi-Fi)
{{"type":"bluetooth","cmd":"scan|disconnect","name":"..."}}  (scan shows a list they pick from; use scan to connect something)
{{"type":"colour","value":"#hex colour for the screen background, or 'default'"}}
{{"type":"mood","value":"grumpy|nice|extra rude"}}
{{"type":"user","name":"name of the person now using it"}}
{{"type":"city","name":"their town for weather"}}
{{"type":"update"}}
{{"type":"screensaver"}}
"""


class Brain:
    """Talks to Google Gemini through its API (key from aistudio.google.com)."""

    def __init__(self, api_key):
        self.api_key = (api_key or "").strip()
        self.history = []

    def reset(self):
        self.history = []

    def _call(self, contents, system=None, max_tokens=1500, json_mode=True):
        if not self.api_key:
            raise KeyError_("no api key")
        body = {"contents": contents,
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9}}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = requests.post(URL.format(model=MODEL), json=body, timeout=60,
                          headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
        if r.status_code in (400, 401, 403) and ("API_KEY" in r.text or "API key" in r.text or r.status_code != 400):
            raise KeyError_("api key rejected: " + r.text[:200])
        r.raise_for_status()
        data = r.json()
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            return '{"say": "Hmm. I\'d rather not answer that one.", "head": "HMM. NO."}'

    def ask(self, text, ctx):
        mood = ctx.get("mood", "grumpy")
        system = SYSTEM.format(mood=mood, mood_text=MOODS.get(mood, MOODS["grumpy"]), **{
            k: ctx.get(k, "unknown") for k in
            ("now", "user", "memory", "notes", "battery", "online", "bt", "city", "weather", "news", "music", "photos")})
        self.history.append({"role": "user", "parts": [{"text": text}]})
        self.history = self.history[-20:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)
        raw = self._call(self.history, system=system)
        self.history.append({"role": "model", "parts": [{"text": raw}]})
        return parse_reply(raw)

    def check_key(self):
        self._call([{"role": "user", "parts": [{"text": "Say hi"}]}], max_tokens=20, json_mode=False)


def parse_reply(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    data = {}
    if m:
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            data = {}
    if not data:
        data = {"say": raw.strip(), "head": "", "body": raw.strip().upper()[:200]}
    out = {
        "say": str(data.get("say", "")).strip(),
        "head": str(data.get("head", "")).upper().strip(),
        "body": str(data.get("body", "")).upper().strip(),
        "image": str(data.get("image", "")).strip(),
        "svg": clean_svg(str(data.get("svg", ""))),
        "actions": [a for a in data.get("actions", []) if isinstance(a, dict)],
        "remember": [str(r) for r in data.get("remember", []) if r],
    }
    if not out["head"] and out["say"]:
        out["head"] = out["say"].upper()[:60]
    return out


def clean_svg(svg):
    """Only allow a plain drawing: no scripts, events, links or embedded content."""
    svg = svg.strip()
    if not svg.startswith("<svg") or not svg.endswith("</svg>"):
        return ""
    if re.search(r"<\s*(script|foreignObject|iframe|image|a\b|use)|on\w+\s*=|javascript:|href", svg, re.I):
        return ""
    return svg
