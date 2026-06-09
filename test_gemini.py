import os
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


# A sample of the system instruction that might be built in context
system_instruction = """\
Ban la Em Linh — chuyen gia ho tro chien luoc kinh doanh nen tang so cho dealer cua nhom kinh / cua cuon / tu bep / VLXD Viet Nam.
VAITRO: Thu data dealer qua tro chuyen tu nhien.
PERSONA: Em xung "em", goi dealer "anh". Toi da 1 emoji/reply.
TASK: Moi anh xem lai ho so va bam xac nhan.
"""

contents = [
    types.Content(role="user", parts=[types.Part(text="ủa hết rồi à")])
]

response = client.models.generate_content(
    model="gemini-3.1-flash-lite",
    contents=contents,
    config=types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=0.6,
        max_output_tokens=512,
    )
)

print("Response status:")
print("text:", repr(response.text))
print("candidates:", response.candidates)
print("prompt_feedback:", response.prompt_feedback)
