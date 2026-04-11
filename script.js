const API_PREFIX = "/api";
let currentUser = localStorage.getItem("user_id") || "";
let currentRoomId = null;
let lastScore = 0;
let selectedModel = "groq";
let userProfileAge = 17;
let isCompetitionMode = false;
let currentProblem = "";
let currentLiveRoomCode = null;
let liveStatusInterval = null;
let isHost = false;

// --- 공통 UI 로직 ---

function showToast(msg, type = "info") {
    let container = document.querySelector(".toast-container");
    if (!container) {
        container = document.createElement("div");
        container.className = "toast-container";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerText = msg;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = "fadeOut 0.5s forwards";
        setTimeout(() => toast.remove(), 500);
    }, 3000);
}

function openConfirmModal(onConfirm) {
    const modal = document.getElementById('confirm-modal');
    const confirmBtn = document.getElementById('modal-confirm-btn');
    modal.style.display = 'flex';
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);
    newBtn.onclick = () => { onConfirm(); closeConfirmModal(); };
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
}

function showAuraScreen(id) {
    document.getElementById('aura-wrapper').style.display = 'flex';
    document.getElementById('chat-ui').style.display = 'none';
    document.querySelectorAll('.aura-container').forEach(c => c.style.display = 'none');
    const target = document.getElementById(id);
    if (target) target.style.display = 'block';
    if (id === 'community-aura') loadCommunityPosts();
    else if (id === 'ai-setup-aura') {
        const aiModelSelect = document.getElementById('ai-model');
        if (aiModelSelect) aiModelSelect.value = selectedModel;
    }
    hideHint();
}

function showChatUI() {
    document.getElementById('aura-wrapper').style.display = 'none';
    document.getElementById('chat-ui').style.display = 'flex';
}

function logout() {
    localStorage.removeItem("user_id");
    location.href = '/login';
}

// --- 프로필 & 히스토리 로직 ---

async function fetchUserProfile() {
    try {
        const res = await fetch(`${API_PREFIX}/profile/${currentUser}`);
        if (res.ok) {
            const data = await res.json();
            userProfileAge = data.age || 17;
            document.getElementById('profile-age').value = data.age || "";
            document.getElementById('profile-school').value = data.school || "";
            const liveAgeInput = document.getElementById('live-comp-age');
            if (liveAgeInput) liveAgeInput.value = userProfileAge;
        }
    } catch (e) { console.error("Profile load failed", e); }
}

async function saveProfile() {
    const age = parseInt(document.getElementById('profile-age').value) || 17;
    const school = document.getElementById('profile-school').value || "일반";
    await fetch(`${API_PREFIX}/profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: currentUser, age, school })
    });
    userProfileAge = age;
    showToast("프로필이 저장되었습니다!", "success");
    showAuraScreen('main-menu-aura');
}

async function loadHistory() {
    const res = await fetch(`${API_PREFIX}/history/${currentUser}`);
    const rooms = await res.json();
    const list = document.getElementById('history-list');
    list.innerHTML = "";
    rooms.forEach(r => {
        const itemWrap = document.createElement('div');
        itemWrap.className = "history-item-wrap";
        itemWrap.style.display = "flex";
        itemWrap.style.alignItems = "center";
        itemWrap.style.justifyContent = "space-between";
        itemWrap.style.paddingRight = "10px";

        const div = document.createElement('div');
        div.className = "history-item";
        div.innerText = r.topic;
        div.style.flex = "1";
        div.onclick = () => loadChatData(r.room_id, r.topic);

        const delBtn = document.createElement('button');
        delBtn.innerHTML = "×";
        delBtn.className = "history-del-btn";
        delBtn.onclick = (e) => {
            e.stopPropagation();
            openConfirmModal(() => deleteHistory(r.room_id));
        };
        itemWrap.appendChild(div);
        itemWrap.appendChild(delBtn);
        list.appendChild(itemWrap);
    });
}

async function deleteHistory(roomId) {
    try {
        const res = await fetch(`${API_PREFIX}/chat/room/${roomId}`, { method: 'DELETE' });
        if (res.ok) {
            showToast("대화 기록이 삭제되었습니다.");
            if (currentRoomId == roomId) location.reload();
            else loadHistory();
        }
    } catch (e) { showToast("서버 오류가 발생했습니다.", "error"); }
}

// --- 채팅 & 경진대회 핵심 로직 ---

async function loadChatData(roomId, topic) {
    isCompetitionMode = false;
    currentRoomId = roomId;
    const res = await fetch(`${API_PREFIX}/chat_data/${roomId}`);
    const msgs = await res.json();
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = "";
    let finalScore = 0;
    msgs.forEach(m => {
        let text = m.content;
        if (m.role === 'assistant') {
            try { const parsed = JSON.parse(m.content); text = parsed.reply; finalScore = m.score; } catch (e) { }
        }
        addMessage(m.role === 'user' ? 'user' : 'ai', text);
    });
    document.getElementById('chat-title').innerText = topic;
    updateScore(finalScore, true);
    showChatUI();
}

function startChat() {
    isCompetitionMode = false;
    const topic = document.getElementById('ai-topic').value;
    if (!topic) return showToast("주제를 입력하세요!", "error");
    selectedModel = document.getElementById('ai-model').value;
    currentRoomId = null;
    document.getElementById('chat-box').innerHTML = "";
    document.getElementById('chat-title').innerText = topic;
    updateScore(0, true);
    showChatUI();
    addMessage('ai', `반가워요! 오늘은 '${topic}'에 대해 설명해주실 준비 되셨나요?`);
}

async function sendChat() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    addMessage('user', message, true);
    input.value = "";
    document.getElementById('typing-indicator').style.display = 'block';
    hideHint();

    if (isCompetitionMode) {
        // 🏆 경진대회 모드 전송
        try {
            const res = await fetch(`${API_PREFIX}/competition/answer`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: currentUser,
                    category: "실시간",
                    age: userProfileAge,
                    problem: currentProblem,
                    answer: message,
                    model_type: selectedModel,
                    room_code: currentLiveRoomCode
                })
            });
            const data = await res.json();
            document.getElementById('typing-indicator').style.display = 'none';
            if (data.feedback) {
                addMessage('ai', `[채점 완료]\n점수: ${data.score}점\n\n${data.feedback}`);
                updateScore(data.score);
                if (data.is_correct) showToast("🏆 멋진 답변입니다!", "success");
            }
        } catch (e) {
            document.getElementById('typing-indicator').style.display = 'none';
            showToast("채점 중 오류가 발생했습니다.", "error");
        }
    } else {
        // 🎓 일반 AI 튜터 모드 전송
        try {
            const res = await fetch(`${API_PREFIX}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: currentUser,
                    room_id: currentRoomId,
                    category: document.getElementById('ai-category').value,
                    topic: document.getElementById('chat-title').innerText,
                    difficulty: parseInt(document.getElementById('ai-difficulty').value),
                    age: userProfileAge,
                    model_type: selectedModel,
                    message: message
                })
            });
            const data = await res.json();
            document.getElementById('typing-indicator').style.display = 'none';
            if (data.reply) {
                currentRoomId = data.room_id;
                addMessage('ai', data.reply);
                if (data.score < lastScore && data.hint) showHint(data.hint);
                updateScore(data.score);
                loadHistory();

                if (data.is_finished) {
                    showToast("🎉 완벽히 이해했습니다!", "success");
                    renderResults(data);
                }
            }
        } catch (e) {
            document.getElementById('typing-indicator').style.display = 'none';
            showToast("메시지 전송 실패", "error");
        }
    }
}

// --- 결과 창 렌더링 로직 ---

function renderResults(data) {
    // 1. 부족한 개념 리스트
    const weakPointsList = document.getElementById('weak-points-list');
    weakPointsList.innerHTML = '';
    if (data.weak_points && data.weak_points.length > 0) {
        data.weak_points.forEach(point => {
            const li = document.createElement('li');
            li.innerText = point;
            weakPointsList.appendChild(li);
        });
    } else {
        weakPointsList.innerHTML = '<li>부족한 점이 없네요! 완벽합니다.</li>';
    }

    // 2. 유튜브 추천 링크
    const youtubeList = document.getElementById('youtube-list');
    youtubeList.innerHTML = '';
    if (data.youtube_recommendations && data.youtube_recommendations.length > 0) {
        data.youtube_recommendations.forEach(video => {
            const a = document.createElement('a');
            a.href = video.url;
            a.target = "_blank";
            a.style.display = "block";
            a.style.padding = "10px";
            a.style.background = "#f1f5f9";
            a.style.borderRadius = "8px";
            a.style.textDecoration = "none";
            a.style.color = "#1e293b";
            a.style.marginBottom = "5px";
            a.style.fontSize = "0.9rem";
            a.innerText = `📺 ${video.title}`;
            youtubeList.appendChild(a);
        });
    }

    // 3. 화면 전환
    setTimeout(() => { showAuraScreen('results-aura'); }, 2000);
}

// --- 기타 유틸리티 (메시지 추가, 점수 업데이트 등) ---

function addMessage(sender, text, forceScroll = false) {
    const chatContainer = document.getElementById('chat-container');
    const chatBox = document.getElementById('chat-box');
    const div = document.createElement('div');
    div.className = `msg ${sender}-msg`;
    div.innerText = text;
    chatBox.appendChild(div);
    if (forceScroll) chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
}

function updateScore(score, silent = false) {
    const el = document.getElementById('current-score');
    const gauge = document.getElementById('score-gauge');
    el.innerText = score;
    gauge.style.width = `${score}%`;
    if (!silent) {
        const effect = score > lastScore ? 'score-up' : (score < lastScore ? 'score-down' : '');
        if (effect) {
            document.body.classList.add(effect);
            setTimeout(() => document.body.classList.remove(effect), 800);
        }
    }
    lastScore = score;
}

function showHint(text) {
    const slider = document.getElementById('hint-slider');
    const hintText = document.getElementById('hint-text');
    hintText.innerText = text;
    slider.classList.add('show');
}

function hideHint() {
    const slider = document.getElementById('hint-slider');
    if (slider) slider.classList.remove('show');
}

// --- 커뮤니티 & 랭킹 로직 ---

async function loadCommunityPosts() {
    const list = document.getElementById('community-posts-list');
    list.innerHTML = "<p>불러오는 중...</p>";
    try {
        const res = await fetch(`${API_PREFIX}/community`);
        const data = await res.json();
        list.innerHTML = data.posts.map(p => `
            <div style="padding: 10px; border-bottom: 1px solid #eee;">
                <div style="font-weight: 700;">${p.user_id}</div>
                <div>${p.content}</div>
                <div style="font-size: 0.8rem; color: #94a3b8;">이해도: ${p.score}%</div>
            </div>
        `).join('') || "<p>게시글이 없습니다.</p>";
    } catch (e) { list.innerHTML = "<p>오류 발생</p>"; }
}

async function writeCommunityPost() {
    const content = document.getElementById('community-post-input').value.trim();
    const currentScore = parseInt(document.getElementById('current-score').innerText);
    if (!content) return showToast("내용을 입력하세요.", "error");
    const res = await fetch(`${API_PREFIX}/community`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: currentUser, content, score: currentScore })
    });
    if (res.ok) {
        showToast("등록되었습니다!", "success");
        document.getElementById('community-post-input').value = "";
        loadCommunityPosts();
    }
}

async function loadRankings(category) {
    const list = document.getElementById('ranking-list');
    list.innerHTML = `<p style="text-align: center; padding: 20px;">${category} 랭킹 로드 중...</p>`;
    try {
        const res = await fetch(`${API_PREFIX}/ranking/${category}`);
        const data = await res.json();
        list.innerHTML = data.map((p, idx) => `
            <div style="padding: 12px 20px; display: flex; justify-content: space-between; border-bottom: 1px solid #f1f5f9; ${p.user_id === currentUser ? 'background:#eff6ff;' : ''}">
                <div style="font-weight: 700;">${idx < 3 ? ['🥇','🥈','🥉'][idx] : idx+1} ${p.user_id}</div>
                <div style="color: var(--primary); font-weight: 800;">${p.score}점</div>
            </div>
        `).join('') || `<p style="text-align: center; padding: 20px;">기록이 없습니다.</p>`;
    } catch (e) { list.innerHTML = "<p>로드 실패</p>"; }
}

// --- 경진대회 방 관리 ---

async function createLiveCompetition() {
    const topic = document.getElementById('live-comp-topic').value.trim();
    if (!topic) return showToast("주제를 입력하세요!", "error");
    const res = await fetch(`${API_PREFIX}/competition/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            host_id: currentUser,
            category: document.getElementById('live-comp-category').value,
            topic: topic,
            age: parseInt(document.getElementById('live-comp-age').value) || userProfileAge
        })
    });
    const data = await res.json();
    if (data.room_code) {
        currentLiveRoomCode = data.room_code;
        isHost = true;
        enterLobby(data.room_code);
    }
}

async function joinLiveCompetition() {
    const code = document.getElementById('live-comp-code').value.trim();
    if (code.length !== 6) return showToast("6자리 코드를 입력하세요.", "error");
    const res = await fetch(`${API_PREFIX}/competition/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: currentUser, room_code: code })
    });
    if (res.ok) {
        currentLiveRoomCode = code;
        isHost = false;
        enterLobby(code);
    } else {
        const err = await res.json();
        showToast(err.detail || "참가 실패", "error");
    }
}

function enterLobby(code) {
    document.getElementById('lobby-code-display').innerText = code;
    document.getElementById('host-controls').style.display = isHost ? 'block' : 'none';
    document.getElementById('guest-waiting').style.display = isHost ? 'none' : 'block';
    showAuraScreen('comp-lobby-aura');
    if (liveStatusInterval) clearInterval(liveStatusInterval);
    liveStatusInterval = setInterval(updateLiveStatus, 2000);
}

async function updateLiveStatus() {
    if (!currentLiveRoomCode) return;
    const res = await fetch(`${API_PREFIX}/competition/status/${currentLiveRoomCode}`);
    const data = await res.json();
    document.getElementById('participant-count').innerText = data.participants.length;
    document.getElementById('lobby-participant-list').innerHTML = data.participants.map(p => `
        <div style="padding:8px; border-bottom:1px solid #eee;">${p.user_id} - ${p.is_submitted ? '완료' : '준비 중'}</div>
    `).join('');
    if (data.status === 'ongoing' && !isCompetitionMode) {
        isCompetitionMode = true;
        currentProblem = data.problem;
        showChatUI();
        addMessage('ai', `[실시간 대회 시작!]\n\n${data.problem}`);
        if (data.hint) showHint(data.hint);
    }
}

async function startLiveCompetition() {
    if (!isHost) return;
    await fetch(`${API_PREFIX}/competition/start_live/${currentLiveRoomCode}`, { method: "POST" });
}

// 초기화
if (currentUser) {
    fetchUserProfile();
    loadHistory();
}