"""
db.py: database ka poora kaam sirf is file mein hai.

Abhi: SQLite demo (demo.db) aur jhooti test calls (DEMO_SEED).
Asli company DB (Postgres) aane par SIRF is file ke functions dobara likhne honge.
Functions ke naam aur wapas aane wali cheezein wohi rehni chahiyen, taake server.py,
accuracy_check.py ya index.html mein kuch na badalna paray.

Asli DB ke liye in functions ko apne tables ke hisab se likhna hoga:
    list_calls()        sab calls (page ki table ke liye)
    list_orders()       sab orders. "items" hamesha [{"name": "...", "qty": 2}, ...] ki shakal mein
    get_call(id)        ek call (dict) ya None
    get_order(id)       ek order (dict, items ke saath) ya None
    fetch_new_calls()   wo calls jo abhi process nahi hui (asli system ka worker yahi use karega)
    save_transcript()   transcript aur call se nikla order save karna
    create_auto_order() order punch na ho to naya order banana aur call se jodna
    save_result()       match status aur details save karna
    confirm_order()     staff ke confirm par order ka status NEW karna

Dhyan: company ke DB mein order ke items agar alag table mein hon (order_items), to
get_order() aur list_orders() ko un se [{"name", "qty"}] list banani hogi.
Postgres (psycopg2) mein placeholder "?" ki jagah "%s" hota hai.
"""
import json
import os
import sqlite3
from contextlib import contextmanager

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "demo.db")

SCHEMA = """
create table if not exists orders(
  id integer primary key autoincrement,
  customer_phone text, items text, source text, status text);
create table if not exists call_recordings(
  id integer primary key autoincrement,
  order_id integer, customer_phone text, recording_path text,
  transcript text, extracted_items text,
  match_status text, match_details text, processed integer default 0);
"""

# Sirf demo ke liye. Asli system mein ye list nahi hogi, calls DB mein khud aati hain.
DEMO_SEED = [
    ("0300-1234567", "call1.aac", [("zinger burger", 2), ("fries", 1), ("cold drink", 1)]),  # MATCH
    ("0321-7654321", "call2.aac", None),                                                    # AUTO_PUNCHED
    ("0333-1112223", "call3.aac", [("zinger burger", 2), ("fries", 2), ("cold drink", 1)]),  # qty farq
    ("0345-9998887", "call1.aac", [("zinger burger", 2), ("fries", 1), ("sandwich", 1)]),    # missing + extra
]


@contextmanager
def _db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with _db() as c:
        c.executescript(SCHEMA)
        if c.execute("select count(*) from call_recordings").fetchone()[0]:
            return
        for phone, path, items in DEMO_SEED:
            order_id = None
            if items:
                js = json.dumps([{"name": n, "qty": q} for n, q in items])
                cur = c.execute(
                    "insert into orders(customer_phone, items, source, status) values (?,?,?,?)",
                    (phone, js, "staff", "NEW"))
                order_id = cur.lastrowid
            c.execute(
                "insert into call_recordings(order_id, customer_phone, recording_path) values (?,?,?)",
                (order_id, phone, path))


def reset_demo():
    """Sirf demo: tables mita kar test calls dobara banata hai. Asli DB par kabhi nahi chalna chahiye."""
    with _db() as c:
        c.executescript("drop table if exists orders; drop table if exists call_recordings;")
    init_db()


def list_calls():
    with _db() as c:
        return [dict(r) for r in c.execute(
            "select id, customer_phone, recording_path, order_id, processed, match_status "
            "from call_recordings order by id")]


def list_orders():
    with _db() as c:
        rows = [dict(r) for r in c.execute("select * from orders order by id")]
    for r in rows:
        r["items"] = json.loads(r["items"])
    return rows


def get_call(call_id):
    with _db() as c:
        r = c.execute("select * from call_recordings where id=?", (call_id,)).fetchone()
    return dict(r) if r else None


def get_order(order_id):
    with _db() as c:
        r = c.execute("select * from orders where id=?", (order_id,)).fetchone()
    if not r:
        return None
    order = dict(r)
    order["items"] = json.loads(order["items"])
    return order


def fetch_new_calls(limit=50):
    with _db() as c:
        return [dict(r) for r in c.execute(
            "select * from call_recordings where processed=0 order by id limit ?", (limit,))]


def save_transcript(call_id, transcript, items):
    with _db() as c:
        c.execute(
            "update call_recordings set transcript=?, extracted_items=? where id=?",
            (transcript, json.dumps(items, ensure_ascii=False), call_id))


def create_auto_order(call_id, phone, items, status):
    """Call ka order punch nahi tha: naya order banao (source=call_ai) aur call se jodo."""
    with _db() as c:
        cur = c.execute(
            "insert into orders(customer_phone, items, source, status) values (?,?,?,?)",
            (phone, json.dumps(items, ensure_ascii=False), "call_ai", status))
        order_id = cur.lastrowid
        c.execute("update call_recordings set order_id=? where id=?", (order_id, call_id))
    return order_id


def save_result(call_id, status, details):
    with _db() as c:
        c.execute(
            "update call_recordings set match_status=?, match_details=?, processed=1 where id=?",
            (status, json.dumps(details, ensure_ascii=False), call_id))


def confirm_order(order_id):
    with _db() as c:
        c.execute("update orders set status='NEW' where id=? and source='call_ai'", (order_id,))