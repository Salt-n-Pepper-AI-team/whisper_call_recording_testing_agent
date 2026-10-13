import sys
from faster_whisper import WhisperModel
from extract import extract_order
from compare import compare

AUDIO = sys.argv[1] if len(sys.argv) > 1 else "call1.aac"
MENU_PROMPT = "zinger burger, sandwich, fries, pizza, cold drink, biryani"

# Abhi test ke liye punched order yahan likha hai. Asli data aane par ye DB se aayega.
PUNCHED = [
    {"name": "zinger burger", "qty": 2},
    {"name": "fries", "qty": 2},
]


print("Whisper model is loading...")
model = WhisperModel("medium", device="cpu", compute_type="int8")

def transcribe(path):
    segments, info = model.transcribe(
        path, language="ur", initial_prompt=MENU_PROMPT, vad_filter=True
    )
    return " ".join(s.text for s in segments)

if __name__ == "__main__":
    transcript = transcribe(AUDIO)
    print("\nTranscript:", transcript)

    call_order = extract_order(transcript)
    print("\nCall se nikla order:", call_order["items"])
    print("Punched order:     ", PUNCHED)

    status, details = compare(call_order["items"], PUNCHED)
    if call_order["uncertain"] and status == "MATCH":
        status = "NEEDS_REVIEW"

    print("\nResult:", status)
    print("Details:", details)