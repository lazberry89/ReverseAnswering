import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

load_dotenv()

# ==========================================
# 🤖 AI 클라이언트 설정
# ==========================================
groq_client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

gemini_client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 🗄️ 임시 DB
# ==========================================
db_users = {}
db_profiles = {}
db_community = []

MAX_HISTORY = 10
user_sessions = {}


# ==========================================
# 📦 데이터 모델
# ==========================================
class UserAuth(BaseModel):
    user_id: str
    password: str


class UserProfile(BaseModel):
    user_id: str
    age: int
    school: str


class CommunityPost(BaseModel):
    user_id: str
    content: str
    score: int


class ChatRequest(BaseModel):
    user_id: str
    category: str
    topic: str
    difficulty: int
    age: int
    lang: str
    model_type: str = "groq"
    message: str


# ==========================================
# 🚀 API 엔드포인트들
# ==========================================
@app.get("/")
async def read_index():
    return FileResponse('index.html')


@app.post("/register")
async def register(auth: UserAuth):
    if auth.user_id in db_users:
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")
    db_users[auth.user_id] = auth.password
    return {"message": "회원가입 성공!"}


@app.post("/login")
async def login(auth: UserAuth):
    if auth.user_id not in db_users or db_users[auth.user_id] != auth.password:
        raise HTTPException(status_code=401, detail="아이디나 비밀번호가 틀렸습니다.")
    return {"message": "로그인 성공!", "user_id": auth.user_id}


@app.post("/profile")
async def save_profile(profile: UserProfile):
    if profile.user_id not in db_users:
        raise HTTPException(status_code=404, detail="가입되지 않은 유저입니다.")
    db_profiles[profile.user_id] = {"age": profile.age, "school": profile.school}
    return {"message": "프로필 저장 완료!", "data": db_profiles[profile.user_id]}


@app.get("/profile/{user_id}")
async def get_profile(user_id: str):
    if user_id not in db_profiles:
        raise HTTPException(status_code=404, detail="프로필이 없습니다.")
    return db_profiles[user_id]


@app.post("/community")
async def create_post(post: CommunityPost):
    db_community.insert(0, {"user_id": post.user_id, "content": post.content, "score": int(post.score)})
    return {"message": "자랑글이 등록되었습니다!"}


@app.get("/community")
async def get_posts():
    return {"posts": db_community}


# ==========================================
# 🚀 4. 역질문 AI 채팅 API
# ==========================================
@app.post("/chat")
async def chat_with_ai(request: ChatRequest):
    # 주제(Topic)가 바뀌었는지 확인하여 세션 강제 초기화
    should_reset = False
    if request.user_id in user_sessions:
        if user_sessions[request.user_id].get("topic") != request.topic:
            should_reset = True

    if request.user_id not in user_sessions or should_reset:
        system_instruction = f"""
            너는 "{request.category}"의 "{request.topic}"을 배우는 {request.age}살 학생이야.
            유저의 설명을 듣는 학생 입장에서 질문을 해야 돼.
            [규칙]
            - 언어는 "{request.lang}"을 기본으로 사용할 것(한자나 다른 언어로 깨지지 않도록 유의).
            - 난이도 {request.difficulty}/10에 맞춰서 기초적인 질문부터 시작해.
            - 직접 개념 설명을 하지 말고, 질문을 통해 유저의 설명을 유도해.
            !!!절대 너가 원래의 AI어시스턴트의 역할이 되면 안돼. 무조건 넌 학생의 역할로, 질문과 반응만 해야돼.
            - 답변은 반드시 아래 JSON 형식으로만 해.
            [점수 산출 규칙 - 중요!!]
            - 'score'는 유저의 현재 설명 수준에 대한 실시간 이해도 점수(0~100)이다.
            - 유저가 핵심 개념을 잘 설명하면 점수를 올려라.
            - 유저가 틀린 설명을 하거나, 횡설수설하거나, 중복된 내용을 반복하면 점수를 가차 없이 깎아라.
            - 점수는 유저의 답변 질에 따라 유동적으로 오르락내리락할 수 있다.
            - 최종적으로 모든 개념이 완벽히 설명되어 이해도가 100이 되면 'is_finished'를 true로 바꿔라.
            {{
                "reply": "학생으로서 할 말",
                "score": 0~100,
                "is_finished": true/false,
                "hint": "유저가 설명을 어려워할 때 줄 수 있는 힌트 (없으면 빈칸)"
            }}
        """
        user_sessions[request.user_id] = {
            "messages": [{"role": "system", "content": system_instruction}],
            "msg_count": 0,
            "topic": request.topic
        }

    session = user_sessions[request.user_id]
    session["msg_count"] += 1

    if len(session["messages"]) > MAX_HISTORY:
        session["messages"].pop(1)

    user_msg = request.message
    # 10번째 메시지마다 힌트 유도
    should_show_hint = (session["msg_count"] % 10 == 0)
    if should_show_hint:
        user_msg += "\n(시스템: 유저가 설명을 어려워하고 있습니다. 다음 JSON 응답의 'hint' 필드에 구체적인 학습 힌트를 포함해주세요.)"

    session["messages"].append({"role": "user", "content": user_msg})

    if request.model_type == "gemini":
        target_client = gemini_client
        target_model = "gemini-2.5-flash" #모델명 절대 바꾸지 않기 AI추천 모델은 틀린버젼
    else:
        target_client = groq_client
        target_model = "llama-3.3-70b-versatile"

    try:
        response = target_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=session["messages"]
        )
        ai_raw_response = response.choices[0].message.content
        
        # [추가] 응답이 bytes일 경우 utf-8 디코딩 처리
        if isinstance(ai_raw_response, bytes):
            ai_raw_response = ai_raw_response.decode('utf-8')
            
        session["messages"].append({"role": "assistant", "content": ai_raw_response})

        result = json.loads(ai_raw_response)

        # 점수 처리 (실시간 점수 반영 및 0~100 제한)
        try:
            raw_score = int(result.get("score", 0))
            result["score"] = max(0, min(100, raw_score))
        except:
            result["score"] = 0

        result["show_hint_button"] = should_show_hint
        result["hint"] = result.get("hint", "")

        # 종료 처리
        if result["score"] >= 100 or result.get("is_finished") is True:
            result["is_finished"] = True

        return result
    except Exception as e:
        return {"reply": f"에러 발생: {str(e)}", "score": 0, "is_finished": False, "show_hint_button": False}


@app.get("/reset/{user_id}")
async def reset_session(user_id: str):
    if user_id in user_sessions:
        del user_sessions[user_id]
        return {"message": "대화 세션이 초기화되었습니다."}
    return {"message": "초기화할 세션이 없습니다."}
