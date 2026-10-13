import re
from rapidfuzz import fuzz

# Menu items aur un ki spellings (English + Urdu script).
# Jo spelling Whisper likhe wo yahan add karte jayein (accuracy_report.csv mein transcript dikhta hai).
ITEMS = {
    "zinger burger": ["zinger burger", "zinger", "زنگر برگر", "زنگر", "زنجر"],
    "sandwich": ["sandwich", "سینڈوچ", "سنڈویچ", "سینڈویچ", "سیڈویچ", "سنڈوچ", "سینڈ وچ"],
    "fries": ["fries", "فرائز", "فرائیز", "فریز", "فریس", "فرائس"],
    "pizza": ["pizza", "پیزا", "پیتزا"],
    "cold drink": ["cold drink", "کولڈ ڈرنک", "کول ڈرنک", "کولڈرنک", "کولڈ drink"],
    "biryani": ["biryani", "بریانی", "بڑیانی", "بڑیاںی"],
}

NUMS = {
    "ایک": 1, "اک": 1, "ek": 1, "one": 1,
    "دو": 2, "ڈو": 2, "do": 2, "two": 2,
    "تین": 3, "تن": 3, "teen": 3, "three": 3,
    "چار": 4, "char": 4, "four": 4,
    "پانچ": 5, "پانج": 5, "panch": 5, "paanch": 5, "five": 5,
    "چھ": 6, "chay": 6, "chhe": 6, "six": 6,
}

# Whisper ki aam ghaltiyan jo asli recordings mein baar baar aayen to yahan add karein.
# Ehtiyat: har ghalti ko sirf ek recording dekh kar na likhein, warna test recordings par
# accuracy jhooti barh jaye gi.
FIXES = {
    "چارکول": "چار کولڈ ڈرنک",
    "ہول رنگ": "کولڈ ڈرنک",
}

# Customer ne baat badli ("nahi nahi, teen pizza"): is ke baad ka hissa liya jata hai.
CORRECTIONS = {"نہیں", "نہی", "nahi", "nahin"}


def tokenize(text):
    return re.findall(r"\w+", text.lower())


def parse_number(tok):
    if tok in NUMS:
        return NUMS[tok]
    try:
        return int(tok)
    except ValueError:
        return None


def extract_order(transcript, threshold=85):
    text = transcript.lower()
    for bad, good in FIXES.items():
        text = text.replace(bad, good)
    tokens = tokenize(text)

    uncertain = []
    last = max((i for i, t in enumerate(tokens) if t in CORRECTIONS), default=-1)
    if last >= 0 and last + 1 < len(tokens):
        tokens = tokens[last + 1:]
        uncertain.append("customer ne correction ki (nahi), sirf aakhri hissa liya gaya, insaan check kare")

    aliases = sorted(
        ((a, item) for item, al in ITEMS.items() for a in al),
        key=lambda x: -len(x[0].split()),
    )
    used, found = set(), []
    for alias, item in aliases:
        n = len(alias.split())
        for i in range(len(tokens) - n + 1):
            span = range(i, i + n)
            if any(j in used for j in span):
                continue
            if fuzz.ratio(" ".join(tokens[i:i + n]), alias.lower()) >= threshold:
                used.update(span)
                found.append((i, item))

    found.sort()
    items = []
    for start, item in found:
        qty = 1
        for back in (1, 2):
            j = start - back
            if j < 0 or j in used:
                break
            q = parse_number(tokens[j])
            if q is not None:
                qty = q
                break
        items.append({"name": item, "qty": qty})

        # Whisper kabhi jumla dohra deta hai ("do pizza, do pizza"): ek hi item do dafa aaye to
    # ek dafa gina jata hai aur insaan ko check ke liye flag hota hai.
    merged = {}
    for it in items:
        merged.setdefault(it["name"], []).append(it["qty"])
    items = []
    for name, qtys in merged.items():
        if len(qtys) > 1:
            uncertain.append(f"{name} {len(qtys)} dafa suna gaya, insaan check kare")
        items.append({"name": name, "qty": qtys[0] if len(set(qtys)) == 1 else sum(qtys)})
    return {"items": items, "uncertain": uncertain}


if __name__ == "__main__":
    text = "دو زنگر برگر, ایک فریس"
    print(extract_order(text))