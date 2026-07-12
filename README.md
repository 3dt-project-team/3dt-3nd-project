# Data Sentinel
 
**AI-Powered Multi-Tenant Data Quality Observatory Platform**
 
멀티테넌트 환경에서 도메인별 데이터 품질을 AI가 자동으로 진단하고 정제하는 Azure 기반 실시간 데이터 품질 관측 플랫폼입니다.
 
## 프로젝트 개요
 
데이터가 기하급수적으로 증가하는 환경에서 수동으로 검증 규칙을 정의하는 방식은 확장성에 한계가 있습니다. Data Sentinel은 AI가 데이터 스키마를 학습해 검증 규칙을 자동으로 생성하고, 실시간으로 이상 데이터를 탐지·격리함으로써 운영 효율성과 데이터 신뢰성을 동시에 확보하는 것을 목표로 합니다.
 
## 핵심 기능
 
- **AI 자동 규칙 생성**: 데이터 프로파일을 학습해 검증 규칙을 자동 생성, 수동 정의 부담 제거
- **멀티테넌트 대응**: E-commerce, Finance 등 다양한 산업 도메인의 데이터 구조에 유연하게 대응
- **지능형 모델 라우팅**: 도메인별 최적 LLM을 자동 선택해 검증 정확도와 비용 효율성 확보
- **실시간 정제·격리**: Structured Streaming 기반 30초 단위 폴링으로 이상치 실시간 탐지 및 격리
## 아키텍처
 
Kafka → ADLS(Bronze) → AI 기반 품질 검증 → 실시간 정제(Silver) → 분석 저장소(Gold) 로 이어지는 Medallion 기반 엔드투엔드 파이프라인
 
- **수집**: 웹 CSV 업로드 + 실시간 스트림 → Kafka 토픽 통합 → ADLS Delta 포맷 적재
- **AI 검증 규칙 생성**: 신규 도메인 진입 시 AI가 컬럼 스키마를 분석해 검증 규칙(JSON) 자동 생성, Redis 캐싱으로 재호출 비용 절감
- **실시간 정제**: Spark Structured Streaming(`foreachBatch`)으로 30초 단위 처리, 이상치는 별도 격리 영역에 저장, 격리 발생 시 5분 단위 배치 알림(Logic Apps)
- **자동 도메인 감지**: 백그라운드 폴링으로 신규 도메인을 코드 수정 없이 자동 인식
- **최종 통합**: Auto Loader 기반 증분 처리로 분석·서빙 가능한 저장소에 적재
## 기술 스택
 
`python` `pyspark` `Kafka` `Azure Databricks` `ADLS Gen2` `Spark Structured Streaming` `Redis` `Azure OpenAI` `Logic Apps` 
 
## 팀 구성 (4인)
 
| 이름 | 담당 |
|---|---|
| 임민규 | Data Engineering & Pipeline & Benchmark |
| 유기쁨 | AI Engine & Pipeline & Benchmark |
| 심우혁 | AI Engine |
| 박기은 | Database & Kafka * Web |

 
