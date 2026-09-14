# Creative Studio

AI와 함께 영상 작품을 기획하고 검수하는 로컬 제작실입니다. 웹앱, 프로젝트 생성 CLI, 에이전트 지침, 문서 라우터와 빈 작품 템플릿을 제공합니다.

## 빠른 시작

Python 3.11 이상과 Git이 필요합니다. 기본 앱은 Python 표준 라이브러리만 사용합니다.

```sh
git clone https://github.com/ghkdeogh/c_studio.git
cd c_studio
python -B _infra/creative-studio/server.py
```

브라우저에서 http://127.0.0.1:8765 를 엽니다. Windows에서는 `Start-Studio.cmd`를 실행해도 됩니다. 처음에는 작품 목록이 비어 있습니다.

새 작품은 저장소 루트에서 만듭니다.

```sh
python -B _infra/creative-studio/project_store.py create my-film --title "내 첫 작품"
python -B _infra/creative-studio/project_store.py validate productions/video/my-film
```

새 작품은 `productions/video/my-film/`에 만들어지고 웹에 자동 반영됩니다. 인물, 기획, 컷, 검수 메모와 제작 피드백을 관리할 수 있습니다.

## 에이전트와 작업하기

복제한 폴더를 에이전트의 작업 폴더로 열고 다음처럼 요청합니다.

> AGENTS.md와 productions/AGENTS.md, docs/studio/project-contract.md를 읽고 새 영상 작품을 만들어줘. 제목은 ○○, 주제는 ○○. 기획부터 시작하자.

에이전트는 작업 태그에 따라 필요한 문서를 선택하고, 계획 컷과 생성 결과를 `project.json`으로 웹에 연결합니다. 이야기·진행점·검수 결과는 작품별 문서에서 관리합니다.

## 구성

| 위치 | 역할 |
|---|---|
| `_infra/creative-studio/` | 웹앱, 작품 CLI, 미디어 편집, 테스트 |
| `_infra/doc-router/` | 작업별 문서 선택과 정책 검사 |
| `docs/agent/` | 문서 라우팅 설정과 스키마 |
| `docs/studio/` | 프로젝트 데이터 계약 |
| `docs/runbooks/` | 실행·검수 절차 |
| `craft/` | 제작 원칙과 모델별 지침 색인 |
| `library/` | 공통 프롬프트·워크플로 관리 지침 |
| `productions/_template/` | 내용이 없는 작품 문서 템플릿 |

## 선택 기능

- 프레임 분석과 영상 이어붙이기에는 `ffmpeg`와 `ffprobe`가 PATH에 필요합니다. H.264 출력에는 libx264 지원 빌드가 필요합니다.
- YouTube 성과 연결은 선택 사항이며 Windows DPAPI를 사용합니다. 각 사용자가 자신의 Google OAuth 클라이언트와 계정을 설정합니다.
- 이미지·영상 생성 API, 모델, API 키, 유료 구독과 외부 플러그인은 포함하지 않습니다. 생성은 사용자가 준비한 도구에서 수행하고 결과를 등록합니다.
- 기본 서버는 로컬 주소에만 바인딩합니다. 공개 웹 호스팅용 서버는 아닙니다.

## 작품과 개인 데이터

이 저장소에는 실제 작품, 생성 이미지·영상, 채널 자산, 계정 정보, 실행 로그와 이전 작업 기록이 없습니다. `productions/` 아래에는 공통 지침과 빈 템플릿만 추적합니다. 새 작품, `.studio`, 채널 폴더, 임시 파일과 인증 파일은 `.gitignore`로 제외합니다. 제외 파일을 강제로 추가하지 마세요.

변경을 공유하기 전 공개 파일 검사를 실행합니다.

```sh
python -B _infra/check_public.py
```

## 검증

```sh
python -B _infra/doc-router/router.py --check
python -B _infra/doc-router/tests/test_router.py
python -B -m unittest discover -s _infra/creative-studio -p "test_*.py"
```

테스트는 임시 작품을 사용합니다. FFmpeg가 없으면 영상 편집 테스트가, Windows가 아니면 DPAPI 테스트가 생략됩니다.

선택적인 브라우저 검사는 Node.js와 Playwright가 필요합니다.

```sh
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node _infra/creative-studio/ui-workspace-check.cjs
```

Python 실행 명령은 `STUDIO_PYTHON`, 별도 Node 모듈 경로는 `STUDIO_NODE_MODULES` 환경변수로 지정할 수 있습니다.

[폴더 지도](INDEX.md) · [프로젝트 규약](docs/studio/project-contract.md) · [앱 상세 안내](_infra/creative-studio/README.md)
