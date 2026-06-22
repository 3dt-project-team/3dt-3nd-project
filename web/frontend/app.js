const dropZone = document.getElementById('drop-zone');
const dropZoneText = document.getElementById('drop-zone-text');
const dropZoneSubtext = document.getElementById('drop-zone-subtext');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('upload-status');
const uploadBtnArea = document.getElementById('upload-button-area');
const startUploadBtn = document.getElementById('start-upload-btn');

// 유저가 선택한 파일을 임시 보관할 변수 (대기실)
let selectedFile = null;

function checkAuthentication() {
    const email = localStorage.getItem('email');
    if (!email) {
        alert("데이터 파이프라인 유입관을 사용하시려면 먼저 로그인 또는 회원가입을 완료해야 합니다.");
        window.location.href = 'login.html';
        return false;
    }
    return true;
}

// 🎯 조치 완료: 로그인한 진짜 회사명(asung 등)을 찾아 화면에 실시간으로 매핑 및 잠금하는 엔진
function initAuthenticatedUI() {
    const email = localStorage.getItem('email');
    const company = localStorage.getItem('company_name');
    const navAuthSection = document.getElementById('nav-auth-section');

    if (email && company) {
        if (navAuthSection) {
            navAuthSection.innerHTML = `
                <a href="dashboard.html" class="bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-bold px-4 py-2 rounded-lg transition-all shadow-md shadow-indigo-600/20 cursor-pointer flex items-center gap-1">
                    📉 관제 대시보드 이동
                </a>
                <button onclick="handleLogout()" class="text-sm font-semibold text-slate-400 hover:text-rose-400 transition-colors cursor-pointer">
                    로그아웃
                </button>
            `;
        }

        // 🎯 고정 텍스트를 파괴하고 로그인 유저의 회사명을 인입한 뒤 락(Lock)을 겁니다.
        const companyInput = document.getElementById('company');
        if (companyInput) {
            companyInput.value = company;
            companyInput.disabled = true;
            companyInput.classList.add('opacity-60', 'cursor-not-allowed');
        }
    }
}

window.handleEnterConsole = function() {
    const email = localStorage.getItem('email');
    if (!email) {
        alert("⚠️ 관제 센터 대시보드에 접근하려면 로그인이 필요합니다. 로그인 화면으로 이동합니다.");
        window.location.href = 'login.html';
    } else {
        window.location.href = 'dashboard.html';
    }
}

window.handleLogout = function() {
    localStorage.clear();
    alert("안전하게 로그아웃되었습니다.");
    window.location.href = 'index.html';
}

document.addEventListener('DOMContentLoaded', initAuthenticatedUI);


// 1. 브라우저 자동 파일 열기 방지
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => e.preventDefault(), false);
});

// 2. 마우스 드래그 진입 시 하이라이트
['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => {
        dropZone.classList.add('border-indigo-500', 'bg-slate-900');
        dropZone.classList.remove('border-slate-800', 'bg-slate-950/40');
    }, false);
});

// 3. 마우스 드래그 탈출 시 복구
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => {
        dropZone.classList.remove('border-indigo-500', 'bg-slate-900');
        dropZone.classList.add('border-slate-800', 'bg-slate-950/40');
    }, false);
});

// 4. 파일이 대기실에 들어왔을 때 화면에 표시해주는 기능
function handleFileSelected(file) {
    if (!checkAuthentication()) return;
    if (!file) return;
    
    selectedFile = file; 
    
    dropZoneText.innerHTML = `📄 <span class="text-indigo-400 font-bold">${file.name}</span>`;
    dropZoneSubtext.innerHTML = `<span class="text-slate-400">용량: ${(file.size / 1024).toFixed(1)} KB (준비 완료)</span>`;
    
    uploadBtnArea.classList.remove('hidden');
    statusDiv.innerHTML = ""; 
}

dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileSelected(files[0]);
});

fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) handleFileSelected(files[0]);
});

startUploadBtn.addEventListener('click', () => {
    if (!selectedFile) {
        alert("적재할 파일이 선택되지 않았습니다.");
        return;
    }
    uploadFileToServer(selectedFile);
});

function uploadFileToServer(file) {
    const email = localStorage.getItem('email');
    const domain = document.getElementById('domain').value.trim();

    if (!email) {
        alert("로그인이 필요합니다.");
        window.location.href = 'login.html';
        return;
    }
    if (!domain) {
        alert("Domain(도메인명)을 입력해 주세요!");
        return;
    }

    startUploadBtn.disabled = true;
    statusDiv.innerHTML = `<span class="text-indigo-400 animate-pulse">⏳ [${file.name}] 카프카 브론즈 레이어로 적재 중...</span>`;

    // 🎯 조치 완료: 동료분의 변경사항에 맞춰 source 데이터를 완전히 탈락시키고 정합성을 맞춤
    const formData = new FormData();
    formData.append("email", email);
    formData.append("domain", domain);
    formData.append("file", file);

    fetch("/api/upload", {
        method: "POST",
        body: formData
    })
    .then(async (response) => {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "카프카 파이프라인 전송 실패");
        }
        return data;
    })
    .then((data) => {
        statusDiv.innerHTML = `<span class="text-emerald-400">✅ 적재 완수! ${data.message}</span>`;
        uploadBtnArea.classList.add('hidden');
        dropZoneText.innerText = "정형 파일(CSV, Excel)을 마우스로 끌어오세요";
        dropZoneSubtext.innerText = "또는 아래 플러스(+) 버튼 클릭";
        selectedFile = null;
    })
    .catch((error) => {
        statusDiv.innerHTML = `<span class="text-rose-400">❌ 적재 실패: ${error.message}</span>`;
        console.error("Pipeline Error:", error);
    })
    .finally(() => {
        startUploadBtn.disabled = false;
    });
}

async function processQuarantineAction(actionType, domain) {
    const checkedBoxes = document.querySelectorAll('.quarantine-checkbox:checked');
    const rowIds = Array.from(checkedBoxes).map(cb => cb.value);

    if (rowIds.length === 0) {
        const confirmAll = confirm("선택된 행이 없습니다. 해당 도메인의 '전체 격리 데이터'를 대상으로 조치하시겠습니까?");
        if (!confirmAll) return;
    }

    const actionName = actionType === 'approve' ? '강제 승인 및 마스터 병합' : '데이터 폐기';
    const reason = prompt(`[${actionName}] 작업을 진행하는 사유를 입력해주세요 (필수):`);
    
    if (reason === null) return;
    if (!reason.trim()) {
        alert("조치 사유를 입력해야만 처리가 가능합니다.");
        return;
    }

    try {
        const requestBody = {
            row_ids: rowIds.length > 0 ? rowIds : null,
            reason: reason
        };

        const response = await fetch(`/api/quarantine/${domain}/${actionType}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert(result.message);
            if (typeof updateDashboardStats === 'function') updateDashboardStats();
            if (typeof loadQuarantineTable === 'function') loadQuarantineTable(domain);
        } else {
            alert(`처리 실패: ${result.detail || '알 수 없는 오류가 발생했습니다.'}`);
        }
    } catch (error) {
        console.error("API 통신 에러:", error);
        alert("서버와 통신하는 중 오류가 발생했습니다.");
    }
}

function downloadMasterReport(domain) {
    if (!domain) {
        alert("선택된 도메인이 없습니다.");
        return;
    }
    window.location.href = `/api/download/${domain}`;
}