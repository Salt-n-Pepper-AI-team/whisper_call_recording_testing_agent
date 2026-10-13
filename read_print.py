"""
read_print.py: Reads items and quantities from an image of a printed Booking Slip.
Everything runs on this laptop (including OCR); nothing is sent outside.

The customer's name, phone number, or address is never printed or saved, only items and totals.

Install once:
    pip install rapidocr-onnxruntime opencv-python-headless

How to run:
    python read_print.py real_prints\\ord1046.jpeg     (one image)
    python read_print.py real_prints                   (entire folder)

When run on an entire folder, these files are created in that folder (items only, no customer data):
    prints.json            items from each print
    menu_from_prints.txt   item names found in the prints (useful for creating a menu list)
"""
import json
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(errors="replace")   # Prevent crashes when printing in CMD

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def group_lines(result):
    """Combines OCR fragments into lines based on their positions (top to bottom, left to right)."""
    boxes = []
    for entry in result:
        box, text = entry[0], entry[1]
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append({"x": min(xs), "y": sum(ys) / len(ys), "h": max(ys) - min(ys), "t": str(text).strip()})
    if not boxes:
        return []
    heights = sorted(b["h"] for b in boxes)
    tol = max(4.0, 0.6 * heights[len(heights) // 2])
    boxes.sort(key=lambda b: b["y"])
    rows, cur = [], [boxes[0]]
    for b in boxes[1:]:
        if abs(b["y"] - sum(c["y"] for c in cur) / len(cur)) <= tol:
            cur.append(b)
        else:
            rows.append(cur)
            cur = [b]
    rows.append(cur)
    return [" ".join(c["t"] for c in sorted(r, key=lambda c: c["x"])) for r in rows]


def image_to_lines(path):
    import cv2
    img = cv2.imread(path)
    if img is None:
        raise ValueError(f"Could not open image: {path}")
    if img.shape[1] < 1000:        # Enlarging small images improves OCR accuracy
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    result, _ = get_ocr()(img)
    return group_lines(result or [])


def to_num(tok):
    try:
        return float(tok.strip().replace(",", ""))
    except ValueError:
        return None


def num_out(x):
    return int(x) if float(x).is_integer() else x


def parse_row(line):
    """A single item line: [Sr] ItemName Rate Qty Amt [Instruction]. rate x qty = amt is used to detect OCR errors."""
    tokens = line.split()
    if len(tokens) < 4:
        return None
    start = 1 if tokens[0].isdigit() else 0
    chosen, valid = None, False
    for i in range(start + 1, len(tokens) - 2):          # The name must contain at least one word
        rate, qty, amt = (to_num(t) for t in tokens[i:i + 3])
        if None in (rate, qty, amt):
            continue
        if qty > 0 and abs(rate * qty - amt) < 1:
            chosen, valid = i, True
            break
    if chosen is None:                                    # If no valid three numbers are found, take the last three
        for i in range(len(tokens) - 3, start, -1):
            if None not in (to_num(t) for t in tokens[i:i + 3]):
                chosen = i
                break
    if chosen is None:
        return None
    rate, qty, amt = (to_num(t) for t in tokens[chosen:chosen + 3])
    return {
        "name": " ".join(tokens[start:chosen]),
        "qty": num_out(qty), "rate": num_out(rate), "amount": num_out(amt),
        "note": " ".join(tokens[chosen + 3:]),
        "valid": valid,
    }


def parse_slip(lines):
    low = [l.lower() for l in lines]
    start = next((i for i, l in enumerate(low) if "item" in l and ("qty" in l or "rate" in l)), None)
    if start is None:
        return {"items": [], "gross": None, "gross_ok": None, "flags": ["Items header not found"]}
    end = next((i for i in range(start + 1, len(low)) if "gross" in low[i] or "payable" in low[i]), len(lines))

    items, flags = [], []
    for line in lines[start + 1:end]:
        row = parse_row(line)
        if row:
            items.append(row)
            if not row["valid"]:
                flags.append(f"'{row['name']}': rate x qty does not equal amount; check the figures again")
        elif items and line.strip():
            items[-1]["note"] = (items[-1]["note"] + " " + line.strip()).strip()   # Treat the next line as part of the instruction

    gross = None
    for l in lines[end:]:
        if "gross" in l.lower():
            nums = [to_num(t) for t in re.findall(r"\d[\d,]*\.?\d*", l)]
            nums = [n for n in nums if n is not None]
            if nums:
                gross = nums[-1]
            break

    total = sum(i["amount"] for i in items)
    gross_ok = None if gross is None else abs(total - gross) < 1
    if gross is None:
        flags.append("Gross amount not found")
    elif not gross_ok:
        flags.append(f"Items total {total:g}, gross {gross:g}: an item or amount may have been read incorrectly")
    if not items:
        flags.append("No items found")
    return {"items": items, "gross": gross, "gross_ok": gross_ok, "flags": flags}


def show(name, r):
    print(name)
    for n, it in enumerate(r["items"], 1):
        note = f"  [{it['note']}]" if it["note"] else ""
        check = "" if it["valid"] else "   <-- CHECK THE FIGURES"
        print(f"  {n}) {it['name']}  x{it['qty']}   ({it['rate']} x {it['qty']} = {it['amount']}){note}{check}")
    if r["gross"] is not None:
        print(f"  Gross: {r['gross']:g}  ({'items total is correct' if r['gross_ok'] else 'TOTAL DOES NOT MATCH'})")
    for f in r["flags"]:
        print("  !", f)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    target = sys.argv[1]
    if os.path.isdir(target):
        files = sorted(f for f in os.listdir(target) if os.path.splitext(f)[1].lower() in IMG_EXT)
        paths = [os.path.join(target, f) for f in files]
    else:
        paths = [target]

    results, names = {}, Counter()
    for p in paths:
        r = parse_slip(image_to_lines(p))
        key = os.path.splitext(os.path.basename(p))[0]
        results[key] = r
        names.update(it["name"] for it in r["items"])
        show(os.path.basename(p), r)

    if os.path.isdir(target) and results:
        with open(os.path.join(target, "prints.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        with open(os.path.join(target, "menu_from_prints.txt"), "w", encoding="utf-8") as f:
            for name, c in names.most_common():
                f.write(f"{name}  ({c})\n")
        bad = sum(1 for r in results.values() if r["flags"])
        print(f"\n{len(results)} prints processed, {bad} have warnings (flags).")
        print("Files: prints.json, menu_from_prints.txt")


if __name__ == "__main__":
    main()