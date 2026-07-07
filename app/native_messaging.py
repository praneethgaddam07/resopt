import sys
import struct
import json
import traceback
import urllib.request
import os

def handle_message(msg):
    endpoint = msg.get("endpoint")
    payload = msg.get("payload", {})
    
    # Forward the message via HTTP to the running RESOPT app server
    url = f"http://127.0.0.1:47615{endpoint}"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body)
    except Exception as e:
        return {"error": f"Native proxy HTTP error: {str(e)}"}

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

def run_loop():
    while True:
        try:
            msg = read_message()
            if msg is None:
                break
            
            try:
                result = handle_message(msg)
                send_message(result)
            except Exception as e:
                send_message({"error": str(e), "trace": traceback.format_exc()})
        except Exception:
            break

def run_native_messaging():
    run_loop()

if __name__ == "__main__":
    run_native_messaging()

def setup_native_messaging_host():
    """Automates the installation of the Chrome Native Messaging Host manifest."""
    import platform
    ext_id = "ajghgjkgdfmijbhgicclkfmebgnjdagi"
    
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
        # On macOS, using the raw binary causes the Dock icon to bounce.
        # Instead of calling the PyInstaller binary, we write a pure lightweight Python proxy script.
        proxy_script = """#!/usr/bin/env python3
import sys, struct, json, urllib.request, traceback

def handle_message(msg):
    endpoint = msg.get("endpoint")
    payload = msg.get("payload", {})
    url = f"http://127.0.0.1:47615{endpoint}"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        return {"error": str(e)}

def main():
    while True:
        length_bytes = sys.stdin.buffer.read(4)
        if not length_bytes: break
        length = struct.unpack('i', length_bytes)[0]
        text = sys.stdin.buffer.read(length).decode('utf-8')
        result = handle_message(json.loads(text))
        out_text = json.dumps(result).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('i', len(out_text)))
        sys.stdout.buffer.write(out_text)
        sys.stdout.buffer.flush()

if __name__ == '__main__':
    main()
"""
        with open(wrapper_path, "w") as f:
            f.write(proxy_script)
        os.chmod(wrapper_path, 0o755)

    manifest = {
        "name": "com.praneeth.resopt",
        "description": "RESOPT Native Messaging Host",
        "path": wrapper_path,
        "type": "stdio",
        "allowed_origins": [
            f"chrome-extension://{ext_id}/",
            "chrome-extension://ldeknffakfmipaaddgkkgblldmdofhea/"
        ]
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
