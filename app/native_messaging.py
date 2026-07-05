import sys
import struct
import json
import asyncio
import traceback

from app.main import semantic_match, hub_add, SemanticMatchRequest, HubJob
from app.workflow.extract import extract_text_from_file
import base64

async def handle_message(msg):
    endpoint = msg.get("endpoint")
    payload = msg.get("payload", {})
    
    if endpoint == "/api/semantic-match":
        req = SemanticMatchRequest(**payload)
        res = await semantic_match(req)
        if hasattr(res, "body"):
            return json.loads(res.body)
        return res
    elif endpoint == "/api/hub/add":
        req = HubJob(**payload)
        res = await hub_add(req)
        if hasattr(res, "body"):
            return json.loads(res.body)
        return res
    elif endpoint == "/api/extract":
        filename = payload.get("filename", "")
        b64data = payload.get("b64data", "")
        if not b64data:
            return {"error": "No file provided"}
        try:
            raw_bytes = base64.b64decode(b64data)
            text = extract_text_from_file(filename, raw_bytes)
            if not text or not text.strip():
                return {"error": "Couldn't read any text from that file."}
            return {"filename": filename, "text": text}
        except Exception as e:
            return {"error": f"Extraction failed: {str(e)}"}
    else:
        return {"error": f"Unknown endpoint: {endpoint}"}

def read_message():
    text_length_bytes = sys.stdin.buffer.read(4)
    if len(text_length_bytes) == 0:
        return None
    message_length = struct.unpack('i', text_length_bytes)[0]
    text = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(text)

def send_message(msg):
    text = json.dumps(msg).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('i', len(text)))
    sys.stdout.buffer.write(text)
    sys.stdout.buffer.flush()

async def run_loop():
    while True:
        try:
            msg = read_message()
            if msg is None:
                break
            
            try:
                result = await handle_message(msg)
                send_message(result)
            except Exception as e:
                send_message({"error": str(e), "trace": traceback.format_exc()})
        except Exception:
            break

def run_native_messaging():
    asyncio.run(run_loop())

if __name__ == "__main__":
    run_native_messaging()
