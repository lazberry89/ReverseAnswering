🎓 AI Tutor: 역질문을 통한 지능형 교육 솔루션
"가르치는 것이 가장 완벽한 학습법입니다."
본 프로젝트는 사용자가 AI에게 개념을 가르치는 **'역질문 기반 학습(Feynman Technique)'**과 **'실시간 학습 성취 분석'**을 결합한 차세대 AI 튜터링 플랫폼입니다.

🌟 핵심 기능 (Key Features)
1. AI 역질문 튜터링 (Reverse Learning)
학생 페르소나 적용: AI는 지식을 알려주는 존재가 아니라, 해당 주제를 배우고 싶어 하는 {req.age}살 학생이 됩니다.

학습 유도: 사용자가 AI를 이해시키기 위해 설명하는 과정에서 스스로 개념을 구조화하고 체득하게 합니다.

실시간 피드백: 설명의 정확도와 논리성을 판단하여 실시간으로 학습 점수를 산출합니다.

2. 실시간 다차원 학습 분석 (Learning Analysis)
강점/약점 분석: 유저의 설명 방식에서 나타나는 장점(비유 활용 등)과 부족한 개념적 허점을 즉시 추출합니다.

학습 성향(Traits) 도출: 유저가 수식 위주로 설명하는지, 비유를 즐겨 쓰는지 등의 특징을 분석하여 리포트를 제공합니다.

맞춤형 사후 가이드: 학습 완료 시, 부족했던 개념 요약과 이를 보완할 수 있는 YouTube 추천 강의를 매칭해 줍니다.

3. 실시간 AI 경진대회 (Live Competition)
동적 문제 생성: 과목과 연령대에 맞춰 AI가 실시간으로 수준 높은 문제를 즉석에서 출제합니다.

지능형 자동 채점: 단순 일치 여부가 아니라, 답변의 질을 AI 채점관이 분석하여 점수를 부여합니다.

랭킹 시스템: 속도 보너스와 정확도 점수를 합산하여 실시간 리더보드를 관리합니다.

🛠 기술 스택 (Tech Stack)
Backend: FastAPI (Python)

Database: SQLite3 (Local persistence)

AI Engine (Multi-LLM):

Groq: Llama-3.3-70b (빠른 반응 속도)

Gemini: Gemini-2.5-flash (멀티모달 및 지능형 분석)

OpenRouter: GPT-OSS-120b (고성능 모델 활용) - 기존 드랍메뉴에 groq이 기본으로 설정되어있는데,드랍메뉴를 사용하여 openrouter를 사용해보세요!

Server: Uvicorn

📂 주요 API 엔드포인트
POST /api/chat: AI 학생과 대화 및 실시간 학습 점수/분석 데이터 수신

GET /api/analysis/all: 누적된 학습 데이터 분석 리포트 조회

POST /api/competition/create: 실시간 경진대회 방 생성 및 문제 자동 출제

POST /api/competition/answer: 제출 답안에 대한 AI 채점 및 피드백 생성

GET /api/ranking/{category}: 과목별 실시간 랭킹 순위표 조회
