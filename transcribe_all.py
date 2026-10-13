"""
transcribe_all.py: Transcribes all recordings in real_calls using Whisper once and stores them in a local cache.

It is designed to run overnight (laptop plugged into the charger, sleep disabled). If it stops midway or you press Ctrl+C,
there is no problem: the cache is saved after each call, and when you run it again, it skips the calls that are already done.
The transcript is not printed on the screen. It is saved locally only in <folder>\\transcripts_cache.json
(accuracy_check.py also uses this same cache, so Whisper will not run again).

How to run:
    python transcribe_all.py real_calls
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(errors="replace")

from pipeline import transcribe      # The Whisper model is loaded here

AUDIO_EXT = {".aac", ".m4a", ".mp3", ".wav", ".amr", ".ogg", ".opus"}
folder = next((a for a in sys.argv[1:] if not a.startswith("--")), "real_calls")
cache_path = os.path.join(folder, "transcripts_cache.json")


def save(cache):
    tmp = cache_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, cache_path)


def main():
    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)

    files = sorted(f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in AUDIO_EXT)
    todo = []
    for fname in files:
        key = f"{fname}:{os.path.getmtime(os.path.join(folder, fname))}"
        if key not in cache:
            todo.append((fname, key))
    print(f"{len(files)} recordings found, {len(files) - len(todo)} already completed, {len(todo)} remaining.")

    started = time.time()
    try:
        for n, (fname, key) in enumerate(todo, 1):
            t0 = time.time()
            cache[key] = transcribe(os.path.join(folder, fname))
            save(cache)
            avg = (time.time() - started) / n
            left = avg * (len(todo) - n)
            print(f"[{n}/{len(todo)}] {fname}  {time.time() - t0:.0f}s  (estimated time remaining: {left / 60:.0f} minutes)")
    except KeyboardInterrupt:
        print("\nStopped. All work completed so far has been saved; running it again will resume from where it left off.")
        return
    print("\nAll recordings completed.")


if __name__ == "__main__":
    main()