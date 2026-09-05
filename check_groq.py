"""
check_groq.py - standalone diagnostic. Makes exactly one direct call to the
Groq API and prints the real result or error immediately, instead of it
being buried inside 3 retries x dozens of pipeline call-sites.

Usage:
    python check_groq.py
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

api_key = os.environ.get("GROQ_API_KEY")
model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

print(f"GROQ_API_KEY set: {bool(api_key)}")
if api_key:
    print(f"  key prefix: {api_key[:8]}...")
print(f"Model: {model}\n")

if not api_key:
    print("No GROQ_API_KEY in environment. If you have a .env file, this script "
          "doesn't auto-load it - run `export GROQ_API_KEY=...` first, or "
          "`pip install python-dotenv` and load it before running.")
    sys.exit(1)

try:
    from groq import Groq
except ImportError:
    print("groq package not installed. Run: pip install groq")
    sys.exit(1)

client = Groq(api_key=api_key)

print("Making one test call...")
try:
    response = client.chat.completions.create(
        model=model,
        max_tokens=256,
        messages=[
            {"role": "system", "content": "Respond ONLY with valid JSON, no markdown."},
            {"role": "user", "content": 'Say hello. Respond with {"msg": "..."}'},
        ],
        response_format={"type": "json_object"},
    )
    print("\nSUCCESS")
    print("Response:", response.choices[0].message.content)
    print("Tokens used:", response.usage.prompt_tokens, "in /", response.usage.completion_tokens, "out")
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}")
    print(str(e))
    print("\nCommon causes:")
    print("  - 401/invalid_api_key: key is wrong, expired, or has a typo/quote left in .env")
    print("  - 404/model_not_found or model_decommissioned: the model name is wrong or retired")
    print(f"    -> if so, try GROQ_MODEL=openai/gpt-oss-120b (current recommendation as of Sept 2026)")
    print("  - 429: rate limited, wait and retry")
    print("  - connection/timeout: network/firewall is blocking api.groq.com")
