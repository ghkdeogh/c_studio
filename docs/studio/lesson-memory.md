# 피드백 선별과 적용 기록

제작 원칙은 [피드백 반영 절차](../../craft/doctrine/feedback-cycle.md)가 소유한다. 이 문서는 로컬 CLI·웹·데이터 계약이다. 외부 AI 호출 없이 조건·단어 기반으로 후보를 선별한다. 현재 사용자의 필수 지시는 검색 점수나 개수 제한으로 생략하지 않는다.

## 조회

```text
python -B _infra/creative-studio/production_assets.py lessons . --project productions/video/my-film --stage generation --model model-name --limit 6
python -B _infra/creative-studio/production_assets.py lessons . --query "요리 카메라" --browse --offset 6
```

--stage는 planning/generation/review. 기본 6개, 요청당 최대 20개. --query는 제목·행동·조건의 단어를 검색하며 --project가 있으면 BRIEF 내용도 관련도에 반영한다. --browse는 경고·조건 불일치 후보까지 살펴보는 모드다. --raw만 과거 형식의 전체 배열을 반환하며 기본 대화에서는 쓰지 않는다.

일반 응답은 items, total, source_count, group_count, duplicate_count, review_count, offset, limit, has_more, plan, constraints_source다. 각 후보는 원본 ref·source_hash, 묶인 refs, 추천 이유·주의·제외 사유, 검수 outcome별 독립 작품 수를 포함한다. 현재 작품·project 전용·archived·retired 원본은 전작 후보에서 제외한다. 기본 추천은 조건 불일치와 경고가 없는 항목만 반환한다. 제목이 같아도 행동·조건이 다르면 자동 병합하지 않는다. 기존 자연어의 의미적 중복·충돌을 모두 탐지한다고 보장하지 않는다.

## 원칙의 정본과 정리

기존 자유문장 조건 중 프리비즈·임시 효과음·드론·추적·바람 등 한정된 용도는 단어 규칙으로도 확인한다. 이번 작품 맥락에 대응하는 단어가 없으면 조건 확인 후보에 남긴다. 명시적인 learning.keywords가 있으면 그 조건을 우선한다. 이것은 모든 문장의 의미를 이해하는 분류가 아니므로 --browse에서 원문을 검토할 수 있다.

원본 feedback.json의 항목에 선택적 learning을 추가한다. 새 전역 원문 장부는 만들지 않는다.

```json
{
  "id": "pacing",
  "learning": {
    "topic": "tempo",
    "stance": "skip-empty-movement",
    "keywords": ["요리", "쇼츠"],
    "exclude_keywords": ["롱테이크"],
    "stages": ["planning", "review"],
    "models": [],
    "state": "active",
    "canonical_ref": "",
    "supersedes": []
  }
}
```

keywords 중 하나 이상이 작품 맥락과 일치해야 한다. exclude_keywords는 하나라도 일치하면 제외한다. 빈 목록은 제한 없음이다. models는 명시한 모델명과 일치해야 하며 모델 미지정 시 조건 확인 대상으로 남는다. state는 candidate/active/retired. 기존 applied는 영상 검증 성공 횟수가 아니다.

표현이 다른 기록을 합칠 때는 원문을 검토한 뒤 active 항목의 canonical_ref에 대표 원본 경로와 ID를 지정한다. 대표는 유효한 재사용 원본이어야 하며 모델·단계·키워드·제외 조건·방침이 같을 때만 묶는다. 대표를 연쇄 연결하거나 순환시키지 않는다. 대체는 active 항목의 supersedes 배열에 이전 원본 ref를 기록한다. 대체 원칙의 조건이 이번 작업에 맞을 때만 이전 원칙을 추천에서 제외한다. 순환은 경고로 남긴다.

```text
python -B _infra/creative-studio/production_assets.py lesson-rule productions/video/source-film --file rule-patch.json --revision 3
```

기존 항목 ID와 learning만 갱신한다. learning 변경은 feedback.json의 learning_history에 before/after를 보존한다. 원문을 바꾸지 않고 조건만 복원하려면 같은 명령에 `{"operation":"revert","id":"pacing","history_revision":4}`와 현재 --revision을 전달한다. 제작실의 피드백 수정 창에서도 재사용 조건과 방침을 편집할 수 있다.

## 이번 작품의 적용 기록

lesson-plan.json은 선택된 출처와 이번 적용 행동을 소유한다. schema_version=1, revision, items, history. 조회만으로 생성하지 않는다. 원문과 .studio 상태는 변경하지 않는다.

```json
{
  "revision": 0,
  "ref": "productions/video/source-film/feedback.json#pacing",
  "source_hash": "조회에서 받은 값",
  "stage": "applied",
  "application": "01의 불필요한 이동을 생략했다. 영상 검수는 남아 있다.",
  "cuts": ["01"],
  "evidence": ["shooting-script.md"],
  "outcome": ""
}
```

```text
python -B _infra/creative-studio/production_assets.py lesson-plan . --project productions/video/my-film --file application.json
```

stage는 planned/applied/reviewed/skipped. application은 필수이며 제외 이유도 여기에 쓴다. cuts는 등록된 컷 ID, 빈 배열이면 작품 전체다. applied는 실제 파일 근거가 필요하다. reviewed는 해당 컷 또는 전체본에 등록된 영상과 renders.md를 모두 요구하며 outcome은 helpful/ineffective/uncertain이다. 실제 영상 시청·청취와 판단은 기록 작성자가 수행한다.

저장 시 근거 파일의 크기·수정 시각을 보존하며 원본 source_hash나 파일 상태가 달라지면 stale로 표시하고 유효한 결과 집계에서 뺀다. 이것은 내용 분석이나 미디어 품질 자동 검사가 아니다. 수정 전 evidence만으로 현재 버전을 검수 완료로 표시하지 않는다.

동일 출처는 현재 항목을 갱신하고 history에는 변경 전후를 남긴다. `{"operation":"revert","ref":"출처","revision":현재값,"history_revision":복원대상변경번호}`를 같은 명령에 전달하면 해당 변경 직전으로 복원한다. 복원도 새 변경 이력을 남기며 오래된 원본·근거에 대한 stale 표시를 지우지 않는다. 쓰기는 배타적 잠금·revision 검사·atomic replace를 사용한다.

## 검수 후 개선 후보

조회 때 현재 lesson-plan의 유효한 reviewed 결과를 집계한다. 묶인 원칙의 동일 작품 기록은 결과별로 한 번만 센다. 서로 다른 작품의 helpful이 2개 이상이고 ineffective가 없으면 improvement_candidate=true다. 후보 표시는 의미적 검증·사용자 승인·성과 개선 확정이 아니며 source 원문이나 learning.state를 자동 변경하지 않는다. 근거 비교 후 원칙 조건을 갱신하는 후속 절차는 feedback-cycle을 따른다.

## 웹과 검증

`GET /api/lessons`: project/query/stage/model/limit/offset/browse(0 또는 1).
`POST /api/lesson-plan`: CLI와 같은 JSON에 project 추가. 기존 제작실 토큰 필요.
`/api/project`의 lesson_selection은 기본 추천과 적용 상태이며 lessons는 호환용으로 제한된 후보 배열이다. 전체 원문 배열을 프로젝트 자동 갱신 응답에 넣지 않는다.

제작실 피드백 화면에서 후보 찾기 → 적용·제외 기록 → 파일 반영/영상 검수 기록으로 이어진다. 조건 확인 후보와 최근 변경 복원은 별도로 제공한다. 로컬 서버 재시작 후 새 화면을 사용할 수 있다.

검증: test_lesson_memory.py, test_production_assets.py, ui-lessons-check.cjs. UI 검사는 임시 작품을 사용하며 STUDIO_NODE_MODULES에 Playwright가 있는 node_modules 경로를 지정할 수 있다.
