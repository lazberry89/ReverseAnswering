import os
import json
import sqlite3
import uvicorn
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from openrouter import OpenRouter
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()


groq_client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
groq_model = "llama-3.3-70b-versatile"
gemini_client = OpenAI(api_key=os.getenv("GEMINI_API_KEY"),
                       base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
gemini_model = "gemini-2.5-flash"
openrouter_client = OpenAI(api_key=os.getenv("OR_API_KEY"), base_url="https://openrouter.ai/api/v1")
openrouter_model = "openai/gpt-oss-120b:free"


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
    c.execute(
        'CREATE TABLE IF NOT EXISTS community (post_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, content TEXT, score INTEGER, timestamp TEXT)')
    conn.commit()
    conn.close()


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
    model_type: str = "openrouter"
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
        if not room_id:
            cursor = db.execute("INSERT INTO chat_rooms (user_id, topic, category, created_at) VALUES (?, ?, ?, ?)",
                                (req.user_id, req.topic, req.category, datetime.now().isoformat()))
            room_id = cursor.lastrowid
            db.commit()

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

        last_score_row = db.execute(
            "SELECT score FROM messages WHERE room_id=? AND role='assistant' ORDER BY timestamp DESC LIMIT 1",
            (room_id,)).fetchone()
        current_score = last_score_row["score"] if last_score_row else 0

        system_instruction = f"""
                        [역할 설정]
                        너는 두 가지 역할을 동시에 수행해야 해.
                        1. 대화(reply) 생성 시: {req.category} {req.topic}을 배우는 {req.age}살 학생. 아무것도 모르는 척하며 유저(선생님)에게 계속 질문하고 유도해. (절대 먼저 정답을 알려주지 마!)
                        2. 한국의 {req.age}살 교육과정을 조사하고({req.topic}에 관련되어야됨) {req.difficulty}에 비례하게 질문을 해.
                        3. 점수(score) 계산 시: 유저의 설명이 개념적으로 맞는지 평가하는 '비밀 채점자'.

                        [점수 평가 규칙 (비밀 채점자로서)]
                        현재 유저의 누적 점수는 **{current_score}점**이야.
                        유저의 최신 답변을 바탕으로 아래 기준에 따라 점수를 가감해서 '최종 결과값'만 계산해.
                        - 완벽하고 정확한 설명: +15점
                        - 방향은 맞지만 설명이 부족함: +5점
                        - 틀린 개념, 횡설수설, 단순 인사: -10점 (난이도 {req.difficulty}/10을 고려해 엄격하게 판단)
                        !!!동일한 설명을 반복함: -5점
                        *주의: 누적 점수는 0점 미만으로 내려갈 수 없어. 계산 결과가 음수면 0으로 맞춰.점수는 누적점수야.

                        [시스템 상태]
                        계산된 최종 점수가 100점 이상이면 'is_finished'를 true로 설정하고, 'reply'에 학습을 완료했다는 기쁜 마무리 멘트를 작성해.

                        반드시 아래 JSON 형식으로만 답해:
                        {{
                            "reply": "학생으로서 할 말 (질문이나 반응)",
                            "score": 00, // (여기에 {current_score}에서 가감된 최종 계산된 숫자만 입력)
                            "is_finished": false, // 또는 true
                            "hint": "선생님이 더 잘 설명할 수 있도록 줄 수 있는 작은 팁"
                        }}
                        """

        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(history)
        messages.append({"role": "user", "content": req.message})

        if req.model_type == "openrouter":
            target_client = openrouter_client
            target_model = openrouter_model

        elif req.model_type == "groq":
            target_client = groq_client
            target_model = groq_model

        else:
            target_client = gemini_client
            target_model = gemini_model


        response = target_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=messages
        )
        ai_raw = response.choices[0].message.content

        result = json.loads(ai_raw)

        try:
            final_score = int(result.get("score", 0))
        except (ValueError, TypeError):
            final_score = 0

        if final_score >= 100:
            final_score = 100
            result["is_finished"] = True

            try:
                full_history_rows = db.execute(
                    "SELECT role, content FROM messages WHERE room_id=? ORDER BY timestamp ASC", (room_id,)).fetchall()
                full_chat_history = []
                for row in full_history_rows:
                    full_chat_history.append({"role": row["role"], "content": row["content"]})
                full_chat_history.append({"role": "user", "content": req.message})

                summary_prompt = f"""
                유저가 {req.category}의 {req.topic}에 대해 학습을 완료했습니다.
                다음 대화 내용을 바탕으로 유저가 어떤 개념을 어려워했는지 2~3가지 '부족한 개념'을 리스트로 요약해주세요.
                또한, 해당 부족한 개념들을 보완할 수 있는 YouTube 강의 영상 2~3개를 추천해주세요.
                각 추천 영상은 'title'과 'url'을 포함해야 합니다.

                대화 내용: {json.dumps(full_chat_history, ensure_ascii=False)}

                반드시 다음 JSON 형식으로만 답해주세요:
                {{
                    "weak_points": ["부족한 개념1", "부족한 개념2"],
                    "youtube_recommendations": [
                        {{"title": "유튜브 강의 제목1", "url": "유튜브 링크1"}},
                        {{"title": "유튜브 강의 제목2", "url": "유튜브 링크2"}}
                    ]
                }}
                """
                summary_response = openrouter_client.chat.completions.create(
                    model=openrouter_model,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": summary_prompt}]
                )
                summary_data = json.loads(summary_response.choices[0].message.content)
                result["weak_points"] = summary_data.get("weak_points", [])
                result["youtube_recommendations"] = summary_data.get("youtube_recommendations", [])
            except Exception as summary_e:
                print(f"Summary generation failed: {summary_e}")
                result["weak_points"] = ["결과 요약 생성 중 오류가 발생했습니다."]
                result["youtube_recommendations"] = []

        elif final_score < 0:
            final_score = 0

        result["score"] = final_score

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