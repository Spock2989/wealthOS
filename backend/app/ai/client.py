import os
from dotenv import load_dotenv
import anthropic

load_dotenv()

def call_llm(prompt):
    key = os.getenv("ANTHROPIC_API_KEY")
    c = anthropic.Anthropic(api_key=key)
    m = c.messages.create(model="claude-sonnet-4-20250514", max_tokens=1024, messages=[{"role": "user", "content": prompt}])
    return m.content[0].text
