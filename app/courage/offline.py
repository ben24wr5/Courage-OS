"""Spare brain for when there's no internet: handles simple things without Claude."""
import ast
import datetime
import operator
import re

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg, ast.Mod: operator.mod}


def calc(expr):
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 100:
                raise ValueError
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        raise ValueError
    return ev(ast.parse(expr, mode="eval").body)


WORDS = {"times": "*", "x": "*", "multiplied by": "*", "plus": "+", "add": "+", "minus": "-",
         "take away": "-", "divided by": "/", "over": "/", "to the power of": "**"}


def answer(text, notes):
    t = text.lower().strip(" ?.!")
    if re.search(r"\btime\b", t) and ("what" in t or "the time" in t):
        now = datetime.datetime.now().strftime("%H:%M")
        return {"say": f"It's {now}. I can still tell the time without the internet.", "head": f"IT'S {now}.", "body": ""}
    if "date" in t or "what day" in t:
        d = datetime.datetime.now().strftime("%A %d %B")
        return {"say": f"It's {d}.", "head": d.upper(), "body": ""}
    m = re.match(r"(?:write (?:this )?down|note|remember)[:,]?\s+(.+)", t)
    if m:
        return {"say": "Noted. Even with no internet.", "head": "NOTED.", "body": f'"{m.group(1).upper()}"',
                "actions": [{"type": "note_add", "text": m.group(1)}]}
    if "notes" in t and ("read" in t or "my" in t):
        body = " · ".join(notes) if notes else "NO NOTES YET."
        return {"say": "Your notes: " + (", ".join(notes) if notes else "none yet."), "head": "YOUR NOTES:", "body": body.upper()}
    expr = t.replace("what's", "").replace("what is", "")
    for w, s in sorted(WORDS.items(), key=lambda kv: -len(kv[0])):
        expr = expr.replace(w, s)
    expr = re.sub(r"[^0-9+\-*/(). %]", "", expr).strip()
    if re.search(r"\d\s*[-+*/%]", expr):
        try:
            v = calc(expr)
            v = int(v) if float(v).is_integer() else round(v, 4)
            return {"say": f"That's {v}.", "head": f"= {v}", "body": expr}
        except Exception:
            pass
    for word, act in (("play", "music"), ("music", "music"), ("pause", "pause"), ("stop", "stop"),
                      ("louder", "up"), ("quieter", "down"), ("volume up", "up"), ("volume down", "down")):
        if word in t:
            if act in ("up", "down"):
                return {"say": "Fine.", "head": "VOLUME " + act.upper() + ".", "body": "",
                        "actions": [{"type": "volume", "value": act}]}
            return {"say": "Fine.", "head": "MUSIC.", "body": "",
                    "actions": [{"type": "music", "cmd": "play" if act == "music" else act}]}
    return {"say": "No internet. I'm running on my spare brain, so I can only do simple things right now.",
            "head": "NO INTERNET.", "body": "SPARE BRAIN ONLY: TIME, DATE, NOTES, SUMS, MUSIC AND VOLUME. BACK TO FULL POWER WHEN THE WI-FI RETURNS."}
