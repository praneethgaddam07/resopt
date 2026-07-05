#!/bin/bash
# RESOPT Native Messaging Host Installer for macOS

echo "================================================="
echo "RESOPT Native Messaging Host Installer"
echo "================================================="
echo "To connect the RESOPT Chrome extension to the desktop app,"
echo "we need your Extension ID. You can find this by:"
echo "1. Opening Chrome and going to chrome://extensions/"
echo "2. Finding the RESOPT extension"
echo "3. Copying the ID (e.g., abcdefghijklmnopqrstuvwxyz)"
echo ""
read -p "Enter your Chrome Extension ID: " EXT_ID

if [ -z "$EXT_ID" ]; then
    echo "Extension ID is required. Exiting."
    exit 1
fi

HOST_DIR="$HOME/.resopt"
mkdir -p "$HOST_DIR"

WRAPPER_SCRIPT="$HOST_DIR/resopt-native-host"
cat << 'EOF' > "$WRAPPER_SCRIPT"
#!/bin/bash
/Applications/RESOPT.app/Contents/MacOS/RESOPT --native
EOF
chmod +x "$WRAPPER_SCRIPT"

JSON_FILE="$HOST_DIR/com.praneeth.resopt.json"
cat << EOF > "$JSON_FILE"
{
  "name": "com.praneeth.resopt",
  "description": "RESOPT Native Messaging Host",
  "path": "$WRAPPER_SCRIPT",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://$EXT_ID/"
  ]
}
EOF

# Install for Chrome
CHROME_DIR="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
mkdir -p "$CHROME_DIR"
cp "$JSON_FILE" "$CHROME_DIR/"

# Install for Brave
BRAVE_DIR="$HOME/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts"
mkdir -p "$BRAVE_DIR"
cp "$JSON_FILE" "$BRAVE_DIR/"

# Install for Edge
EDGE_DIR="$HOME/Library/Application Support/Microsoft Edge/NativeMessagingHosts"
mkdir -p "$EDGE_DIR"
cp "$JSON_FILE" "$EDGE_DIR/"

echo ""
echo "✅ Successfully installed!"
echo "The extension should now be able to communicate with the RESOPT desktop app."
echo "Please restart Chrome if it is currently running."
