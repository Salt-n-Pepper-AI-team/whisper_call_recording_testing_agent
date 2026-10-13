"""
server.py: UI ko asli pipeline (Whisper + extract + compare) se jodta hai.
Database ka sara kaam db.py mein hai, yahan koi SQL nahi.

Chalane ka tareeqa:
    pip install flask
    python server.py
Phir browser mein kholein: http://127.0.0.1:5000

Is folder mein ye files saath honi chahiyen:
    server.py, db.py, index.html, pipeline.py, extract.py, compare.py, call1.aac
"""
import os
import threading

from flask import Flask, abort, jsonify, send_file, send_from_directory

import db
from pipeline import transcribe      # Whisper model yahan ek dafa load hota hai
from extract import extract_order
from compare import compare

BASE = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)
whisper_lock = threading.Lock()           # CPU par ek waqt mein ek hi transcription
_transcript_cache = {}                    # demo mein ek hi file baar baar use hoti hai, is liye cache


def need_call(call_id):
    call = db.get_call(call_id)
    if not call:
        abort(404)
    return call


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/api/state")
def state():
    return jsonify(calls=db.list_calls(), orders=db.list_orders())


@app.post("/api/reset")
def reset():
    db.reset_demo()
    return jsonify(ok=True)


@app.get("/audio/<int:cid>")
def audio(cid):
    call = need_call(cid)
    path = os.path.join(BASE, call["recording_path"])
    if not os.path.exists(path):
        abort(404)
    return send_file(path)


@app.post("/api/transcribe/<int:cid>")
def api_transcribe(cid):
    """Step 1: recording, Whisper transcript, call se order nikalna."""
    call = need_call(cid)
    path = os.path.join(BASE, call["recording_path"])
    if not os.path.exists(path):
        return jsonify(error=f"Recording nahi mili: {call['recording_path']}"), 404

    with whisper_lock:
        if path not in _transcript_cache:
            _transcript_cache[path] = transcribe(path)
        transcript = _transcript_cache[path]

    parsed = extract_order(transcript)
    db.save_transcript(cid, transcript, parsed["items"])
    return jsonify(transcript=transcript, items=parsed["items"], uncertain=parsed["uncertain"])


@app.post("/api/verify/<int:cid>")
def api_verify(cid):
    """Step 2: punched order se compare (ya order punch na ho to auto-punch)."""
    call = need_call(cid)
    if call["transcript"] is None:
        return jsonify(error="Pehle transcribe karein"), 400

    parsed = extract_order(call["transcript"])

    if call["order_id"]:
        order = db.get_order(call["order_id"])
        status, details = compare(parsed["items"], order["items"])
        if parsed["uncertain"] and status == "MATCH":
            status = "NEEDS_REVIEW"
        order_info = {"id": order["id"], "source": order["source"],
                      "status": order["status"], "items": order["items"], "auto": False}
    else:
        order_status = "NEEDS_REVIEW" if (parsed["uncertain"] or not parsed["items"]) else "PENDING_CONFIRMATION"
        oid = db.create_auto_order(cid, call["customer_phone"], parsed["items"], order_status)
        status, details = "AUTO_PUNCHED", {"order_status": order_status}
        order_info = {"id": oid, "source": "call_ai", "status": order_status,
                      "items": parsed["items"], "auto": True}

    db.save_result(cid, status, details)
    return jsonify(status=status, details=details, order=order_info, uncertain=parsed["uncertain"])


@app.post("/api/confirm/<int:oid>")
def confirm(oid):
    """Staff auto-punched order ko confirm karta hai, phir wo kitchen ke liye NEW ho jata hai."""
    db.confirm_order(oid)
    return jsonify(ok=True)


if __name__ == "__main__":
    db.init_db()
    print("\nServer chal gaya: http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)