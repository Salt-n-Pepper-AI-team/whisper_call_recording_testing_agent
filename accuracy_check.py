"""
accuracy_check.py: test recordings par Whisper + extract.py ki accuracy napta hai.

Isi folder mein ye banayein:
    test_calls/call1.aac, call2.aac, ...        (test recordings)
    test_calls/ground_truth.txt                 (har line: file | sahi order)

ground_truth.txt ki misal:
    # file | qty item, qty item
    call1.aac | 2 zinger burger, 1 fries, 1 cold drink
    call2.aac | 3 sandwich, 1 pizza

Chalane ka tareeqa:
    python accuracy_check.py            # purani transcripts cache se leta hai (extract.py badalne ke baad jaldi chalta hai)
    python accuracy_check.py --fresh    # Whisper sab recordings par dobara chalata hai
"""
import csv
import json
import os
import re
import sys
import time
from collections import Counter

sys.stdout.reconfigure(errors="replace")   # CMD mein Urdu print par crash na ho

from pipeline import transcribe            # Whisper model yahan load hota hai
from extract import extract_order
from compare import compare

FOLDER = "test_calls"
TRUTH = os.path.join(FOLDER, "ground_truth.txt")
CACHE = os.path.join(FOLDER, "transcripts_cache.json")
REPORT = "accuracy_report.csv"
FRESH = "--fresh" in sys.argv


def parse_expected(text):
    items = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(\d+)\s*x?\s*(.+)", part)
        if not m:
            raise ValueError(f"Samajh nahi aaya: '{part}' (sahi format: 2 zinger burger)")
        items.append({"name": m.group(2).strip().lower(), "qty": int(m.group(1))})
    return items


def load_truth():
    rows = []
    with open(TRUTH, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                print(f"[SKIP] ground_truth.txt line {n}: '|' nahi mila: {line}")
                continue
            fname, exp = line.split("|", 1)
            rows.append((fname.strip(), parse_expected(exp)))
    return rows


def fmt(items):
    return ", ".join(f"{i['qty']}x {i['name']}" for i in items) or "(kuch nahi)"


def main():
    if not os.path.exists(TRUTH):
        print(f"{TRUTH} nahi mili. Pehle test_calls folder aur ground_truth.txt banayein.")
        return

    rows = load_truth()
    cache = {}
    if os.path.exists(CACHE) and not FRESH:
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)

    report = []
    counted = correct = items_total = items_ok = 0
    missed = Counter()
    times = []

    for fname, expected in rows:
        path = os.path.join(FOLDER, fname)
        if not os.path.exists(path):
            print(f"[SKIP] {fname}: file test_calls mein nahi mili")
            continue

        key = f"{fname}:{os.path.getmtime(path)}"
        secs = None
        if key in cache:
            transcript = cache[key]
        else:
            t0 = time.time()
            transcript = transcribe(path)
            secs = time.time() - t0
            times.append(secs)
            cache[key] = transcript

        parsed = extract_order(transcript)
        # compare(sunna gaya, sahi order): "missing" = ghalat add hua, "extra" = miss hua
        status, d = compare(parsed["items"], expected)
        is_ok = status == "MATCH"

        counted += 1
        correct += is_ok
        items_total += len(expected)
        items_ok += len(expected) - len(d["extra"]) - len(d["qty_diff"])
        missed.update(d["extra"].keys())

        print(f"[{'OK ' if is_ok else 'BAD'}] {fname}" + (f" ({secs:.1f}s)" if secs else " (cache)"))
        if not is_ok or parsed["uncertain"]:
            print("   Transcript :", transcript)
            print("   Sunna gaya :", fmt(parsed["items"]))
            print("   Sahi order :", fmt(expected))
            for n, q in d["extra"].items():
                print(f"   Miss hua   : {q}x {n}")
            for n, q in d["missing"].items():
                print(f"   Ghalat add : {q}x {n}")
            for n, x in d["qty_diff"].items():
                print(f"   Quantity   : {n} sunna {x['call']}, sahi {x['punched']}")
            if parsed["uncertain"]:
                print("   Unclear    :", "; ".join(parsed["uncertain"]))

        report.append({
            "file": fname,
            "result": "OK" if is_ok else "BAD",
            "transcript": transcript,
            "heard": fmt(parsed["items"]),
            "expected": fmt(expected),
            "missed": "; ".join(f"{q}x {n}" for n, q in d["extra"].items()),
            "wrongly_added": "; ".join(f"{q}x {n}" for n, q in d["missing"].items()),
            "wrong_qty": "; ".join(f"{n} ({x['call']} vs {x['punched']})" for n, x in d["qty_diff"].items()),
            "seconds": f"{secs:.1f}" if secs else "",
        })

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    if not report:
        print("Koi recording process nahi hui.")
        return

    with open(REPORT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)

    print("\n" + "=" * 50)
    print(f"Calls test hui        : {counted}")
    print(f"Poora order sahi      : {correct}/{counted} ({100 * correct / counted:.0f}%)")
    if items_total:
        print(f"Item level par sahi   : {items_ok}/{items_total} ({100 * items_ok / items_total:.0f}%)")
    if times:
        print(f"Whisper ka average    : {sum(times) / len(times):.1f} second per call")
    if missed:
        print("Sab se zyada miss hone wale items:", ", ".join(f"{n} ({c})" for n, c in missed.most_common(5)))
    print(f"Poori report          : {REPORT} (Excel mein khul jati hai)")


if __name__ == "__main__":
    main()