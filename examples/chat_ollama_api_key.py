import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("secrets/.env")

# ==========================================
# Configuration
# ==========================================
# Set these via environment variables for security, or load from file for testing

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com") # Change to your cloud endpoint

def get_api_key(file_path="secrets/keys.txt"):
    """
    Loads the first line (key[0]) from the specified keys file.
    Falls back to an environment variable if the file is not found or is empty.
    """
    try:
        with open(file_path, "r") as f:
            lines = f.read().splitlines()
            if lines:
                return lines[0].strip()
    except FileNotFoundError:
        print(f"Warning: '{file_path}' not found. Falling back to environment variable.")
    
    # Fallback to environment variable (updated to a more logical name)
    return os.getenv("OLLAMA_API_KEY", "")

API_KEY = get_api_key()
MODEL_NAME = "gemma4:31b-cloud"

def chat_with_ollama(prompt, system_prompt="You are a helpful assistant."):
    """
    Sends a chat completion request to the Ollama API.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    
    # Cloud Ollama proxies typically use Bearer token authentication
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False, # Set to True if you want to stream the response token-by-token
        "options": {
            "temperature": 0.7
        }
    }
    
    try:
        print(f"Sending request to {MODEL_NAME}...")
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        
        # Raise an exception if the request failed (e.g., 401 Unauthorized, 404 Not Found)
        response.raise_for_status() 
        
        # Parse the JSON response
        result = response.json()
        
        # Extract the assistant's message content
        assistant_message = result.get("message", {}).get("content", "No response content found.")
        return assistant_message
        
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response body: {response.text}")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the Ollama API. Check your OLLAMA_BASE_URL.")
    except Exception as err:
        print(f"An unexpected error occurred: {err}")
        
    return None

if __name__ == "__main__":
    # Example usage
    user_prompt = "Explain the difference between a cloud-native LLM and a locally hosted one in 3 bullet points."
    
    response_text = chat_with_ollama(user_prompt)
    
    if response_text:
        print("\n--- Assistant Response ---")
        print(response_text)