import os
import json
import sqlite3
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
    # 실시간 경진대회 방
    c.execute('''CREATE TABLE IF NOT EXISTS comp_rooms 
                 (room_code TEXT PRIMARY KEY, host_id TEXT, category TEXT, topic TEXT, age INTEGER, 
                  status TEXT DEFAULT "waiting", problem TEXT, hint TEXT, started_at TEXT, created_at TEXT)''')
    # 경진대회 참가자
    c.execute('''CREATE TABLE IF NOT EXISTS comp_participants 
                 (room_code TEXT, user_id TEXT, score INTEGER DEFAULT 0, 
                  is_submitted BOOLEAN DEFAULT 0, feedback TEXT, PRIMARY KEY(room_code, user_id))''')
    
    # 📊 실시간 학생 분석 데이터 테이블 추가
    c.execute('''CREATE TABLE IF NOT EXISTS student_analysis (
        analysis_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id TEXT, 
        topic TEXT, 
        strengths TEXT, 
        weaknesses TEXT, 
        learning_traits TEXT,
        updated_at TEXT,
        UNIQUE(user_id, topic)
    )''')
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


class CompetitionRequest(BaseModel):
    user_id: str
    category: str
    age: int
    model_type: str = "openrouter"


class CompetitionAnswerRequest(BaseModel):
    user_id: str
    category: str
    age: int
    problem: str
    answer: str
    model_type: str = "openrouter"
    room_code: Optional[str] = None


class CreateCompRoomRequest(BaseModel):
    host_id: str
    category: str
    topic: str
    age: int


class JoinCompRoomRequest(BaseModel):
    user_id: str
    room_code: str


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
                                [역할 고정: 너는 절대 AI가 아니다]
                                - 너는 {req.category} 과목의 '{req.topic}'을 하나도 모르는 {req.age}살 학생이야.
                                - 유저는 너를 가르치는 '선생님'이다. 
                                - 절대 "무엇을 도와드릴까요?", "궁금한 게 있으신가요?", "제 설명이 도움이 되었나요?" 같은 AI 어시스턴트 말투를 쓰지 마.
                                - 너의 목적은 유저에게 '도움을 주는 것'이 아니라, 유저로부터 '설명을 들어서 이해하는 것'이다.

                                [대화 규칙]
                                1. 모르는 게 있으면 학생처럼 질문해. (예: "그게 무슨 말이야?", "좀 더 쉽게 비유해줄 수 있어?")
                                2. 유저의 설명이 좋으면 감탄해. (예: "와, 그렇게 생각하니까 이해가 잘 돼!")
                                3. 절대 유저의 질문에 답만 하고 끝내지 말고, 배운 내용을 네 방식대로 재구성해서 "이게 맞아?"라고 되물어봐.
                                4. {req.age}살 아이의 지능과 말투를 유지해. 너무 격식 차리지 마.

                                [중요: 실시간 분석 기능]
                                - analysis_update: 유저(선생님)의 설명에서 느낀 강점, 약점, 성향을 분석해.

                                [점수 평가]
                                현재 점수: **{current_score}점**
                                - 유저가 개념을 아주 쉽게 비유나 예시로 설명함: +15점
                                - 설명이 논리적이고 정확함: +10점
                                - 단순히 지식을 나열하거나 AI처럼 말함: -10점
                                - 했던 말을 또 함: -5점
                                * 최종 점수는 누적이며 0~100점 사이야.

                                [시스템 상태]
                                100점 도달 시 'is_finished'를 true로 하고, "다 이해했어! 고마워 선생님!" 같은 느낌으로 마무리해.

                                반드시 아래 JSON 형식으로만 답해:
                                {{
                                    "reply": "학생으로서의 반응 (절대 도움을 제안하지 말 것)",
                                    "score": 현재_누적_점수, 
                                    "is_finished": false, 
                                    "hint": "선생님이 더 쉽게 가르칠 수 있게 유도하는 팁",
                                    "analysis_update": {{
                                        "strengths": "선생님의 장점",
                                        "weaknesses": "선생님의 단점",
                                        "traits": "선생님의 스타일"
                                    }}
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

        # 분석 데이터 DB 업데이트
        analysis = result.get("analysis_update", {})
        if analysis:
            db.execute('''INSERT INTO student_analysis (user_id, topic, strengths, weaknesses, learning_traits, updated_at)
                          VALUES (?, ?, ?, ?, ?, ?)
                          ON CONFLICT(user_id, topic) DO UPDATE SET
                          strengths=excluded.strengths, weaknesses=excluded.weaknesses, 
                          learning_traits=excluded.learning_traits, updated_at=excluded.updated_at''',
                       (req.user_id, req.topic, analysis.get("strengths"), analysis.get("weaknesses"), 
                        analysis.get("traits"), datetime.now().isoformat()))

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
        final_ai_content = json.dumps(result, ensure_ascii=False)

        now = datetime.now().isoformat()
        db.execute("INSERT INTO messages (room_id, role, content, score, timestamp) VALUES (?, 'user', ?, 0, ?)",
                   (room_id, req.message, now))
        db.execute("INSERT INTO messages (room_id, role, content, score, timestamp) VALUES (?, 'assistant', ?, ?, ?)",
                   (room_id, final_ai_content, final_score, now))
        db.commit()

        result["room_id"] = room_id
        return result

    except Exception as e:
        print(f"🔥 서버 에러 발생: {e}")
        return JSONResponse(status_code=500, content={"reply": f"에러: {str(e)}", "score": 0})
    finally:
        db.close()

# 👨‍🏫 분석 데이터 조회 API
@app.get("/api/analysis/all")
async def get_all_analysis():
    db = get_db()
    rows = db.execute("SELECT * FROM student_analysis ORDER BY updated_at DESC").fetchall()
    db.close()
    return {"analysis": [dict(r) for r in rows]}

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


@app.post("/api/competition/create")
async def create_comp_room(req: CreateCompRoomRequest):
    import random
    room_code = "".join([str(random.randint(0, 9)) for _ in range(6)])
    db = get_db()
    db.execute(
        "INSERT INTO comp_rooms (room_code, host_id, category, topic, age, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (room_code, req.host_id, req.category, req.topic, req.age, datetime.now().isoformat()))
    db.execute("INSERT INTO comp_participants (room_code, user_id) VALUES (?, ?)", (room_code, req.host_id))
    db.commit()
    db.close()
    return {"room_code": room_code}


@app.post("/api/competition/join")
async def join_comp_room(req: JoinCompRoomRequest):
    db = get_db()
    room = db.execute("SELECT * FROM comp_rooms WHERE room_code=?", (req.room_code,)).fetchone()
    if not room:
        db.close()
        raise HTTPException(status_code=404, detail="존재하지 않는 대회 코드입니다.")
    try:
        db.execute("INSERT OR IGNORE INTO comp_participants (room_code, user_id) VALUES (?, ?)",
                   (req.room_code, req.user_id))
        db.commit()
    finally:
        db.close()
    return {"message": "참가 성공", "category": room["category"], "age": room["age"]}


@app.get("/api/competition/status/{room_code}")
async def get_comp_status(room_code: str):
    db = get_db()
    room = db.execute("SELECT * FROM comp_rooms WHERE room_code=?", (room_code,)).fetchone()
    participants = db.execute("SELECT user_id, score, is_submitted FROM comp_participants WHERE room_code=?",
                              (room_code,)).fetchall()
    db.close()
    if not room: raise HTTPException(status_code=404, detail="대회를 찾을 수 없습니다.")
    return {
        "status": room["status"],
        "category": room["category"],
        "topic": room["topic"],
        "problem": room["problem"],
        "hint": room["hint"],
        "participants": [dict(p) for p in participants]
    }


@app.post("/api/competition/start_live/{room_code}")
async def start_live_competition(room_code: str, model_type: str = "openrouter"):
    db = get_db()
    room = db.execute("SELECT * FROM comp_rooms WHERE room_code=?", (room_code,)).fetchone()
    if not room:
        db.close()
        raise HTTPException(status_code=404, detail="대회를 찾을 수 없습니다.")
    if room["status"] == "ongoing":
        db.close()
        return {"message": "이미 진행 중입니다."}
    try:
        system_instruction = f"""
        너는 실시간 'AI 경진대회'의 운영자야.
        과목({room['category']})과 주제({room['topic']}), 그리고 나이({room['age']}살)에 딱 맞는 수준 높은 문제를 출제해줘.
        JSON 형식으로만 답해: {{"problem": "...", "hint": "..."}}
        """
        target_client, target_model = openrouter_client, openrouter_model
        response = target_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_instruction}]
        )
        data = json.loads(response.choices[0].message.content)
        db.execute("UPDATE comp_rooms SET status='ongoing', problem=?, hint=?, started_at=? WHERE room_code=?",
                   (data["problem"], data["hint"], datetime.now().isoformat(), room_code))
        db.commit()
        return data
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="문제 생성 실패")
    finally:
        db.close()


@app.post("/api/competition/answer")
async def check_competition_answer(req: CompetitionAnswerRequest):
    try:
        system_instruction = f"""
        너는 'AI 경진대회'의 채점관이야.
        유저가 제출한 답변을 엄격하고 공정하게 채점해서 점수와 피드백을 줘.
        JSON 형식: {{"score": 00, "feedback": "상세 피드백", "is_correct": true}}
        """
        target_client, target_model = openrouter_client, openrouter_model
        response = target_client.chat.completions.create(
            model=target_model,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": req.answer}]
        )
        result = json.loads(response.choices[0].message.content)
        ai_score = result["score"]
        final_score = ai_score
        if req.room_code:
            db = get_db()
            room = db.execute("SELECT started_at FROM comp_rooms WHERE room_code=?", (req.room_code,)).fetchone()
            if room and room["started_at"]:
                start_time = datetime.fromisoformat(room["started_at"])
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                speed_bonus = 20 if elapsed_seconds <= 300 else (10 if elapsed_seconds <= 600 else 0)
                perfect_bonus = 10 if ai_score >= 100 else 0
                final_score += speed_bonus + perfect_bonus
                result["bonus_info"] = f"속도(+{speed_bonus}) + 정확도(+{perfect_bonus})"
            db.execute(
                "UPDATE comp_participants SET score=?, is_submitted=1, feedback=? WHERE room_code=? AND user_id=?",
                (final_score, result["feedback"], req.room_code, req.user_id))
            db.commit()
            db.close()
        result["score"] = final_score
        return result
    except Exception as e:
        print(f"Competition answer error: {e}")
        return JSONResponse(status_code=500, content={"score": 0, "feedback": "채점 중 오류", "is_correct": False})


@app.get("/api/ranking/{category}")
async def get_ranking(category: str):
    db = get_db()
    query = """
        SELECT cp.user_id, MAX(cp.score) as top_score
        FROM comp_participants cp
        JOIN comp_rooms cr ON cp.room_code = cr.room_code
        WHERE cr.category = ? AND cp.is_submitted = 1
        GROUP BY cp.user_id
        ORDER BY top_score DESC
        LIMIT 20
    """
    try:
        rows = db.execute(query, (category,)).fetchall()
        if not rows:
            query_chat = """
                SELECT r.user_id, MAX(m.score) as top_score
                FROM chat_rooms r
                JOIN messages m ON r.room_id = m.room_id
                WHERE r.category = ? AND m.role = 'assistant'
                GROUP BY r.user_id
                ORDER BY top_score DESC
                LIMIT 20
            """
            rows = db.execute(query_chat, (category,)).fetchall()
        return [{"user_id": row["user_id"], "score": row["top_score"]} for row in rows]
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
