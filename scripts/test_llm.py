from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from coder.llm import chat_json, get_client  # noqa: E402

client = get_client()
print("base_url:", client.base_url)
try:
    result = chat_json(client, "deepseek-chat", 'Верни json: {"ok": true}')
    print("result:", result)
except Exception as e:
    print("ERROR:", type(e).__name__, e)
