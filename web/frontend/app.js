const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('upload-status');

// 1. 브라우저가 파일 드롭 시 자동으로 파일을 열어버리는 기본 동작 방지
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => e.preventDefault(), false);
});

// 2. 마우스로 파일을 끌고 박스 위로 올라왔을 때 (시각적 하이라이트 효과 On)
['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => {
        dropZone.classList.add('border-indigo-500', 'bg-slate-900');
        dropZone.classList.remove('border-slate-800', 'bg-slate-950/40');
    }, false);
});

// 3. 마우스가 박스 밖으로 나가거나 파일이 드롭되었을 때 (시각적 효과 원상복구 Off)
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => {
        dropZone.classList.remove('border-indigo-500', 'bg-slate-900');
        dropZone.classList.add('border-slate-800', 'bg-slate-950/40');
    }, false);
});

// 4. 파일 유입 경로 감지 (드롭존에 던졌을 때 vs 플러스 버튼으로 선택했을 때)
dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) uploadFileToServer(files[0]);
});

fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) uploadFileToServer(files[0]);
});

// 5. FastAPI 백엔드로 대용량 파일 폼 데이터 전송 (핵심 로직)
function uploadFileToServer(file) {
    const company = document.getElementById('company').value.trim();
    const domain = document.getElementById('domain').value.trim();

    // 빈값 방지 자물쇠
    if (!company || !domain) {
        alert("Company(회사명)와 Domain(도메인명)을 입력해 주세요!");
        return;
    }

    // 업로드 중 상태 표시 (노란색/인디고 연출)
    statusDiv.innerHTML = `<span class="text-indigo-400 animate-pulse">⏳ [${file.name}] 카프카 브론즈 레이어로 적재 중...</span>`;

    // Multipart Form 데이터 포장 (FastAPI 매개변수와 Key값 일치)
    const formData = new FormData();
    formData.append("company", company);
    formData.append("domain", domain);
    formData.append("file", file);

    // FastAPI 서버의 업로드 엔드포인트 호출
    fetch("/api/upload", {
        method: "POST",
        body: formData
    })
    .then(async (response) => {
        const data = await response.json();
        if (!response.ok) {
            // FastAPI가 준 400, 500번대 에러 메시지 그대로 가로채기
            throw new Error(data.detail || "카프카 파이프라인 전송 실패");
        }
        return data;
    })
    .then((data) => {
        // 성공 시 초록색 성공 메시지와 행 수 출력
        statusDiv.innerHTML = `<span class="text-emerald-400">✅ 적재 완수! ${data.message}</span>`;
    })
    .catch((error) => {
        // 실패 시 빨간색 에러 메시지 출력
        statusDiv.innerHTML = `<span class="text-rose-400">❌ 적재 실패: ${error.message}</span>`;
        console.error("Pipeline Error:", error);
    });
}

// =================================================================
// [기능 1] 격리 데이터 승인(Approve) 또는 폐기(Delete) 처리 함수
// =================================================================
/**
 * @param {string} actionType - 'approve' (마스터 병합) 또는 'delete' (폐기)
 * @param {string} domain - 현재 선택된 도메인 (예: 'wikipedia', 'traffic')
 */
async function processQuarantineAction(actionType, domain) {
    // 1. 테이블에서 체크박스가 선택된 행들의 row_hash 값들을 긁어모읍니다.
    // (HTML 테이블의 체크박스 클래스명을 'quarantine-checkbox'로 맞추시면 됩니다)
    const checkedBoxes = document.querySelectorAll('.quarantine-checkbox:checked');
    const rowIds = Array.from(checkedBoxes).map(cb => cb.value);

    // 2. 선택된 데이터가 없을 때의 예외 처리
    if (rowIds.length === 0) {
        const confirmAll = confirm("선택된 행이 없습니다. 해당 도메인의 '전체 격리 데이터'를 대상으로 조치하시겠습니까?");
        if (!confirmAll) return; // 취소 시 함수 종료
    }

    // 3. 🎯 현업 감사 추적을 위한 조치 사유 수집 (prompt 창 이용)
    const actionName = actionType === 'approve' ? '강제 승인 및 마스터 병합' : '데이터 폐기';
    const reason = prompt(`[${actionName}] 작업을 진행하는 사유를 입력해주세요 (필수):`);
    
    if (reason === null) return; // 유저가 취소 버튼을 누른 경우
    if (!reason.trim()) {
        alert("조치 사유를 입력해야만 처리가 가능합니다.");
        return;
    }

    // 4. 백엔드 API 호출 시작
    try {
        // rowIds가 비어있으면 null을 보내 백엔드에서 '전체 대상'으로 인식하게 합니다.
        const requestBody = {
            row_ids: rowIds.length > 0 ? rowIds : null,
            reason: reason
        };

        const response = await fetch(`/api/quarantine/${domain}/${actionType}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert(result.message);
            
            // 5. 조치 완료 후 화면 새로고침 함수들 호출
            if (typeof updateDashboardStats === 'function') updateDashboardStats(); // 대시보드 카운트 갱신
            if (typeof loadQuarantineTable === 'function') loadQuarantineTable(domain); // 격리 테이블 리로드
        } else {
            alert(`처리 실패: ${result.detail || '알 수 없는 오류가 발생했습니다.'}`);
        }
    } catch (error) {
        console.error("API 통신 에러:", error);
        alert("서버와 통신하는 중 오류가 발생했습니다.");
    }
}


// =================================================================
// [기능 2] 최종 마스터 정형 리포트 다운로드 함수
// =================================================================
/**
 * @param {string} domain - 다운로드할 도메인명 (예: 'wikipedia')
 */
function downloadMasterReport(domain) {
    if (!domain) {
        alert("선택된 도메인이 없습니다.");
        return;
    }
    
    // 아주르 스토리지에서 CSV 스트림을 받아 브라우저 다운로드 창을 켜는 가장 간단하고 확실한 방법
    window.location.href = `/api/download/${domain}`;
}