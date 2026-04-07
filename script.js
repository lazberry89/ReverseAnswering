// ==========================================
// 🌐 전역 변수 (상태 관리)
// ==========================================
const BASE_URL = "http://127.0.0.1:8000";
let currentUser = ""; // 현재 로그인한 유저 ID

// ==========================================
// 🛠️ 화면 전환 함수
// ==========================================
function showScreen(screenId) {
    // 모든 화면을 숨기고
    document.querySelectorAll('.screen').forEach(s => s.style.display = 'none');
    // 선택한 화면만 보여주기
    document.getElementById(screenId).style.display = 'block';
}

// ==========================================
// 🔐 1. 로그인 & 회원가입
// ==========================================
document.getElementById('btn-register').onclick = async () => {
    const id = document.getElementById('login-id').value;
    const pw = document.getElementById('login-pw').value;

    const res = await fetch(`${BASE_URL}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: id, password: pw })
    });

    const data = await res.json();
    alert(data.detail || data.message);
};

document.getElementById('btn-login').onclick = async () => {
    const id = document.getElementById('login-id').value;
    const pw = document.getElementById('login-pw').value;

    const res = await fetch(`${BASE_URL}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: id, password: pw })
    });

    if (res.ok) {
        currentUser = id;
        // 로그인 성공 시 프로필이 있는지 확인하고 없으면 프로필 화면으로, 있으면 메인으로
        showScreen('profile-screen');
    } else {
        const data = await res.json();
        alert(data.detail);
    }
};

// ==========================================
// 👤 2. 프로필 저장
// ==========================================
document.getElementById('btn-save-profile').onclick = async () => {
    const age = document.getElementById('profile-age').value;
    const school = document.getElementById('profile-school').value;

    await fetch(`${BASE_URL}/profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: currentUser, age: parseInt(age), school: school })
    });

    showScreen('main-menu-screen');
};

// ==========================================
// 🏠 3. 메인 메뉴 이동
// ==========================================
document.getElementById('btn-go-ai').onclick = () => showScreen('ai-setup-screen');
document.getElementById('btn-go-community').onclick = async () => {
    await updateCommunity();
    showScreen('community-screen');
};

// ==========================================
// 🤖 4. AI 채팅 로직
// ==========================================
document.getElementById('ai-difficulty').oninput = (e) => {
    document.getElementById('diff-value').innerText = e.target.value;
};

document.getElementById('btn-start-chat').onclick = () => {
    // 채팅창 비우고 시작
    document.getElementById('chat-box').innerHTML = "";
    showScreen('chat-screen');
    addMessage("system", "AI 학생이 접속했습니다. 주제에 대해 설명을 시작해주세요!");
};

document.getElementById('btn-send-chat').onclick = async () => {
    const input = document.getElementById('chat-input');
    const message = input.value;
    if (!message) return;

    addMessage("user", message);
    input.value = "";

    // 서버로 데이터 전송
    const res = await fetch(`${BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            user_id: currentUser,
            category: document.getElementById('ai-category').value,
            topic: document.getElementById('ai-topic').value,
            difficulty: parseInt(document.getElementById('ai-difficulty').value),
            age: parseInt(document.getElementById('ai-age').value),
            lang: document.getElementById('ai-lang').value, // 언어 선택 추가
            message: message
        })
    });

    const data = await res.json();
    addMessage("ai", data.reply);
    document.getElementById('current-score').innerText = data.score;

    if (data.is_finished) {
        alert("🎉 축하합니다! 완벽히 이해했어요!");
    }
};

function addMessage(sender, text) {
    const box = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    msgDiv.innerHTML = `<strong>${sender}:</strong> ${text}`;
    box.appendChild(msgDiv);
    box.scrollTop = box.scrollHeight;
}

// ==========================================
// 🏆 5. 커뮤니티 로직
// ==========================================
async function updateCommunity() {
    const res = await fetch(`${BASE_URL}/community`);
    const data = await res.json();
    const list = document.getElementById('post-list');
    list.innerHTML = "";
    data.posts.forEach(post => {
        const item = document.createElement('div');
        item.innerHTML = `<p><strong>${post.user_id}</strong>: ${post.content} (점수: ${post.score}점)</p>`;
        list.appendChild(item);
    });
}

document.getElementById('btn-write-post').onclick = async () => {
    const content = document.getElementById('post-content').value;
    const score = document.getElementById('current-score').innerText;

    await fetch(`${BASE_URL}/community`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: currentUser, content: content, score: parseInt(score) })
    });

    document.getElementById('post-content').value = "";
    await updateCommunity();
};

document.getElementById('btn-back-to-main').onclick = () => showScreen('main-menu-screen');