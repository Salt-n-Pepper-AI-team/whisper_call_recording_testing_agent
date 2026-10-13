"""
side_by_side.py: Displays each call's transcript (what Whisper heard) and its printed items (OCR) side by side.
Matches calls and prints by name (both must have the same name; only the extension should differ).

Everything is local. The output is saved in <calls folder>/side_by_side.txt. Open it in VS Code
(it displays Urdu better than CMD).
This file contains real data (phone numbers in filenames and customer conversations in transcripts):
do not send it to anyone or paste it into this chat.

Run first:
    python transcribe_all.py Real_Call
    python read_print.py real_prints
Then:
    python side_by_side.py Real_Call real_prints
"""
import json
import os
import sys

sys.stdout.reconfigure(errors="replace")

calls_dir = sys.argv[1] if len(sys.argv) > 1 else "Real_Call"
prints_dir = sys.argv[2] if len(sys.argv) > 2 else "real_prints"

cache_path = os.path.join(calls_dir, "transcripts_cache.json")
prints_path = os.path.join(prints_dir, "prints.json")


def load(path, hint):
    if not os.path.exists(path):
        print(f"{path} not found. {hint}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    cache = load(cache_path, f"Run first: python transcribe_all.py {calls_dir}")
    prints = load(prints_path, f"Run first: python read_print.py {prints_dir}")

    lines, missing_print = [], 0
    for n, (key, transcript) in enumerate(sorted(cache.items()), 1):
        fname = key.rsplit(":", 1)[0]                 # Cache key: "name.aac:time"
        stem = os.path.splitext(fname)[0]
        lines.append("=" * 60)
        lines.append(f"{n}) {fname}")
        lines.append("")
        lines.append("Whisper heard:")
        lines.append("  " + transcript.strip())
        lines.append("")
        p = prints.get(stem)
        if p is None:
            missing_print += 1
            lines.append("Print: No print with this name was found in real_prints (the names must match)")
        else:
            lines.append("Items in print (OCR):")
            for it in p["items"]:
                lines.append(f"  {it['qty']}x {it['name']}")
            if not p["items"]:
                lines.append("  (No items were detected)")
            if p["flags"]:
                lines.append("  ! OCR warning: " + "; ".join(p["flags"]))
        lines.append("")

    out = os.path.join(calls_dir, "side_by_side.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Comparison of {len(cache)} calls is ready: {out}")
    if missing_print:
        print(f"Prints for {missing_print} calls were not found (the names did not match).")
    print("Open this file in VS Code. It contains real data; do not send it to anyone.")


if __name__ == "__main__":
    main()