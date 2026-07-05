import os

# Force mock mode so tests never hit a real LLM API (no key, deterministic output).
os.environ["FORCE_MOCK"] = "1"
