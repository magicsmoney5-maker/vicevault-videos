#!/usr/bin/env python3
"""Compare voice takes with the script: word errors, long pauses inside sentences, pace."""
import sys, json, re, difflib
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from render import transcribe

NUM = {"6": "six", "6's": "six's", "19th": "nineteenth", "18th": "eighteenth", "9": "nine", "vi": "six", "vi's": "six's"}


def norm(text):
    toks = re.findall(r"[a-z0-9']+", text.lower().replace("-", " "))
    return [NUM.get(t, t) for t in toks]


def check(script, take):
    w = transcribe(take)
    said = norm(" ".join(x[2] for x in w))
    want = norm(script)
    sm = difflib.SequenceMatcher(None, want, said)
    errs = [(op, " ".join(want[a:b]), " ".join(said[c:d])) for op, a, b, c, d in sm.get_opcodes() if op != "equal"]
    gaps = []
    for a, b in zip(w, w[1:]):
        g = b[0] - a[1]
        if g > 0.55 and not re.search(r"[.?!,]$", a[2]):
            gaps.append((round(a[1], 2), round(g, 2), a[2], b[2]))
    secs = w[-1][1] - w[0][0]
    return {"take": take, "errors": errs, "stalls": gaps, "wpm": round(len(said) / secs * 60), "len": round(w[-1][1], 2)}


if __name__ == "__main__":
    script = open(sys.argv[1]).read()
    for t in sys.argv[2:]:
        print(json.dumps(check(script, t)))
