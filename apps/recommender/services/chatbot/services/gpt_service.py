import httpx
import os
from dotenv import load_dotenv
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

async def call_openai_gpt(messages):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            json={"model": "gpt-3.5-turbo", "messages": messages},
            timeout=15
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
