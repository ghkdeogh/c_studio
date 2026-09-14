# Creative Studio 앱

실행 저장소는 이 코드를 복제한 저장소 루트다.
앱 코드는 _infra/creative-studio, 작품은 productions/video/<project-id>에 둔다.

실행: 저장소 루트의 Start-Studio.cmd 또는 python _infra/creative-studio/server.py.
기본 주소 http://127.0.0.1:8765. 루프백 전용, Python 표준 라이브러리 사용.

## 데이터
- project.json이 있으면 이를 우선 검증하고 컷 목록·실제 입력·영상·끝 프레임·프롬프트 경로를 읽는다.
- 없는 이전 작품은 호환 어댑터로 읽는다. 새 작품은 project_store.py create로 만든다.
- 웹의 이미지 선택·버전·메모는 작품 .studio에 저장한다. 원본을 덮어쓰지 않는다.
- 생성 및 유료 API는 연결하지 않았다. Codex가 생성하고 project.json으로 결과를 등록한다.
- 3초마다 새 프로젝트·컷·이미지·영상·대본을 자동 반영한다. 검수 중 열린 컷과 미저장 구간은 보존한다.
- 컷별 소수점 3자리 PTS, 실제 프레임 이동, 배속, 사용 구간 저장을 제공한다.
- 편집 목록에서 포함/순서를 저장하면 원본 전체와 편집 구간 연결본을 비동기로 출력한다. FFmpeg/ffprobe가 PATH에 있어야 한다.
- 시작·종료 계획 이미지는 planned_start_image/planned_end_image로 등록한다.
- 대화에서 컷이 나오면 project_store.py upsert-cut으로 등록한다. 추가 HTML은 필요 없다.

정확한 폴더 규칙과 Codex 절차: ../../docs/studio/project-contract.md.

## 검증
python -m unittest discover -s _infra/creative-studio -p "test_*.py"

임시 작품에서 생성/중복방지/검증/계획 컷/이미지 교체/복원/메모/Range/경로제한 검증.
ui-workspace-check.cjs는 임시 작품으로 로컬 브라우저를 검사한다. 선택 의존성 설치는 루트 README.md를 따른다.

## 출력 검증
`test_editing.py`는 실제 임시 영상을 만들어 프레임 경계·원본 변경·동시 저장 충돌·메모 보존·서로 다른 fps·무음 원본·비동기 출력·해시 보존을 확인한다.

## 인물과 피드백
인물·시트에서 인물 설명과 기준 이미지를 관리한다. 피드백·다음 작품에서 피드백을 저장하고 범위/분류/조건별로 다음 작품에 참고한다. `production_assets.py`의 list/upsert/lessons CLI는 .studio를 변경하지 않는다. 정본과 필드는 docs/studio/project-contract.md를 따른다.

추가 검사: `ui-workspace-check.cjs`는 임시 프로젝트에서 저장·업로드·메모 승격·공유·모바일을 검사한다. 서버 코드 변경은 기존 제작실 서버를 종료하고 Start-Studio.cmd로 다시 시작해야 반영된다.

## YouTube 성과 연결

피드백 · 다음 작품의 상단에서 사용한다.

1. 게시 기록을 발견하면 ‘이 영상 연결’을 누르거나 영상 주소를 직접 연결한다.
2. 계정 연결 전에는 ‘Studio 지표 기록’으로 확인한 수치를 입력할 수 있다. 같은 기간의 수치만 함께 저장하고 미집계 항목은 비운다.
3. API 연결은 ‘연결 설정’에서 Google Cloud **데스크톱 앱** OAuth 클라이언트 JSON을 등록한다. 다운로드가 어려우면 ‘파일 없이 직접 입력’에서 같은 데스크톱 클라이언트의 ID와 보안 비밀번호를 입력한다. 입력값은 저장 또는 창 닫기 뒤 화면에서 제거한다. Google Cloud에서 YouTube Data API v3와 YouTube Analytics API를 사용 설정하고 OAuth 동의 화면과 테스트 사용자를 준비한다. 웹 애플리케이션용 JSON과 API 키는 이 연결에 사용할 수 없다.
4. ‘Google 계정 연결’은 기본 시스템 브라우저를 연다. `youtube.readonly`, `yt-analytics.readonly`만 요청한다. 채널 선택 및 Google 동의는 사용자가 완료한다. 재접속 시에도 별도로 읽기 권한이 필요할 수 있다.
5. ‘API 성과 가져오기’에서 시작·종료일을 선택한다. API 날짜는 Pacific Time 기준이다. 소유 채널과 영상이 일치하는지 확인한 뒤 기본 성과, 유입 경로, 일별 성과, 구간별 유지율을 요청한다. 일부 보조 보고서가 실패해도 기본 수치는 출처·실패 사유와 함께 저장한다. 전체 결과가 없으면 0으로 저장하지 않는다. 자동/예약 수집은 구현하지 않았으며 사용자가 버튼을 누를 때만 수집한다.
6. 성과 기록을 선택해 회고를 작성한다. 규칙 기반 사실 요약에 가설·다음 실험·비교 기준을 추가한다. ‘다음 작품에도 참고’로 저장하면 다른 작품에서 원본 회고를 읽을 수 있다. 유지율 데이터와 등록한 원본이 있으면 영상 구간으로 이동해 함께 검토할 수 있다.

인증 파일은 `%LOCALAPPDATA%/CreativeStudio/youtube-oauth.bin`에 Windows DPAPI로 암호화한다. 프로젝트 파일 및 브라우저 응답에 토큰을 넣지 않는다. OAuth에는 만료·일회성 state와 PKCE를 사용한다. 콜백은 로컬 `/api/youtube/oauth/callback`이며 Google API 주소는 고정한다. 새 클라이언트 JSON으로 바꾸면 기존 연결이 교체된다. 앱 연결 해제는 Google 계정의 연결된 앱 관리에서 수행한다. Google 테스트 모드의 인증 만료나 API 한도 오류는 화면에 안내한다.

현재 수집하는 항목: 조회수, 유효 조회수, 평균 시청 시간/조회율, 시청 시간, 구독자 증감, 좋아요·댓글·공유, 유입 경로, 일별 성과, 구간별 시청 유지율. ‘계속 시청함/이탈함’은 현재 API 어댑터에서 수집하지 않으며 Studio 기록으로 입력한다. 데이터 제공 여부와 조합 지원은 채널·기간·Google 정책에 따라 달라질 수 있다. 인증 전의 API 테스트는 모의 응답 검증이며 실제 채널 접속 성공을 의미하지 않는다.

검사: `python -B -m unittest discover -s _infra/creative-studio -p "test_*.py"`. `test_youtube.py`는 원본 보존, 경로 제한, 기록 충돌, 결측값·0 구분, API 부분 실패, 다른 채널 거부, 회고 근거, OAuth 암호화·재사용 방지·토큰 갱신을 검증한다.

참조: [채널 보고서](https://developers.google.com/youtube/analytics/channel_reports), [보고서 조회](https://developers.google.com/youtube/analytics/reference/reports/query), [데스크톱 OAuth](https://developers.google.com/identity/protocols/oauth2/native-app). 데이터 계약은 [프로젝트 규약](../../docs/studio/project-contract.md#게시-성과와-다음-작품-회고)을 따른다.
