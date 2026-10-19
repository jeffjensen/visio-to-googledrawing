"""Compare the base64 sent in create_file calls (read from a Claude Code session transcript) with the intended EMF.

usage: python -I sent_vs_orig.py <transcript.jsonl> <title substring> <orig.emf> [which=-1]
"""
import base64, json, sys, difflib

tr, title, emf = sys.argv[1], sys.argv[2], sys.argv[3]
which = int(sys.argv[4]) if len(sys.argv) > 4 else -1
sent = []
with open(tr, encoding="utf-8") as f:
    for line in f:
        try:
            o = json.loads(line)
        except Exception:
            continue
        msg = o.get("message") or {}
        c = msg.get("content")
        if not isinstance(c, list):
            continue
        for b in c:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name", "").endswith("create_file"):
                inp = b.get("input", {})
                if title in inp.get("title", "") and inp.get("base64Content"):
                    sent.append(inp["base64Content"])
print("matching create_file calls:", len(sent))
s = sent[which]
orig = base64.b64encode(open(emf, "rb").read()).decode()
print("sent len %d, orig len %d, identical: %s" % (len(s), len(orig), s == orig))
if s != orig:
    sm = difflib.SequenceMatcher(None, orig, s, autojunk=False)
    n = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            n += 1
            if n <= 40:
                print("%-8s orig[%d:%d]=%r  sent[%d:%d]=%r   (context orig: ...%s...)" % (tag, i1, i2, orig[i1:i2], j1, j2, s[j1:j2], orig[max(0, i1 - 12):i2 + 12]))
    print("diff ops:", n)
    # decodability
    try:
        base64.b64decode(s, validate=True)
        print("sent decodes as valid base64")
    except Exception as e:
        print("sent does NOT decode:", e)
