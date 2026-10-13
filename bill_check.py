"""
bill_check.py: Calculates the order bill using menu prices and compares three things:
  1) Are the printed items (OCR) in the menu? What subtotal do their prices add up to?
  2) The gross amount on the print.
  3) The bill amount spoken during the call (from the numbers in the transcript).
If all three match, the order bill in the call and print is correct.

Limitation: This does not compare the item names heard in the call. If two different items have the same price (for example, Club Sandwich
and Chicken Sandwich, both 1250), it cannot detect the difference. That is why it must be
used alongside item matching, not as a replacement for it.

Run first:
    python transcribe_all.py Real_Call
    python read_print.py real_prints
Then:
    python bill_check.py Real_Call real_prints menu.csv

Only the call number, item names, and amounts appear on the screen (not the transcript or phone number).
The call number matches the number in side_by_side.txt.
The complete report is saved locally in <calls folder>/bill_check.csv (it contains filenames:
do not send it to anyone).
"""
import csv
import json
import os
import re
import sys

sys.stdout.reconfigure(errors="replace")

from rapidfuzz import fuzz

# Tax rates that may apply to the bill (confirm with the manager: 16% for cash, lower for card?).
TAX_RATES = (0.0, 0.05, 0.08, 0.16)

calls_dir = sys.argv[1] if len(sys.argv) > 1 else "Real_Call"
prints_dir = sys.argv[2] if len(sys.argv) > 2 else "real_prints"
menu_path = sys.argv[3] if len(sys.argv) > 3 else "menu.csv"


def norm(s):
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return re.sub(r"(pcs|pes|pieces|piece|pc)$", "pcs", s)    # Treat "6pes" and "6 Pcs" as the same


def load_menu(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                price = int(float(r["price"]))
            except (ValueError, TypeError):
                continue
            rows.append({"name": r["print_name"], "price": price,
                         "key": norm(r["print_name"]), "base": norm(r["name"])})
    return rows


def match_item(name, rate, menu):
    """Matches a printed item with the closest menu entry. If the name has no variant, it chooses by rate."""
    key = norm(name)
    scored = sorted(((max(fuzz.ratio(key, m["key"]), fuzz.ratio(key, m["base"])), m) for m in menu),
                    key=lambda x: -x[0])
    best = scored[0][0]
    if best < 85:
        return None
    close = [m for s, m in scored if s >= best - 6]
    if rate is not None:
        for m in close:
            if abs(m["price"] - rate) < 1:
                return m
    return close[0]


def numbers_in(text):
    nums = []
    for tok in re.findall(r"\d[\d,]*", text):
        try:
            n = int(tok.replace(",", ""))
        except ValueError:
            continue
        if 100 <= n <= 99999:                    # Ignore small numbers (25, 30 percent) and phone numbers
            nums.append(n)
    return nums


def find_bill(subtotal, nums):
    hits = []
    for rate in TAX_RATES:
        target = subtotal * (1 + rate)
        tol = max(5, target * 0.0015)
        for n in nums:
            if abs(n - target) <= tol:
                hits.append((n, rate, target))
    return hits


def check(transcript, p, menu):
    reasons, notes = [], []
    priced, unmatched = [], []
    for it in p["items"]:
        m = match_item(it["name"], it.get("rate"), menu)
        if m is None:
            unmatched.append(it["name"])
            continue
        priced.append((m, it["qty"]))
        if it.get("rate") is not None and abs(it["rate"] - m["price"]) >= 1:
            notes.append(f"{m['name']}: print rate is {it['rate']}, menu price is {m['price']}")
    nums = numbers_in(transcript)
    res = {"subtotal": None, "gross": p.get("gross"), "bill": None, "tax": None,
           "reasons": reasons, "notes": notes, "unmatched": unmatched, "numbers": nums}

    if not p["items"]:
        reasons.append("No items were read from the print")
        return res
    if unmatched:
        reasons.append("Not found in menu: " + ", ".join(unmatched))
        return res

    subtotal = sum(m["price"] * q for m, q in priced)
    res["subtotal"] = subtotal
    if p.get("gross") is None:
        reasons.append("The print's gross amount was not read")
    elif abs(subtotal - p["gross"]) > 1:
        reasons.append(f"Print gross is {p['gross']:g}, menu-based total is {subtotal}")

    hits = find_bill(subtotal, nums)
    if hits:
        n, rate, _ = hits[0]
        res["bill"], res["tax"] = n, rate
    else:
        reasons.append("No bill amount matching the menu total was found in the call (numbers: "
                       + (", ".join(map(str, nums)) if nums else "none") + ")")
    return res


def main():
    cache_path = os.path.join(calls_dir, "transcripts_cache.json")
    prints_path = os.path.join(prints_dir, "prints.json")
    for path, hint in ((cache_path, f"python transcribe_all.py {calls_dir}"),
                       (prints_path, f"python read_print.py {prints_dir}"),
                       (menu_path, "Place menu.csv in this folder")):
        if not os.path.exists(path):
            print(f"{path} not found. Run first: {hint}")
            return

    with open(cache_path, encoding="utf-8") as f:
        cache = json.load(f)
    with open(prints_path, encoding="utf-8") as f:
        prints = json.load(f)
    menu = load_menu(menu_path)

    report, ok = [], 0
    for n, (key, transcript) in enumerate(sorted(cache.items()), 1):
        fname = key.rsplit(":", 1)[0]
        p = prints.get(os.path.splitext(fname)[0])
        if p is None:
            print(f"Call {n}: print not found (the names did not match)")
            report.append({"call": n, "file": fname, "status": "NO_PRINT"})
            continue
        r = check(transcript, p, menu)
        status = "OK" if not r["reasons"] else "CHECK"
        ok += status == "OK"

        print(f"Call {n}: {status}")
        if r["subtotal"] is not None:
            print(f"  Subtotal from menu: {r['subtotal']}, print gross "
                  f"{'?' if r['gross'] is None else format(r['gross'], 'g')}")
        if r["bill"] is not None:
            print(f"  Bill in call: {r['bill']} (subtotal + {round(r['tax'] * 100)}% tax)")
        for x in r["reasons"]:
            print("  -", x)
        for x in r["notes"]:
            print("  *", x)
        report.append({
            "call": n, "file": fname, "status": status, "subtotal_menu": r["subtotal"],
            "print_gross": r["gross"], "spoken_bill": r["bill"],
            "tax_percent": None if r["tax"] is None else round(r["tax"] * 100),
            "reasons": "; ".join(r["reasons"]), "notes": "; ".join(r["notes"]),
        })

    out = os.path.join(calls_dir, "bill_check.csv")
    fields = ["call", "file", "status", "subtotal_menu", "print_gross", "spoken_bill",
              "tax_percent", "reasons", "notes"]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(report)
    print(f"\nThe bill, print, and menu match for {ok}/{len(report)} calls.")
    print(f"Report: {out}")


if __name__ == "__main__":
    main()