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

def setup_native_messaging_host():
    """Automates the installation of the Chrome Native Messaging Host manifest."""
    import os, platform
    ext_id = "bbgacjcfjkmfcacimbkhelodlnegboej"
    
    if sys.platform == "darwin":
        host_dir = os.path.expanduser("~/.resopt")
    elif os.name == "nt":
        host_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "resopt")
    else:
        host_dir = os.path.expanduser("~/.resopt")
        
    os.makedirs(host_dir, exist_ok=True)
    
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        exe_path = os.path.abspath(sys.argv[0])

    is_windows = (os.name == "nt")
    wrapper_path = os.path.join(host_dir, "resopt-native-host.bat" if is_windows else "resopt-native-host")
    json_path = os.path.join(host_dir, "com.praneeth.resopt.json")

    if is_windows:
        with open(wrapper_path, "w") as f:
            f.write("@echo off\n")
            f.write(f'"{exe_path}" --native\n')
    else:
        with open(wrapper_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f'"{exe_path}" --native\n')
        os.chmod(wrapper_path, 0o755)

    manifest = {
        "name": "com.praneeth.resopt",
        "description": "RESOPT Native Messaging Host",
        "path": wrapper_path,
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"]
    }
    
    with open(json_path, "w") as f:
        json.dump(manifest, f, indent=2)

    try:
        if is_windows:
            import winreg
            key_paths = [
                r"Software\Google\Chrome\NativeMessagingHosts\com.praneeth.resopt",
                r"Software\Microsoft\Edge\NativeMessagingHosts\com.praneeth.resopt",
                r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\com.praneeth.resopt"
            ]
            for kp in key_paths:
                try:
                    winreg.CreateKey(winreg.HKEY_CURRENT_USER, kp)
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, kp, 0, winreg.KEY_WRITE)
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, json_path)
                    winreg.CloseKey(key)
                except Exception:
                    pass
        elif sys.platform == "darwin":
            import shutil
            chrome_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome/NativeMessagingHosts")
            edge_dir = os.path.expanduser("~/Library/Application Support/Microsoft Edge/NativeMessagingHosts")
            brave_dir = os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts")
            for d in [chrome_dir, edge_dir, brave_dir]:
                os.makedirs(d, exist_ok=True)
                shutil.copy(json_path, os.path.join(d, "com.praneeth.resopt.json"))
    except Exception as e:
        print(f"Failed to install native messaging host automatically: {e}")
