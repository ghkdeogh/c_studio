# Creative Studio 프로젝트 규약 v1

## 저장소와 시작점

새 제작 작업의 기본 저장소는 현재 복제한 저장소 루트다. 앱과 작품은 이 저장소 안에서 분리한다. 프로젝트 내부에는 상대 경로만 쓴다.

```text
CreativeStudio/
  AGENTS.md                       공통 규칙과 문서 라우터 안내
  _infra/creative-studio/          앱과 프로젝트 생성·검증 CLI
  _infra/doc-router/              작업별 문서 선택
  docs/studio/                    프로젝트 데이터 규약
  craft/                         제작 원칙
  library/                       프롬프트·워크플로 지침
  productions/
    AGENTS.md                     모든 작품에 적용되는 작업 절차
    video/<project-id>/
      AGENTS.md                   작품 진입 안내
      BRIEF.md                    이야기·사용자 제약의 정본
      생성상태.md                 현재 진행점·다음 단계의 정본
      renders.md                  실제 결과·품질 판정·비용 근거의 정본
      shooting-script.md          컷별 대사·동작·카메라 계획
      project.json                앱용 컷 순서와 선택된 결과 경로
      references/characters/      인물 기준 자료
      references/locations/       배치도·공간 기준 자료
      shots/<cut-id>/v001/        해당 시도의 입력·요청·출력 기록
        input.png                 실제 생성에 쓴 로컬 이미지
        request.json              모델·프롬프트·입력 역할
        result.mp4                실제 결과 원본
        actual-end.png            확보된 실제 끝 프레임
        result.json               작업 ID·상태·결과 URL·확인된 비용
      assets/                     기존 자산 및 호환 자료
      exports/                    새 전체본·최종 출력(v001 등)
      .studio/state.json          웹의 다음 입력 선택·이미지 버전·컷 메모
      .studio/images/             웹에서 가져온 이미지 원본
```

위 파일은 단계에 맞춰 만든다. 아직 없는 결과 파일은 가짜로 만들지 않는다. 새 컷 ID는 안정적으로 유지하고 순서는 `project.json.cuts` 배열로 관리한다. 재시도는 v002 등 새 폴더에 저장한다. 기존 가져온 작품의 파일명과 폴더는 호환 상태로 유지하며 이 규약에 맞추려고 일괄 이동하지 않는다.

## Codex의 작업 순서

### 대화 요청의 기본 처리와 완료 기준

- 전작 피드백의 조회·선택·단계별 근거·완료 보고는 [피드백 반영 절차](../../craft/doctrine/feedback-cycle.md)를 따른다. 제작실의 재사용 목록 표시는 자동 적용이나 영상 검수 완료를 의미하지 않는다.

- “스토리보드 만들어줘”, “이 컷 대사 바꿔줘”, “프롬프트 정리해줘”, “이 이미지로 교체해줘”는 해당 작품의 로컬 파일과 제작실 등록까지 요청한 것으로 처리한다. 채팅에 작성한 뒤 “제작실에도 반영할까요?”라고 다시 묻지 않는다. 설명·평가·아이디어 상담만 요청한 경우와 저장하지 말라는 요청은 파일 수정 없이 답한다.
- 현재 대화의 작품을 이어간다. 기존 작품은 작품별 AGENTS.md, 생성상태.md → BRIEF.md, project.json, .studio/state.json(존재 시)을 확인하고 관련 대본·인물·컷만 추가로 읽는다. 작품 경로를 알면 작업 태그와 함께 라우터에 --path를 넘긴다. 새 작품 요청은 기존 작품과 중복되지 않는지 확인한 뒤 create CLI로 시작한다. 이름이 없으면 내용에 맞는 임시 제목을 사용할 수 있으나, 기존 작품 대상이 모호할 때 새 작품을 임의 생성하지 않는다.
- 스토리보드·콘티·대본 작업은 최신 shooting-script의 5열 표와 project.json의 계획 컷·순서·script_file 연결까지 반영한다. 기획 초안은 대본에 초안으로 표시하고 생성상태.md에 검토 대기와 다음 행동을 남긴다. 확정된 이야기만 BRIEF.md에 반영하며, 제작실에 등록했다는 이유로 이야기나 결과를 승인 상태로 바꾸지 않는다.
- 프롬프트·인물·이미지·영상 작업은 아래 등록 계약에 따라 해당 정본과 실제 파일 연결을 갱신한다. 연결된 기존 결과가 있으면 과거 생성에 사용된 기록을 보존하고 새 계획과 구분한다. 미생성 미디어는 null로 두며 텍스트 콘티 요청만으로 이미지·영상 생성이나 외부 업로드를 시작하지 않는다.
- 완료 전에는 수정 내용을 다시 읽고 project_store.py validate를 통과시킨다. 대본의 요청 대상 컷과 project.json의 id/script_ids 연결, 최신 script_file, 등록한 파일의 존재도 확인한다. 검증 실패는 가능한 범위에서 수정하고 다시 확인한다.
- 제작실에서 해당 작품과 변경한 컷이 열리는지 확인한다. 접속·화면 확인이 불가능하면 로컬 저장·등록·검증은 끝내고, 최종 답변에서 화면 확인이 남았음을 구분한다. 확인하지 않은 표시 상태를 완료로 보고하지 않는다.
- 최종 답변은 어느 작품의 무엇을 반영했는지, 검증 결과, 해당 제작실 작품 링크를 짧게 전달한다. 질문·상담만 한 경우에는 반영 완료라고 표현하지 않는다.

### 실행 순서

1. 저장소 AGENTS.md와 `productions/AGENTS.md`, 이 문서를 읽는다. 작업 태그에 따라 문서 라우터를 실행한다. 작품 작업은 해당 BRIEF.md·생성상태.md를 읽고, `project.json`과 `.studio/state.json`을 확인한다.
2. 새 작품은 저장소 루트에서 아래 CLI로 만든다. 사용자의 일반 작품 제작 요청은 템플릿 생성 권한을 포함하지만 유료 생성·외부 업로드 권한은 별도 사용자 요청에서 판단한다.

```powershell
python -B _infra/creative-studio/project_store.py create my-film --title "내 작품"
```

3. 기획을 BRIEF와 촬영 대본에 기록하고, `project.json`에 계획 컷을 등록한다. 미생성 파일 경로는 null. 계획 컷도 웹에 나타난다.
4. 생성 전에 웹에서 고른 이미지가 있는지 `.studio/state.json`의 해당 컷 selected를 확인한다. 이 선택은 다음 생성 입력 후보이며 기존 영상이 그 이미지로 생성됐다는 증거가 아니다. 참고 이미지·시작 이미지·끝 이미지를 구분하고, 실제 업로드한 파일과 역할을 request.json에 기록한다.
5. 앞 컷 연결은 실제 끝 프레임과 공간·손·소품 상태를 확인한다. 같은 이미지를 여러 컷에 재사용했다면 실제 끝 프레임 연결이라고 보고하지 않는다.
6. 도구가 반환한 실제 결과를 보존하고 `project.json`에 해당 video, input_image, end_image, request_file 경로를 등록한다. input_image는 실제 사용이 확인된 이미지다. 확인할 수 없으면 null.
7. 결과 판정과 확인된 비용은 renders.md, 진행점은 생성상태.md에 기록한다. 앱용 cost/budget 값은 기록의 요약이며 실시간 잔액이나 별도 승인으로 해석하지 않는다.
8. 아래 검증을 통과시키고 웹에서 결과가 열리는지 확인한다. 앱은 3초마다 프로젝트 목록과 파일 변경을 확인한다. project.json과 대본을 등록하면 별도 HTML 작성 없이 화면에 반영된다. 열린 컷의 미저장 내용은 자동 갱신으로 덮어쓰지 않는다.

```powershell
python -B _infra/creative-studio/project_store.py validate productions/video/my-film
```

## project.json 계약

```json
{
  "schema_version": 1,
  "id": "my-film",
  "title": "내 작품",
  "kind": "video",
  "full_video": null,
  "cuts": [
    {
      "id": "01",
      "name": "첫 입장",
      "status": "planned",
      "video": null,
      "input_image": null,
      "end_image": null,
      "request_file": null,
      "duration": null,
      "start": null
    }
  ]
}
```

- status: planned / ready / generating / review / approved / rejected. 사용자 확인을 받지 않은 결과를 approved로 바꾸지 않는다.
- duration은 실제 결과 길이, start는 현재 전체본에서의 시작 시간(초). 계획 길이는 shooting-script에 쓴다. 전체본에 포함되지 않았으면 start=null.
- 모든 파일 경로는 작품 기준 상대 경로이며 `/`를 사용한다. 드라이브 절대 경로·외부 URL·`..` 이탈 경로를 넣지 않는다. 원격 URL은 result.json 실행 기록에 남긴다.
- `.studio`는 웹이 소유한다. Codex는 읽을 수 있지만 사용자의 선택·메모를 덮어쓰지 않는다. 새 영상으로 웹 선택을 소비한 경우에도 선택 이력을 임의 삭제하지 않는다.
- 메모·이미지 선택은 저장 버튼 또는 교체 동작에서 저장된다. 동시에 외부에서 .studio/state.json을 편집하지 않는다.
- JSON 변경은 임시 파일 작성 후 atomic replace. 같은 작품에 여러 에이전트가 쓰는 경우 쓰기 담당을 하나로 정한다.

## 이전 작품

기존 작품을 새 저장소에 복사한 뒤 `adopt`로 현재 확인 가능한 결과만 등록한다. 빈 작품은 빈 cuts 배열로 시작한다. 자동 추측이나 과거 영상 채택은 하지 않는다. 이전 HTML은 당시 기록이며 최신 화면은 project.json을 읽는 앱이다. 가져온 과거 실행 스크립트의 절대 경로는 보관 당시 위치일 수 있으므로 그대로 실행하지 말고 현재 작품 경로를 확인해 수정한다.

```powershell
python -B _infra/creative-studio/project_store.py adopt productions/video/legacy-film
```

유료 생성은 Codex에서 사용자 요청 범위를 확인해 실행한다. 웹은 로컬 FFmpeg로 사용자가 저장한 구간을 연결하여 원본 전체본과 편집본을 출력한다. 생성 API는 웹에 연결하지 않는다.


## 웹의 기획·콘티·연결 화면
- 작품 개요는 BRIEF.md를 직접 읽는다. 기획 요약을 웹 전용으로 복제하지 않는다.
- project.json의 script_file에 최신 촬영 대본의 상대 경로를 지정한다. 새 작품 기본값은 shooting-script.md다.
- 촬영 대본의 표는 `컷 | 목표 | 대사·말투 | 시간 안의 사건 | 카메라·소리·끝 연결` 5열로 쓴다. 첫 열은 `01 입장`처럼 컷 ID와 이름을 띄운다. 표 안에 구분자 |를 넣지 않는다.
- 하나의 영상이 여러 계획 컷을 포함하면 해당 컷에 script_ids: ["01B", "01A2"]를 지정한다. 없으면 자신의 id로 연결한다.
- planned_start_image와 planned_end_image는 선택적인 계획 이미지 상대 경로다. 실제 영상의 input_image/end_image와 구분한다. 영상 미생성 컷에서도 계획 이미지를 보여준다. 영상의 첫 프레임은 실제 프레임 번호 0으로 추출하고, 마지막 프레임은 실제 count-1로 추출하거나 확보된 actual-end를 표시한다.
- 편집 화면은 포함할 생성 컷과 순서를 저장하고, 컷별 사용 구간을 모두 저장한 뒤 두 영상 이어붙이기를 실행한다. 같은 원본·순서로 전체 길이 연결본과 트림 연결본을 새 버전 폴더에 출력한다.
- 새 작품과 컷은 자동 갱신되며 다시 불러오기 버튼도 제공한다. 주 검수 주소는 http://127.0.0.1:8765/?project=productions%2Fvideo%2F작품ID 이다. 새 결과를 전달할 때 버전별 HTML을 만드는 대신 이 사이트의 작품을 연다.

## 대화 → 사이트 등록 절차
1. 새 작품은 기존 create CLI를 사용한다. BRIEF.md에 컨셉, shooting-script.md의 5열 표에 컷별 대사·동작·카메라를 기록한다. 최신 문장이 표와 별도 섹션에서 충돌하지 않도록 표도 갱신한다.
2. 컷 패치 JSON을 준비하고 `python -B _infra/creative-studio/project_store.py upsert-cut productions/video/<id> --file <patch.json>`으로 등록한다. ID가 있으면 해당 필드만 병합하고 없으면 계획 컷을 추가한다. 검증 실패 시 project.json을 쓰지 않는다. .studio를 수정하지 않는다.
3. 정지 이미지에는 planned_start_image/planned_end_image를 사용한다. 생성 완료 후 실제 video/input_image/end_image/request_file/duration을 별도로 등록한다. 등록되지 않은 임의 폴더를 결과로 추측하지 않는다.
4. 사이트에서 프레임 시각은 ffprobe의 실제 PTS를 사용한다. 사용 구간은 0기반 in_frame 이상, out_frame 미만이며 SHA-256과 함께 .studio/state.json의 cuts[ID].trim에 저장된다. 화면의 ‘이 프레임까지’는 현재 프레임을 포함하도록 out_frame=index+1로 저장한다.
5. 원본 변경 시 구간을 다시 검수한다. 잘못된 범위·다른 원본 해시·다른 창의 오래된 구간 저장 요청은 거부한다. 메모·이미지 버전은 보존한다.
6. .studio의 timeline은 생성 컷 ID 순서다. 웹 API가 저장하며 Codex는 파일을 직접 덮어쓰지 않는다. 과거에 사용자가 지정한 구간을 이전할 때도 웹 저장 API를 사용한다.
7. 출력은 exports/studio-<시각>-<고유값>/raw.mp4와 edited.mp4, job.json에 저장한다. job.json은 입력 해시·프레임 경계·배치 시각·변환 조건·실제 결과의 실행 증거다. 결과 평가는 renders.md, 다음 단계는 생성상태.md가 소유한다.
8. 출력은 첫 원본의 해상도/프레임률에 맞춰 재인코딩하며 화면비는 패딩으로 보존한다. 음성은 해당 영상 구간과 연결하고 부족한 음성/무음 트랙은 무음으로 채운다. 음악·효과·배속·음량 변경은 추가하지 않는다. 서로 다른 fps나 VFR을 같은 출력 fps로 통일할 때의 프레임 복제/제거는 실행 기록에 명시한다.
9. 출력 상태는 사이트에서 확인한다. 실패한 작업은 이유를 표시하고 새 작업으로 재시도한다. 성공 전에는 완료로 표시하지 않으며 원본·이전 출력은 삭제하지 않는다.

## 인물시트와 제작 피드백

피드백이 쌓일 때의 선별·원칙 정리·적용 이력은 [피드백 선별과 적용 기록](lesson-memory.md)이 소유한다. 원본 feedback.json과 선택적 learning은 전작 경험의 정본, lesson-plan.json은 이번 작품의 적용·검수 기록이다. 기존 원문을 새 작품으로 복제하지 않는다.

모든 프로젝트에 인물·시트 및 피드백·다음 작품 화면을 제공한다. 기존 프로젝트에 파일이 없으면 빈 상태로 표시하며 새 프로젝트 CLI는 characters.json과 feedback.json을 자동 생성한다. project.json과 .studio의 미디어·구간·메모는 변경하지 않는다.

characters.json: schema_version=1, revision, items. 인물별 id/name/role/description/appearance/wardrobe/performance/continuity/source/status, images 배열. status는 draft/reference/approved. 이미지는 작품 내부의 실제 파일 path, 설명 label, 종류 kind(sheet/reference/detail)로 등록한다. 캐릭터 설명과 연결 파일의 정본이며 확정된 서사·관계는 BRIEF.md를 참조한다. 이미지 추가는 별도 파일로 보존한다.

feedback.json: schema_version=1, revision, items. 각 기록은 id/title/observation/action/context/evidence/source/origin/tags/scope/status. origin=user/review/reference, scope=project/reusable, status=open/applied/archived. 다음 작품 참고 목록은 원본 장부들을 읽어 합치며 별도 전역 복사본을 만들지 않는다. 과거 피드백은 현재 요청을 덮어쓰는 명령이 아니다.

Codex 등록: `python -B _infra/creative-studio/production_assets.py upsert <작품> --kind characters --file <인물.json>` 또는 `--kind feedback`. 조회는 list, 전체 재사용 기록은 `lessons <작업폴더>`. 웹 저장은 /api/characters, /api/feedback을 사용하며 토큰과 revision으로 오래된 저장을 거절한다. .studio의 사용자 선택·메모는 직접 수정하지 않는다.

## 게시 성과와 다음 작품 회고

작품의 `youtube-analytics.json`은 게시 영상 연결과 수집 시점별 성과 수치의 정본이다. `schema_version=1`, `revision`, `links`, `snapshots`를 가진다. 기존 `exports/*/youtube-publication.json`은 게시 증거로 읽어 연결 후보를 표시하며 자동으로 덮어쓰지 않는다. 연결은 영상 ID, 채널 ID, 제목, 게시일, 작품 내부 업로드 원본 MP4 경로, 게시 기록 경로를 보관한다.

각 snapshot은 고유 id, 영상 ID, 요청 시작일·종료일, 확인 시각과 시간대, 저장 시각, 출처, 지표, 집계 메모를 보존한다. 출처 `youtube_api`는 서버가 Google API에서 직접 수집한 기록에만 사용한다. `studio_manual`은 사람이거나 Codex가 Studio 화면을 확인해 입력한 값이다. 기록은 추가 방식으로 저장하며 revision이 오래되면 저장을 거절한다. 제공되지 않은 값은 null이며 실제 0과 구분한다. API 날짜는 Pacific Time, 화면 기록은 사용자가 확인한 Studio 선택 기간이다. 일별 데이터 마지막 날짜와 요청 종료일을 구분한다. 서로 다른 기간·출처의 값을 자동 병합하지 않는다.

회고는 기존 `feedback.json` 항목에 선택적 `retrospective`를 연결한다. 필드: video_id, snapshot_id, hypothesis, experiment, success_measure, scene_seconds(초 또는 null), confidence(hypothesis/supported/inconclusive). 근거 snapshot은 반드시 같은 작품에 존재해야 한다. 수치 자동 정리는 규칙 기반 초안이며 AI가 영상을 시청한 결과로 표시하지 않는다. 가설·다음 실험·비교 기준을 작성한 뒤 저장한다. `scope=reusable`인 회고는 기존 피드백과 같이 다음 작품 참고 목록에서 원본을 읽는다. 확정 이야기나 현재 제작 지시를 자동 변경하지 않는다. 품질의 최종 판정은 기존 `renders.md`가 소유한다.

인증 정보는 작품과 저장소에 넣지 않는다. 로컬 연결 설정·제약·테스트 절차는 [_infra/creative-studio/README.md](../../_infra/creative-studio/README.md)의 YouTube 연결을 따른다.
