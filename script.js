const API_PREFIX = "/api";
let currentUser = localStorage.getItem("user_id") || "";
let currentRoomId = null;
let lastScore = 0;
let selectedModel = "groq";
let userProfileAge = 17; // 유저 나이 전역 변수

function showToast(msg, type="info") {
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
    setTimeout(() => { toast.style.animation = "fadeOut 0.5s forwards"; setTimeout(() => toast.remove(), 500); }, 3000);
}

// 🖼️ 커스텀 컨펌 모달 로직
function openConfirmModal(onConfirm) {
    const modal = document.getElementById('confirm-modal');
    const confirmBtn = document.getElementById('modal-confirm-btn');
    modal.style.display = 'flex';

    // 버튼 클릭 이벤트 바인딩 (이전 이벤트 제거를 위해 클론 사용)
    const newBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

    newBtn.onclick = () => {
        onConfirm();
        closeConfirmModal();
    };
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
}

function showAuraScreen(id) {
    document.getElementById('aura-wrapper').style.display = 'flex';
    document.getElementById('chat-ui').style.display = 'none';

    // 모든 아우라 컨테이너 숨기기
    document.querySelectorAll('.aura-container').forEach(c => c.style.display = 'none');

    // 선택된 화면 보여주기
    const target = document.getElementById(id);
    if(target) target.style.display = 'block';

    // 커뮤니티 화면일 경우 게시글 로드
    if (id === 'community-aura') {
        loadCommunityPosts();
    }
    // AI 설정 화면일 경우 드롭다운 메뉴에 현재 선택된 모델 반영
    else if (id === 'ai-setup-aura') {
        const aiModelSelect = document.getElementById('ai-model');
        if (aiModelSelect) {
            aiModelSelect.value = selectedModel; // 현재 selectedModel 값으로 드롭다운 설정
        }
    }
    // 채팅 화면이 아닐 때는 힌트 숨김
    hideHint();
}

function showChatUI() {
    document.getElementById('aura-wrapper').style.display = 'none';
    document.getElementById('chat-ui').style.display = 'flex';
}

function logout() {
    localStorage.removeItem("user_id");
    localStorage.removeItem("user_age");
    location.href = '/login';
}

async function fetchUserProfile() {
    try {
        const res = await fetch(`${API_PREFIX}/profile/${currentUser}`);
        if (res.ok) {
            const data = await res.json();
            userProfileAge = data.age || 17;
            document.getElementById('profile-age').value = data.age || "";
            document.getElementById('profile-school').value = data.school || "";
        }
    } catch (e) { console.error("Profile load failed", e); }
}

async function saveProfile() {
    const age = parseInt(document.getElementById('profile-age').value) || 17;
    const school = document.getElementById('profile-school').value || "일반";

    await fetch(`${API_PREFIX}/profile`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({user_id: currentUser, age, school})
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
        if(res.ok) {
            showToast("대화 기록이 삭제되었습니다.");
            if(currentRoomId == roomId) {
                location.reload();
            } else {
                loadHistory();
            }
        } else {
            showToast("삭제할 수 없습니다.", "error");
        }
    } catch(e) {
        console.error(e);
        showToast("서버 오류가 발생했습니다.", "error");
    }
}

async function loadChatData(roomId, topic) {
    currentRoomId = roomId;
    const res = await fetch(`${API_PREFIX}/chat_data/${roomId}`);
    const msgs = await res.json();
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = "";
    let finalScore = 0;
    msgs.forEach(m => {
        let text = m.content;
        if(m.role === 'assistant') {
            try { const parsed = JSON.parse(m.content); text = parsed.reply; finalScore = m.score; } catch(e) {}
        }
        addMessage(m.role === 'user' ? 'user' : 'ai', text);
    });
    document.getElementById('chat-title').innerText = topic;
    updateScore(finalScore, true);
    showChatUI();
}

function startChat() {
    const topic = document.getElementById('ai-topic').value;
    if(!topic) return showToast("주제를 입력하세요!", "error");
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
    if(!message) return;

    addMessage('user', message, true);
    input.value = "";
    document.getElementById('typing-indicator').style.display = 'block';
    hideHint(); // 유저가 전송하면 힌트 숨김

    try {
        const res = await fetch(`${API_PREFIX}/chat`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                user_id: currentUser,
                room_id: currentRoomId,
                category: document.getElementById('ai-category').value,
                topic: document.getElementById('chat-title').innerText,
                difficulty: parseInt(document.getElementById('ai-difficulty').value),
                age: userProfileAge,
                lang: "Korean",
                model_type: selectedModel,
                message: message
            })
        });
        const data = await res.json();
        document.getElementById('typing-indicator').style.display = 'none';
        if(data.reply) {
            currentRoomId = data.room_id;
            addMessage('ai', data.reply);

            // 점수가 하락했고 힌트가 있다면 표시
            if (data.score < lastScore && data.hint) {
                showHint(data.hint);
            }

            updateScore(data.score);
            loadHistory();
            if(data.is_finished) showToast("🎉 완벽히 이해했습니다!", "success");
        }
    } catch (e) { document.getElementById('typing-indicator').style.display = 'none'; }
}

function addMessage(sender, text, forceScroll = false) {
    const chatContainer = document.getElementById('chat-container');
    const chatBox = document.getElementById('chat-box');
    const isAtBottom = chatContainer.scrollHeight - chatContainer.scrollTop <= chatContainer.clientHeight + 50;
    const div = document.createElement('div');
    div.className = `msg ${sender}-msg`;
    div.innerText = text;
    chatBox.appendChild(div);

    if (isAtBottom || forceScroll) {
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
    }
}

function updateScore(score, silent = false) {
    const el = document.getElementById('current-score');
    const gauge = document.getElementById('score-gauge');
    el.innerText = score;
    gauge.style.width = `${score}%`;

    if (!silent) {
        if (score > lastScore) {
            document.body.classList.remove('score-up', 'score-down');
            void document.body.offsetWidth;
            document.body.classList.add('score-up');
            setTimeout(() => document.body.classList.remove('score-up'), 800);
        } else if (score < lastScore) {
            document.body.classList.remove('score-up', 'score-down');
            void document.body.offsetWidth;
            document.body.classList.add('score-down');
            setTimeout(() => document.body.classList.remove('score-down'), 800);
        }
    }
    lastScore = score;
}

// 💡 힌트 슬라이더 로직
function showHint(text) {
    const slider = document.getElementById('hint-slider');
    const hintText = document.getElementById('hint-text');
    hintText.innerText = text;
    slider.classList.add('show');
}

function hideHint() {
    const slider = document.getElementById('hint-slider');
    if(slider) slider.classList.remove('show');
}

// 🏆 커뮤니티 연동 로직
async function loadCommunityPosts() {
    const list = document.getElementById('community-posts-list');
    list.innerHTML = "<p style='color: #94a3b8;'>불러오는 중...</p>";

    try {
        const res = await fetch(`${API_PREFIX}/community`);
        const data = await res.json();
        list.innerHTML = "";

        if (data.posts && data.posts.length > 0) {
            data.posts.forEach(post => {
                const item = document.createElement('div');
                item.style.padding = "10px";
                item.style.borderBottom = "1px solid #f1f5f9";
                item.innerHTML = `
                    <div style="font-weight: 700; font-size: 0.9rem; color: var(--primary);">${post.user_id}</div>
                    <div style="font-size: 0.95rem; margin: 4px 0;">${post.content}</div>
                    <div style="font-size: 0.8rem; color: #94a3b8;">이해도: ${post.score}%</div>
                `;
                list.appendChild(item);
            });
        } else {
            list.innerHTML = "<p style='color: #94a3b8;'>게시글이 없습니다.</p>";
        }
    } catch (e) {
        list.innerHTML = "<p style='color: #e74c3c;'>불러오지 못했습니다.</p>";
    }
}

async function writeCommunityPost() {
    const postInput = document.getElementById('community-post-input');
    const content = postInput.value.trim();
    const currentScore = parseInt(document.getElementById('current-score').innerText);

    if (!content) {
        return showToast("자랑할 내용을 입력해주세요!", "error");
    }

    try {
        const res = await fetch(`${API_PREFIX}/community`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                user_id: currentUser,
                content: content,
                score: currentScore
            })
        });

        if (res.ok) {
            showToast("자랑글이 등록되었습니다!", "success");
            postInput.value = "";
            loadCommunityPosts();
        } else {
            showToast("글쓰기에 실패했습니다.", "error");
        }
    } catch (e) {
        console.error("Community post failed", e);
        showToast("서버 오류로 글쓰기에 실패했습니다.", "error");
    }
}

if (currentUser) {
    fetchUserProfile();
}