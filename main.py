import os
import json
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("AI_API_KEY"), base_url="https://api.groq.com/openai/v1")

app = FastAPI()

class ChatRequest(BaseModel):
    category: str
    topic: str
    difficulty: int # 1~10
    message: str

@app.post("/chat")
async def chat_with_ai(request: ChatRequest):
    system_instruction = f"""
        너는 "{request.category}"의 "{request.topic}"을 배우는 17살 학생이야.
        유저의 설명을 듣고 피드백을 줘.

        [규칙]
        중요!! - "{request.category}"의 "{request.topic}"에 관하여 유저가 설명을 시작할 수 있게 "{request.difficulty}" (1~10정도 난이도)에 맞게 질문으로 대화를 시작해줘.
        1. 모르는 건 날카롭게 질문하고, 잘 설명하면 점수를 올려.
        2. 답변은 반드시 아래의 JSON 형식으로만 해. 다른 말은 하지 마.
        {{
            "reply": "네가 학생으로서 할 말",
            "score": 0~100 사이의 숫자(난이도에 따라 점수주는 기준을 더 엄격하게),
            "is_finished": true/false (이해도가 100이면 true)
        }}
        """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
        messages=[ {"role": "system", "content": system_instruction}, {"role": "user", "content": request.message}]
    )

    result = json.loads(response.choices[0].message.content)
    return result