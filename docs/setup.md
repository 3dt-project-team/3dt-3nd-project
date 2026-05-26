# 로컬 개발 환경 초기 설정 가이드

> **대상**: 프로젝트에 처음 합류하는 팀원  
> **소요 시간**: 약 20~30분 (도구 설치 포함)

---

## 전체 흐름

```
1. 도구 설치 (Git · uv · Azure CLI)
        │
        ▼
2. 저장소 클론 & Python 환경 세팅  ← uv가 Python 3.11도 자동 설치
        │
        ▼
3. Azure 로그인 (az login)
        │
        ▼
4. 팀장에게 Key Vault 접근 권한 요청
        │
        ▼
5. .env 파일 작성
        │
        ▼
6. 연결 테스트 (vault_manager.py)
        │
        ▼
7. pre-commit 훅 등록
```

---

## 1. 도구 설치

### 1-1. Git

버전 관리 도구입니다. 이미 설치되어 있다면 건너뜁니다.

**Windows**

```powershell
winget install Git.Git
```

> winget이 없으면 https://git-scm.com/download/win 에서 설치 파일을 받으세요.

**macOS**

```bash
brew install git
```

> Homebrew가 없으면 https://brew.sh 에서 먼저 설치하세요.

**Linux (Ubuntu / Debian)**

```bash
sudo apt update && sudo apt install -y git
```

설치 확인:

```bash
git --version   # git version 2.x.x
```

---

### 1-2. uv (Python 패키지·버전 관리자)

`pip` + `pyenv` + `virtualenv`를 하나로 합친 도구입니다.  
**Python 3.11도 uv가 자동으로 설치**해 주므로 Python을 별도로 설치할 필요가 없습니다.

**Windows (PowerShell)**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

설치 후 터미널을 **새로 열고** 확인:

```bash
uv --version   # uv x.x.x
```

> 터미널을 새로 열지 않으면 `uv: command not found` 오류가 납니다.

---

### 1-3. Azure CLI

Azure 리소스를 명령줄에서 제어하고, 로컬 인증(`az login`)에 사용합니다.

**Windows (PowerShell)**

```powershell
winget install Microsoft.AzureCLI
```

> 설치 후 터미널을 **새로 열어야** `az` 명령이 인식됩니다.  
> winget이 없으면 https://aka.ms/installazurecliwindows 에서 MSI 파일을 받으세요.

**macOS**

```bash
brew install azure-cli
```

**Linux (Ubuntu / Debian)**

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

설치 확인:

```bash
az version   # "azure-cli": "2.xx.x"
```

---

## 2. 저장소 클론 & Python 환경 세팅

```bash
# 저장소 클론
git clone https://github.com/3dt-project-team/3dt-3nd-project.git
cd 3dt-3nd-project

# 의존성 설치 — Python 3.11 자동 다운로드 + 가상환경 생성까지 한 번에
uv sync
```

처음 실행하면 Python 3.11을 다운로드하므로 1~2분 정도 걸립니다.

```
Using Python 3.11.x
Creating virtualenv at .venv
Resolved xx packages in x.xxs
Installed xx packages in x.xxs
```

위처럼 뜨면 성공입니다.

**역할별 추가 설치**

```bash
# 데이터 분석가 — ML 라이브러리 포함 (scikit-learn, mlflow, azure-ai-ml)
uv sync --extra ml

# 데이터 엔지니어 — Databricks SDK 포함
uv sync --extra databricks
```

> 어떤 것을 설치해야 할지 모르겠다면 일단 `uv sync`만 실행하세요.  
> 나중에 추가로 실행해도 됩니다.

---

## 3. Azure 로그인

```bash
az login
```

실행하면 브라우저가 자동으로 열립니다.  
팀에서 지급한 계정(`3dtXXX@msacademy.msai.kr`)으로 로그인합니다.

로그인 성공 시 터미널에 아래와 같이 출력됩니다:

```
Tenant: 대한상공회의소 인력개발사업단
Subscription: 대한상공회의소 Data School (27db5ec6-d206-4028-b5e1-6004dca5eeef)
```

구독이 올바르게 선택됐는지 확인:

```bash
az account show --query "{name:name, id:id}" -o table
```

```
Name                        SubscriptionId
--------------------------  ------------------------------------
대한상공회의소 Data School  27db5ec6-d206-4028-b5e1-6004dca5eeef
```

위처럼 뜨면 정상입니다.

---

## 4. Key Vault 접근 권한 신청

Azure Key Vault는 팀 시크릿(DB 연결 문자열, API 키 등)을 보관하는 저장소입니다.  
접근하려면 팀장이 권한을 부여해야 합니다.

**팀원이 할 일**

팀장(또는 팀 채널)에 본인의 Azure 계정 이메일을 공유합니다.

```bash
# 본인 계정 이메일 확인
az account show --query "user.name" -o tsv
```

출력된 이메일(`3dtXXX@msacademy.msai.kr`)을 팀장에게 전달하세요.

> 권한 부여에는 팀장 측에서 1~2분, 전파에는 최대 3분이 걸립니다.  
> 팀장으로부터 "권한 부여 완료" 확인을 받은 뒤 다음 단계로 넘어가세요.

---

## 5. `.env` 파일 작성

프로젝트 루트의 `.env.example`을 복사합니다.

**Windows (PowerShell)**

```powershell
cp .env.example .env
```

**macOS / Linux**

```bash
cp .env.example .env
```

`.env` 파일을 열고 아래 두 항목을 채웁니다.  
나머지는 빈 채로 두어도 됩니다 (해당 리소스가 생성될 때 추가).

```dotenv
# ── Key Vault ─────────────────────────────────────────
KEY_VAULT_URL=https://kv-sense-team4.vault.azure.net/

# ── Azure ─────────────────────────────────────────────
# 로컬에서는 az login만 사용 — CLIENT_ID / SECRET 입력 불필요
AZURE_SUBSCRIPTION_ID=27db5ec6-d206-4028-b5e1-6004dca5eeef
```

> **⚠️ 중요**: `.env.example`에 있는 `AZURE_CLIENT_ID=`, `AZURE_CLIENT_SECRET=` 줄은  
> 값 없이 그대로 두면 인증 오류가 발생합니다.  
> 로컬 개발에서는 이 두 줄을 **삭제하거나 `#`으로 주석 처리**하세요.
>
> ```dotenv
> # AZURE_CLIENT_ID=      ← 이렇게 주석 처리
> # AZURE_CLIENT_SECRET=  ← 이렇게 주석 처리
> ```

---

## 6. 연결 테스트

모든 설정이 완료됐는지 확인합니다.

```bash
uv run python src/utils/vault_manager.py
```

**정상 출력:**

```
[OK] Key Vault 클라이언트 연결 완료: https://kv-sense-team4.vault.azure.net/
데이터 파이프라인 설정을 초기화합니다...
[결과] 성공 N개 / 실패 0개
```

`[OK]` 메시지가 뜨면 Azure 연결이 성공한 것입니다.

> **처음 실행 시 바로 실패하는 경우**: `az login` 직후 인증 캐시가 동기화되는 데  
> 시간이 걸릴 수 있습니다. 1~2분 기다린 뒤 다시 실행해 보세요.  
> 계속 실패하면 아래 **트러블슈팅** 섹션을 참조하세요.

---

## 7. pre-commit 훅 등록 (선택)

커밋 전에 자동으로 린트·포맷·시크릿 감지를 실행하는 훅을 등록합니다.

```bash
# Git 훅 등록 (최초 1회, 반드시 실행)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg

# 전체 파일 검사 (첫 실행 시 캐시 생성 — 약 30초 소요)
uv run pre-commit run --all-files
```

훅이 정상 등록되면 이후 `git commit` 시 자동으로 검사가 실행됩니다.

> 자세한 내용은 [`docs/git_guide/git_guide_workflow/05_precommit_setup.md`](git_guide/git_guide_workflow/05_precommit_setup.md)를 참조하세요.

---

## 완료 체크리스트

```
□ Git 설치 확인 (git --version)
□ uv 설치 확인 (uv --version)
□ Azure CLI 설치 확인 (az version)
□ uv sync 완료 (.venv 디렉토리 생성됨)
□ az login 완료 (구독: 대한상공회의소 Data School)
□ 팀장에게 Key Vault 권한 요청 및 수락 확인
□ .env 파일 작성 (KEY_VAULT_URL 채움, CLIENT_ID 주석 처리)
□ vault_manager.py 연결 테스트 성공 ([OK] 메시지 확인)
□ pre-commit install 완료
```

---

## 트러블슈팅

### `uv: command not found`

설치 후 터미널을 새로 열지 않아서 PATH가 반영되지 않은 상태입니다.  
터미널을 완전히 닫고 다시 열어서 재시도하세요.

---

### `az: command not found`

Azure CLI 설치 후 터미널을 새로 열지 않은 경우입니다.  
터미널을 새로 열어서 재시도하세요.  
계속 안 된다면 설치가 완료됐는지 다시 확인합니다.

---

### `AzureCliCredential: Failed to invoke the Azure CLI`

**원인**: `az login` 완료 직후 인증 캐시가 프로젝트 내부 디렉토리에 아직 복사되지 않은 상태입니다.

**해결 1**: 1~2분 기다린 뒤 다시 실행합니다.

**해결 2**: 아래 명령으로 캐시를 수동으로 복사합니다.

```powershell
# Windows PowerShell
$src = "$HOME\.azure"
$dst = Join-Path (Get-Location) ".azure-config"
foreach ($f in @("azureProfile.json","msal_token_cache.bin","msal_http_cache.bin","config","clouds.config")) {
    if (Test-Path "$src\$f") { Copy-Item "$src\$f" "$dst\$f" -Force; Write-Host "[OK] $f" }
}
```

```bash
# macOS / Linux
SRC=~/.azure DST=./.azure-config
for f in azureProfile.json msal_token_cache.bin msal_http_cache.bin config clouds.config; do
    [ -f "$SRC/$f" ] && cp -f "$SRC/$f" "$DST/$f" && echo "[OK] $f"
done
```

---

### `does not have secrets get permission`

Key Vault 접근 권한이 없습니다. 4단계로 돌아가 팀장에게 권한 부여를 요청합니다.  
권한을 받은 뒤 최대 3분 후 재시도하세요.

---

### `KEY_VAULT_URL 미설정` 메시지

```
[INFO] KEY_VAULT_URL 미설정 - 환경 변수에서 시크릿을 로드합니다
```

`.env` 파일에 `KEY_VAULT_URL`이 없거나 오타입니다. 5단계로 돌아가 확인합니다.

---

### `client_id should be the id of a Microsoft Entra application`

```
DefaultAzureCredential failed ... client_id should be the id of a Microsoft Entra application
```

`.env`에 `AZURE_CLIENT_ID=`처럼 빈 값이 있어서 발생합니다.  
해당 줄을 삭제하거나 `#`으로 주석 처리하세요.

---

## [팀장용] 새 팀원 Key Vault 권한 부여

팀원에게 권한을 부여하는 방법입니다.  
팀원에게 이메일을 받은 후 아래 명령을 실행합니다.

```bash
# 1. 팀원 objectId 조회
az ad user show --id 3dtXXX@msacademy.msai.kr --query id -o tsv

# 2. Key Vault 리소스 ID 저장
KV_ID=$(az keyvault show \
  --name kv-sense-team4 \
  --resource-group 3dt-final-team4 \
  --query id -o tsv)

# 3-A. 일반 팀원 — 읽기만 허용
az role assignment create \
  --assignee <1번에서-조회한-objectId> \
  --role "Key Vault Secrets User" \
  --scope $KV_ID

# 3-B. 시크릿 추가·수정 권한이 필요한 경우
az role assignment create \
  --assignee <1번에서-조회한-objectId> \
  --role "Key Vault Secrets Officer" \
  --scope $KV_ID
```

권한 부여 현황 확인:

```bash
az role assignment list \
  --scope $KV_ID \
  --query "[].{role:roleDefinitionName, principal:principalName}" \
  -o table
```

> 권한이 전파되는 데 최대 **2~3분**이 걸립니다.  
> 팀원이 연결 테스트에 실패하면 잠시 기다렸다가 재시도하도록 안내하세요.

---

## Azure 리소스 현황

| 리소스 | 이름 | 위치 | 용도 |
|---|---|---|---|
| 리소스 그룹 | `3dt-final-team4` | Korea Central | 모든 리소스 컨테이너 |
| Key Vault | `kv-sense-team4` | Korea Central | 시크릿 중앙 관리 |

> 리소스가 추가되면 이 표를 업데이트합니다.

---

*최초 작성: 2026-05-26*
