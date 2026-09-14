# 문서 라우팅

사용자 요청을 아래 태그로 분류한다. 여러 태그는 쉼표로 구분한다. 라우트 선언과 읽기 순서의 정본은 [routes.json](routes.json)이다. 아래 표는 자동 선택기를 사용할 수 없을 때의 진입점이다.

| 요청 | 태그 | 수동 진입 문서(작업 폴더 기준) |
|---|---|---|
| 문서 구조 수정 | repo-docs | docs/agent/README.md |
| 이야기 기획·스토리보드·콘티·대본·인물 기획 | story-planning (별칭 storyboard) | productions/AGENTS.md → docs/studio/project-contract.md → craft/doctrine/production-cycle.md |
| 프롬프트 작성 | prompt-writing | library/prompts/README.md |
| 로컬 실행 | local-run | docs/runbooks/local-generation.md |
| 유료 생성 | paid-generation | docs/runbooks/paid-generation.md |
| 작품 이어가기 | resume-project | 지정 작품에서 가장 가까운 생성상태.md → BRIEF.md |
| 결과 검수·전달 | review-delivery | docs/runbooks/review-delivery.md |
| 피드백 선별·원칙 정리·적용 기록·복원 | feedback-learning | craft/doctrine/feedback-cycle.md → docs/studio/lesson-memory.md |

repo-docs를 제외한 모든 제작 라우트는 `productions/AGENTS.md` → `docs/studio/project-contract.md` → `craft/doctrine/feedback-cycle.md`를 먼저 선택한다. 수동 선택에서도 이 세 문서를 표의 작업 문서 앞에 읽는다. 채팅에서 시작한 요청도 동일하며 “제작실”이라는 단어가 없어도 적용한다. 구체적인 저장·완료 기준은 프로젝트 규약, 전작 피드백의 활용 절차는 feedback-cycle이 소유한다.

기존 작품의 경로를 알면 모든 작업 태그에 `--path`를 함께 준다. `productions/*` 경로는 resume-project도 자동 선택하여 가까운 생성상태.md → BRIEF.md를 포함한다. 새 작품은 경로 없이 제작 라우트를 읽고 규약에 따라 생성한 뒤 작품 맥락을 확인한다. 작품별 AGENTS.md와 project.json, .studio/state.json, 관련 대본·자산은 규약에 따라 좁혀 읽는다. 대화에서 이어오던 작품을 매번 다시 묻지 않는다.

## 사용법
작업 폴더에서 실행한다.

```text
python -B _infra/doc-router/router.py --tags "story-planning" --json
python -B _infra/doc-router/router.py --tags "resume-project" --path "productions/_template" --json
python -B _infra/doc-router/router.py --check
python -B _infra/doc-router/tests/test_router.py
```

_template 경로는 모의시험용이며 실제 작품이 아니다. 실제 작업에서는 사용자가 지정한 작품 상대경로를 사용한다. 자동 선택기는 문서를 읽거나 실행하지 않고 선택 이유·존재·바이트를 출력한다. 상한 초과, 누락, 경로 오류 또는 작품 미지정이면 읽기를 멈추고 원인을 해결한다. 경고 구간에서는 요청을 더 좁힐 수 있는지 확인한다. 심볼릭 링크와 junction은 최종 경로를 검사한다.

## 문서 소유권
공통 안전·보존·권위는 [AGENTS.md](../../AGENTS.md)가 소유한다. 제작 원칙은 craft/doctrine, 모델 문법은 craft/playbooks, 프롬프트 관리 규칙은 library/prompts/README.md, 워크플로 수치는 개별 library/workflows 폴더의 README.md가 소유한다. 실행·복구는 docs/runbooks, 확정 이야기는 작품 BRIEF.md, 진행점은 생성상태.md, 결과 판정은 작품 renders.md가 소유한다. 전문 복제 대신 정본 경로를 연결한다.

## 유지보수
routes.schema.json은 JSON Schema 2020-12 계약이다. Python 선택기는 외부 패키지 없이 필수 구조·미정의 필드·경로·중복·존재·정책 상한·대표 태그를 검사한다. 일반 JSON Schema 엔진은 포함하지 않는다. 자연어 의미상의 중복 소유권은 문서를 검토하여 확인한다.
로컬에서 .agent-system.json을 사용하는 경우 관리 파일의 구축 시점 SHA-256만 보관한다. 이 파일은 공개 저장소에 포함하지 않는다. 사용자 편집 후 기준 해시를 자동 갱신하지 않는다. 작품과 결과물은 관리 파일에 추가하지 않는다.
