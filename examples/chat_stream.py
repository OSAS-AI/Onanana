import requests

WARP_URL = "http://localhost:11435/api/chat"
MODEL = "gemma4:31b-cloud"
MESSAGES = [{"role": "user", "content": "hello"}]


def main():
    payload = {"model": MODEL, "messages": MESSAGES, "stream": False}

    resp = requests.post(WARP_URL, json=payload, timeout=None)
    if resp.status_code != 200:
        print(f"Error: {resp.status_code} {resp.text}")
        return

    data = resp.json()
    content = data.get("message", {}).get("content", "")
    print(content)


if __name__ == "__main__":
    main()
