from rapidfuzz import process, fuzz

MENU = ["zinger burger", "sandwich", "fries", "pizza", "cold drink", "biryani"]

def normalize(name):
    m = process.extractOne(name.lower().strip(), MENU, scorer=fuzz.WRatio)
    return m[0] if m and m[1] >= 80 else None

def to_dict(items):
    d = {}
    for it in items:
        key = normalize(it["name"]) or "?" + it["name"]
        d[key] = d.get(key, 0) + int(it.get("qty", 1))
    return d

def compare(call_items, punched_items):
    c, p = to_dict(call_items), to_dict(punched_items)
    missing = {k: v for k, v in c.items() if k not in p}   # call mein tha, punch nahi hua
    extra = {k: v for k, v in p.items() if k not in c}     # punch hua, call mein nahi tha
    qty_diff = {k: {"call": c[k], "punched": p[k]} for k in c if k in p and c[k] != p[k]}
    unknown = [k for k in list(c) + list(p) if k.startswith("?")]

    if unknown:
        status = "NEEDS_REVIEW"
    elif missing or extra or qty_diff:
        status = "MISMATCH"
    else:
        status = "MATCH"
    return status, {"missing": missing, "extra": extra, "qty_diff": qty_diff, "unknown": unknown}

if __name__ == "__main__":
    call = [{"name": "zinger burgar", "qty": 2}, {"name": "fries", "qty": 1}, {"name": "cold drink", "qty": 1}]
    punched = [{"name": "zinger burger", "qty": 2}, {"name": "fries", "qty": 2}]
    print(compare(call, punched))