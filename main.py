import os
import json
import sqlite3
import random
import httpx
import uvicorn
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

# AI 설정
groq_client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
gemini_client = OpenAI(api_key=os.getenv("GEMINI_API_KEY"),
                       base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

DB_PATH = "tutor.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, password TEXT, email TEXT, provider TEXT DEFAULT "local")')
    c.execute('CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, age INTEGER, school TEXT)')
    c.execute(
        'CREATE TABLE IF NOT EXISTS chat_rooms (room_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, topic TEXT, category TEXT, created_at TEXT)')
    c.execute(
        'CREATE TABLE IF NOT EXISTS messages (msg_id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER, role TEXT, content TEXT, score INTEGER, timestamp TEXT)')
    # 🏆 커뮤니티 테이블 추가
    c.execute(
        'CREATE TABLE IF NOT EXISTS community (post_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, content TEXT, score INTEGER, timestamp TEXT)')
    conn.commit()
    conn.close()


# 서버 시작 시 DB 초기화
init_db()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class ChatRequest(BaseModel):
    user_id: str
    room_id: Optional[int] = None
    category: str
    topic: str
    difficulty: int
    age: int
    lang: str = "Korean"
    model_type: str = "groq"
    message: str

class CommunityPost(BaseModel):
    user_id: str
    content: str
    score: int

@app.get("/")
async def read_index(): return FileResponse('index.html')


@app.get("/login")
async def read_login(): return FileResponse('login.html')


@app.get("/register")
async def read_register(): return FileResponse('register.html')


app.mount("/static", StaticFiles(directory="."), name="static")


@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest):
    db = get_db()
    room_id = req.room_id
    try:
        # 1. 방이 없으면 생성
        if not room_id:
            cursor = db.execute("INSERT INTO chat_rooms (user_id, topic, category, created_at) VALUES (?, ?, ?, ?)",
                                (req.user_id, req.topic, req.category, datetime.now().isoformat()))
            room_id = cursor.lastrowid
            db.commit()

        # 2. 히스토리 가져오기 (마지막 10개)
        history_rows = db.execute("SELECT role, content FROM messages WHERE room_id=? ORDER BY timestamp DESC LIMIT 10",
                                  (room_id,)).fetchall()

        history = []
        for row in reversed(history_rows):
            content = row["content"]
            if row["role"] == "assistant":
                try:
                    content = json.loads(content).get("reply", content)
                except:
                    pass
            history.append({"role": row["role"], "content": content})

        # 누적 점수 가져오기
        last_score_row = db.execute(
            "SELECT score FROM messages WHERE room_id=? AND role='assistant' ORDER BY timestamp DESC LIMIT 1",
            (room_id,)).fetchone()
        current_score = last_score_row["score"] if last_score_row else 0

        # 시스템 프롬프트
        system_instruction = f"""
                너는 {req.category} {req.topic}을 배우는 {req.age}살 학생이야. {req.lang} 언어를 사용하여 말하도록해.
                {req.difficulty}/10 에 맞는 난이도로 점수를 주면돼.
                !!!넌 무조건 학생이야.유저는 선생님이고.넌 아무것도 모르는거고,유저가 알려주는 입장이야.
                !!!그리고 내용이 틀렸더라도 절대 너가 알려주지마. 질문으로 유도해.
                !!!유저가 질문했다고 해서 절대 알려주지마.넌 학생이야.AI어시스턴트가 아니라고
                [중요: 누적 점수 규칙]
                현재 유저의 누적 점수는 **{current_score}점**이야.
                !!!누적점수는 음수가 될 수 없어.0점이라면 감점을 하지마.
                - 설명이 아주 명쾌하고 이해가 잘 되면: +10~15점
                - 설명이 맞긴 하지만 조금 부족하면: +3~5점
                - 틀린 사실을 말하거나 횡설수설하면: -10~20점 차감
                - 난이도({req.difficulty}/10)가 높을수록 오답 시 더 크게 차감해.
        
                !!! 점수 'score' 는 {current_score}에서 위 계산을 적용한 "결과값"을 숫자로만 적어.
                !!! 점수 'score' 가 100이상이라면 'is_finished'를 true로 바꾸고, 마무리 멘트를 하도록 해.

                반드시 다음 JSON 형식으로만 답해: 
                {{"reply": "질문 내용", "score": 최종누적점수, "is_finished": true/false, "hint": "힌트"}}
                """

        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(history)
        messages.append({"role": "user", "content": req.message})

        target_client = gemini_client if req.model_type == "gemini" else groq_client
        target_model = "gemini-2.0-flash" if req.model_type == "gemini" else "llama-3.3-70b-versatile"

        response = target_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=messages
        )

        ai_raw = response.choices[0].message.content
        result = json.loads(ai_raw)

        # [보완] 점수 강제 가드 및 종료 조건 확인
        final_score = result.get("score", 0)
        # 점수가 100점 이상이면 무조건 종료로 간주
        if final_score >= 100:
            final_score = 100
            result["is_finished"] = True
        elif final_score < 0:
            final_score = 0
            
        result["score"] = final_score

        # 5. DB 저장
        now = datetime.now().isoformat()
        db.execute("INSERT INTO messages (room_id, role, content, score, timestamp) VALUES (?, 'user', ?, 0, ?)",
                   (room_id, req.message, now))
        db.execute("INSERT INTO messages (room_id, role, content, score, timestamp) VALUES (?, 'assistant', ?, ?, ?)",
                   (room_id, ai_raw, final_score, now))
        db.commit()

        result["room_id"] = room_id
        return result

    except Exception as e:
        print(f"🔥 서버 에러 발생: {e}")
        return JSONResponse(status_code=500, content={"reply": f"에러: {str(e)}", "score": 0})
    finally:
        db.close()

@app.post("/api/login")
async def login(auth: dict):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE (user_id=? OR email=?) AND provider='local'",
                      (auth['user_id'], auth['user_id'])).fetchone()
    db.close()
    if not user or user["password"] != auth['password']: raise HTTPException(status_code=401,
                                                                             detail="아이디/이메일 또는 비밀번호가 틀렸습니다.")
    return {"user_id": user["user_id"]}


@app.post("/api/register")
async def register(auth: dict):
    db = get_db()
    try:
        db.execute("INSERT INTO users (user_id, password, email, provider) VALUES (?, ?, ?, 'local')",
                   (auth['user_id'], auth['password'], auth['email']))
        db.commit()
        return {"message": "성공"}
    except:
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디나 이메일입니다.")
    finally:
        db.close()


@app.get("/api/history/{user_id}")
async def get_history(user_id: str):
    db = get_db()
    rooms = db.execute("SELECT * FROM chat_rooms WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rooms]


@app.get("/api/chat_data/{room_id}")
async def get_chat_data(room_id: int):
    db = get_db()
    msgs = db.execute("SELECT role, content, score FROM messages WHERE room_id=? ORDER BY timestamp ASC",
                      (room_id,)).fetchall()
    db.close()
    return [dict(m) for m in msgs]


@app.post("/api/profile")
async def save_profile(data: dict):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?)", (data["user_id"], data["age"], data["school"]))
    db.commit()
    db.close()
    return {"message": "저장 완료"}


@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    db = get_db()
    p = db.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    db.close()
    return dict(p) if p else {"age": 17, "school": "미입력"}


@app.delete("/api/chat/room/{room_id}")
async def delete_room(room_id: int):
    db = get_db()
    db.execute("DELETE FROM messages WHERE room_id = ?", (room_id,))
    db.execute("DELETE FROM chat_rooms WHERE room_id = ?", (room_id,))
    db.commit()
    db.close()
    return {"message": "삭제 성공"}

# 🚀 커뮤니티 API 추가
@app.get("/api/community")
async def get_community():
    db = get_db()
    posts = db.execute("SELECT * FROM community ORDER BY timestamp DESC").fetchall()
    db.close()
    return {"posts": [dict(p) for p in posts]}

@app.post("/api/community")
async def create_post(post: CommunityPost):
    db = get_db()
    db.execute("INSERT INTO community (user_id, content, score, timestamp) VALUES (?, ?, ?, ?)",
               (post.user_id, post.content, post.score, datetime.now().isoformat()))
    db.commit()
    db.close()
    return {"message": "등록 완료"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)