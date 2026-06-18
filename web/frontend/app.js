const dropZone = document.getElementById('drop-zone');
const dropZoneText = document.getElementById('drop-zone-text');
const dropZoneSubtext = document.getElementById('drop-zone-subtext');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('upload-status');
const uploadBtnArea = document.getElementById('upload-button-area');
const startUploadBtn = document.getElementById('start-upload-btn');

// 유저가 선택한 파일을 임시 보관할 변수 (대기실)
let selectedFile = null;

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

// 4. ✨ 파일이 대기실에 들어왔을 때 화면에 표시해주는 기능 (1단계 완수)
function handleFileSelected(file) {
    if (!file) return;
    
    selectedFile = file; // 파일 저장
    
    // 화면 텍스트를 파일 정보로 변경
    dropZoneText.innerHTML = `📄 <span class="text-indigo-400 font-bold">${file.name}</span>`;
    dropZoneSubtext.innerHTML = `<span class="text-slate-400">용량: ${(file.size / 1024).toFixed(1)} KB (준비 완료)</span>`;
    
    // 숨겨져 있던 적재 시작 버튼 영역 표시
    uploadBtnArea.classList.remove('hidden');
    statusDiv.innerHTML = ""; // 이전 알림 초기화
}

// 드롭존에 던졌을 때와 버튼으로 선택했을 때 모두 대기실로 연결
dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileSelected(files[0]);
});

fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) handleFileSelected(files[0]);
});

// 5. ✨ [신규] 적재 시작 버튼을 클릭했을 때 실제 백엔드로 발사 (2단계 완수)
startUploadBtn.addEventListener('click', () => {
    if (!selectedFile) {
        alert("적재할 파일이 선택되지 않았습니다.");
        return;
    }
    uploadFileToServer(selectedFile);
});

// 6. FastAPI 백엔드로 데이터 전송
function uploadFileToServer(file) {
    const company = document.getElementById('company').value.trim();
    const domain = document.getElementById('domain').value.trim();

    if (!company || !domain) {
        alert("Company(회사명)와 Domain(도메인명)을 입력해 주세요!");
        return;
    }

    // 전송 시작 시 버튼 비활성화하여 더블 클릭 방지
    startUploadBtn.disabled = true;
    statusDiv.innerHTML = `<span class="text-indigo-400 animate-pulse">⏳ [${file.name}] 카프카 브론즈 레이어로 적재 중...</span>`;

    const formData = new FormData();
    formData.append("company", company);
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
        // 성공 후 초기화
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

// --- 아래 격리 조치 및 다운로드 함수는 기존과 동일하게 유지됩니다 ---
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