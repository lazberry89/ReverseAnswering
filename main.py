import os
import json
import sqlite3
import uvicorn
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
import ollama  # 🚀 Ollama 라이브러리 추가
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

celebras_client = OpenAI(api_key=os.getenv("CELEBRAS_API_KEY"), base_url="https://api.cerebras.ai/v1")
groq_client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
gemini_client = OpenAI(api_key=os.getenv("GEMINI_API_KEY"),
                       base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🚀 Ollama 클라이언트 세팅
ollama_client = ollama.Client(host='http://aruru.kr:11434')

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
                너는 {req.category} {req.topic}을 배우는 {req.age}살 학생이야. {req.lang} 언어를 사용하여 말하도록해.
                {req.difficulty}/10 에 맞는 난이도로 점수를 주면돼.
                !!!넌 무조건 학생이야.유저는 선생님이고.넌 아무것도 모르는거고,유저가 알려주는 입장이야.
                !!!그리고 내용이 틀렸더라도 절대 너가 알려주지마. 질문으로 유도해.
                !!!유저가 질문했다고 해서 절대 알려주지마.넌 학생이야.AI어시스턴트가 아니라고
                [중요: 누적 점수 규칙]
                현재 유저의 누적 점수는 **{current_score}점**이야.
                !!!누적점수는 음수가 될 수 없어.0점이라면 감점을 하지마.
                - 설명이 정확하다면: +10~15점
                - 설명이 맞긴 하지만 조금 부족하면: +3~5점
                - 틀린 사실을 말하거나 횡설수설하면: -10~20점 차감
                - 중복된 내용을 반복시 감점하기
                - 난이도({req.difficulty}/10)가 높을수록 오답 시 더 크게 차감해.

                !!! 점수 'score' 는 {current_score}에서 위 계산을 적용한 "결과값"을 숫자로만 적어.
                !!! 점수 'score' 가 100이상이라면 'is_finished'를 true로 바꾸고, 마무리 멘트를 하도록 해.

                반드시 다음 JSON 형식으로만 답해: 
                {{"reply": "질문 내용", "score": 최종누적점수, "is_finished": true/false, "hint": "힌트"}}
                """

        messages = [{"role": "system", "content": system_instruction}]
        messages.extend(history)
        messages.append({"role": "user", "content": req.message})

        # 🚀 모델 선택 로직 (Ollama 방식 추가)
        is_ollama = False

        if req.model_type == "ollama":
            is_ollama = True
            target_model = "gpt-oss:20b"  # 요청하신 모델명
        elif req.model_type == "groq":
            target_client = groq_client
            target_model = "llama-3.3-70b-versatile"
        elif req.model_type == "gemini":
            target_client = gemini_client
            target_model = "gemini-2.0-flash"  # 아까 수정한 모델명 유지
        elif req.model_type == "celebras":
            target_client = celebras_client
            target_model = "llama3.1-8b"
        else:
            target_client = groq_client
            target_model = "llama-3.3-70b-versatile"

        # 🚀 API 호출 방식 분기 처리 (Ollama vs OpenAI)
        if is_ollama:
            response = ollama_client.chat(
                model=target_model,
                messages=messages,
                format='json'  # JSON 강제 출력 옵션
            )
            ai_raw = response['message']['content']
        else:
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
                summary_response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
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