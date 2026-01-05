import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dotenv import load_dotenv

def main():
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")
    base_url = os.getenv("BASE_URL")

    print("=== Chat with AI ===")
    print("Type 'exit' or 'quit' to end the conversation\n")

    while True:
        # Get user question
        question = input("You: ").strip()

        if question.lower() in ['exit', 'quit']:
            print("Goodbye!")
            break

        if not question:
            continue

        # Create request body with user's question
        request_body = create_request_body(question)

        # Generate timestamp and request ID
        timestamp = time.time() * 1000
        request_id = uuid.uuid4()

        # Create HMAC signature
        hmac_signature = create_hmac_signature(request_body, api_key, api_secret, timestamp, request_id)

        # Send request and get response
        try:
            api_response = send_request(request_body, hmac_signature, base_url, api_key, timestamp, request_id)
            print(f"\nAI: {api_response}\n")
        except Exception as e:
            print(f"\nError: {e}\n")

def create_request_body(question):
    body = {
        "messages": [
            {
                "content": "You are a helpful assistant.",
                "role": "system"
            },
            {
                "content": question,
                "role": "user"
            }
        ],
        "frequency_penalty": 0,
        "max_tokens": 1000,
        "n": 1,
        "presence_penalty": 0,
        "response_format": {
            "type": "text"
        },
        "stream": False,
        "temperature": 1,
        "top_p": 1
    }
    return body

def create_hmac_signature(request_body, api_key, api_secret, timestamp, request_id):
    hmacSourceData = api_key + str(request_id) + str(timestamp) + json.dumps(request_body)
    computedHash = hmac.new(api_secret.encode(), hmacSourceData.encode(), hashlib.sha256)
    computedHmac = base64.b64encode(computedHash.digest()).decode()
    return computedHmac

def send_request(request_body, hmac_signature, base_url, api_key, timestamp, request_id):
    import requests

    path = "/chat/completions"
    url = base_url + path

    headers = {
        "api-key": api_key,
        "Client-Request-Id": str(request_id),
        "Timestamp": str(timestamp),
        "Authorization": hmac_signature,
        "Accept": "application/json",
    }

    response = requests.request("POST", url, headers=headers, json=request_body)

    if response.status_code != 200:
        raise Exception(f"API returned status code {response.status_code}: {response.text}")

    js = response.json()
    return js['choices'][0]['message']['content']

if __name__ == "__main__":
    main()