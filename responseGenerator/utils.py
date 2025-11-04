import redis
import json

# utils/webhook_utils.py
import requests


def get_user_chat(user_id: str, chat_id: str):
    """Retrieve a specific chat record from Redis using user_id and chat_id."""
    r = redis.Redis(host="localhost", port=6379, db=1)
    key = f"llmChat:{user_id}:{chat_id}"

    # Fetch the hash directly
    data = r.hgetall(key)

    if not data:
        return None  # Chat not found

    # Decode byte values to strings
    data = {k.decode(): v.decode() for k, v in data.items()}
    data["chat_id"] = chat_id
    data["llm_object"] = json.loads(data["llm_object"])

    return data


def send_webhook(url, payload):
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            url, data=json.dumps(payload), headers=headers, timeout=5
        )
        response.raise_for_status()
        print(f"✅ Webhook sent successfully to {url}")
    except requests.RequestException as e:
        print(f"❌ Failed to send webhook: {e}")
