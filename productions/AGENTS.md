# 작품 제작 지침

사용자의 현재 요청과 상위 AGENTS.md를 따른다. 새 작품과 기존 작품 작업 전 저장소의 `docs/studio/project-contract.md`를 읽는다. 작품별 지침이 있으면 이어서 읽는다.

## 저장 위치
새 제작의 기본 저장소는 현재 복제한 저장소 루트이며 작품은 그 아래 `productions/video/<project-id>`에 만든다. 사용자가 별도 위치를 명시하면 그 위치를 우선한다. 기존 작품이 있는지 확인하고 중복 생성하지 않는다.

## 필수 실행
- 이전 작품 피드백은 [피드백 반영 절차](../craft/doctrine/feedback-cycle.md)에 따라 기획·프롬프트·생성·검수 각 진입점에서 확인한다. 완료 보고에는 실제 적용 근거와 미검수 단계를 구분한다.
- 대화에서 시작한 기획·스토리보드·콘티·대본·프롬프트·컷·인물·미디어 작업도 적용 대상이다. 별도 제작실 반영 요청을 기다리지 않으며, 요청 구분과 완료 기준은 [프로젝트 규약](../docs/studio/project-contract.md#대화-요청의-기본-처리와-완료-기준)을 따른다.
- 새 작품: 저장소 루트에서 `python -B _infra/creative-studio/project_store.py create <project-id> --title "작품 제목"`.
- 작품 재개: 생성상태.md → BRIEF.md 및 project.json, .studio/state.json(존재할 때)을 확인. 작업별 지침은 기존 라우터로 선택.
- 대화에서 컷·기획·이미지·영상이 나오면 project.json과 촬영 대본을 등록해 공통 제작실(http://127.0.0.1:8765)에 반영한다. 기본 전달을 위해 매번 별도 HTML을 만들지 않는다. 계획 시작·종료 이미지는 planned_start_image/planned_end_image, 실제 입력·결과는 기존 필드를 사용한다. 정확한 등록·검수·출력 계약은 docs/studio/project-contract.md를 따른다.
- 컷 등록·변경 후: `python -B _infra/creative-studio/project_store.py validate productions/video/<project-id>`.
- 웹이 읽는 project.json에는 계획 컷도 등록하고, 미생성 경로는 null. 경로 규약 위반을 덮어두고 완료로 보고하지 않는다.

## 보존과 사실
기존 시도는 덮어쓰지 않고 새 버전 폴더에 저장한다. 실제 입력과 결과의 연결을 확인한다. 웹 이미지 선택은 다음 생성 후보이며 이미 생성된 영상의 입력이라고 추정하지 않는다. `.studio`의 사용자 선택과 메모를 보존한다. 파일 구조와 CLI는 비용·업로드·공개 권한을 주지 않는다. API 키를 프로젝트에 저장하지 않는다.

이야기는 BRIEF.md, 진행점은 생성상태.md, 결과 판정과 비용 근거는 renders.md가 소유한다. project.json은 컷 목록과 경로를 연결하며 이 문서들의 전문을 복제하지 않는다.
