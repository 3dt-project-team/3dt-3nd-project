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