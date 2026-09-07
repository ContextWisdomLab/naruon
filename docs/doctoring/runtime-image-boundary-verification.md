# 독립 이미지의 실행·출처 정보 검증

상태: Proposed. [PR #1365](https://github.com/ContextualWisdomLab/naruon/pull/1365)의
로컬 수리와 검증 기록이며 보호 병합·배포 완료를 뜻하지 않는다.
검증한 구현 커밋은 `08417ad4b5b05a8d45abed67d5849228e5c21c31`이다.

## 문제와 선택

운영자가 backend 이미지를 선택했는데 통합 이미지가 만들어지면 실행 책임과
자원 요구량이 달라진다. 기존 PR은 workflow의 backend/frontend/호환 이미지에
각각 `backend-runtime`, `frontend-runtime`, `combined-runtime`을 지정한다.
다음 수리는 이 구분을 유지하면서 실제 빌드에서 드러난 결함을 해결했다.

- frontend의 shell-form CMD는 바깥 shell을 하나 더 만든다. JSON exec-form의
  `sh -c` 안에서 `exec`하도록 바꿔 runtime PORT 확장·기본값을 유지했다.
  별도 wrapper나 경고 억제용 SHELL 설정은 추가하지 않았다.
- 공통 OCI 라벨이 combined 단계에만 있어 로컬 backend target에 포함되지 않았다.
  공통 ARG/LABEL을 backend 단계로 옮겨 상속하고 통합 이미지의 제목·설명만
  재지정했다. 배포 workflow에는 원래 metadata-action 라벨이 있었으므로
  배포 라벨 전체가 누락됐다는 주장은 하지 않는다.
- UID 10001과 system 계정 기본 상한 999가 충돌했다. Kubernetes의 UID/GID를
  바꾸지 않고 useradd 호출에만 `SYS_UID_MAX=10001`을 지정했다.
  system 계정 종류, nologin, 비루트 실행과 전역 login.defs는 그대로다.
- 일반 로컬 빌드가 backend/.venv를 COPY할 수 있었다. 매번 archive로 빌드하는
  수동 절차에 의존하지 않도록 `.dockerignore`에 `**/.venv`를 추가했다.

## 실패와 후속 검증

초기 CMD 수리의 2개 검사는 기존 release-governance의 옛 명령 기대값을 놓쳤다.
해당 테스트의 실제 실패를 확인하고 기대값을 동기화했다. OCI 단계 누락과
가상환경 제외 누락도 각각 RED를 확인한 뒤 고쳤다. 최종 구현 커밋에서는
다음 명령이 38 passed, 0.28초, exit 0이었다. 두 파일의 Ruff와 diff 검사도 통과했다.

```sh
cd backend
uv run --frozen --offline python -m pytest --noconftest \
  tests/test_runtime_image_targets.py tests/test_release_governance.py -q -W error
```

동일 커밋의 git archive에 빌드 필터 검사용 `backend/.venv/context_probe.txt`만
추가하고 실제 backend 이미지를 만들었다. 앱·고객 데이터는 넣지 않았다.
변경되지 않은 잠금 의존성 설치는 BuildKit cache를 재사용했다.

- 태그: `naruon-pr1365-backend:08417ad4`, 플랫폼: Linux ARM64.
- image ID: `sha256:d2ea778c9f7f6a0c4c0dd479a3b20e049f71c94bab5d79872ab4ac6210160068`.
- 빌드 exit 0. 원시 로그의 warning/fatal/denied/timeout 검사 결과 0건.
- network-none/read-only/cap-drop ALL/no-new-privileges 임시 컨테이너에서
  `/app/.venv` 부재, UID/GID 10001, nologin을 확인했다. exit 0, `--rm` 종료.
- 원시 로그 SHA-256: `709dd7388d500aa666b7e1ac42f316d7f69fb536c17137159fdc0fba1e7bc21d`.

[실제 빌드 기록](https://github.com/ContextualWisdomLab/naruon/pull/1365#issuecomment-5564387499)은
원시 로그 위치와 실행 범위를 연결한다. 이전 ae002 빌드의 UID 경고는 당시 실패
관찰로 보존하며 후속 성공으로 지우지 않는다.

## 남은 위험과 다음 검증

기본 OCI created/revision/ref.name은 비어 있다. 라벨 존재는 release provenance
완성이 아니다. 최신 hosted 전체 검사·독립 승인·보호 병합, 실제 backend 앱 기동,
frontend SIGTERM, AMD64·통합 이미지, 배포·rollback, 인증된 제품 화면의 Visual
Inspection은 별도 근거가 필요하다. 문서의 시각 검수도 제품 검수를 대신하지 않는다.

## 배포 digest 전달 후속 수리

상태: Proposed. 이 절은 `9b137f25f426743e18fc61125575ec7949d45db8` 위의
후속 작업이며 앞선 이미지 빌드 기록의 검증 범위를 확대하지 않는다.
[이슈 #1022의 Linux 재현](https://github.com/ContextualWisdomLab/naruon/issues/1022#issuecomment-5564923743)에서
기존 manifest 생성 명령은 digest 없이 버전 tag로 두 이미지를 선택했다.
운영자가 같은 tag를 다른 이미지에 붙이면 배포 결과와 게시 기록이 달라질 수 있다.
외부 registry의 tag 변경 방지 설정은 이번 조사에서 확인하지 않았다.

선택한 계약은 publisher의 실제 `steps.build.outputs.digest`를 backend/frontend
각각의 artifact로 전달하는 것이다. 이름에 source SHA, 실행 attempt, component를
포함하며 같은 실행의 deploy job만 내려받는다. 공통 matrix output은 완료 순서에
따라 서로 덮어쓸 수 있어 쓰지 않는다. 다운로드 무결성 불일치는 오류로 처리한다.
누락된 artifact를 이전 실행에서 검색하거나 tag로 되돌리는 fallback은 없다.
실패 job만 재실행해 현재 attempt의 두 artifact가 모두 없으면 배포를 거부한다.
재시도는 보호 source와 버전을 재검증한 뒤 게시 matrix 전체를 포함해야 한다.

`scripts/render_release_manifests.sh`는 기존 manifest의 image 필드만 치환한다.
두 digest의 `sha256:` 및 소문자 64자리 hex, repository owner, VERSION, 두 원본의
단일 placeholder를 먼저 확인한다. 별도 출력 디렉터리에 두 manifest를 만들고
deploy workflow는 이 파일만 apply한다. GNU 전용 `sed -i` 대신 stdout 출력을
사용해 macOS와 Linux의 같은 명령을 검증한다. Python 제품 runtime은 추가하지
않았고 기존 pytest는 shell과 workflow 계약의 테스트 도구로만 사용한다.

검증 명령은 다음과 같다. 합성 digest는 unit test 입력일 뿐 실제 게시 증거가 아니다.

```sh
uv run --project backend --frozen --offline python -m pytest --noconftest \
  backend/tests/test_release_manifest_digests.py \
  backend/tests/test_runtime_image_targets.py \
  backend/tests/test_release_governance.py -q -W error
actionlint .github/workflows/deploy.yml .github/workflows/docker-publish.yml
shellcheck scripts/render_release_manifests.sh
```

새 계약의 초기 14개 RED는 renderer와 artifact 전달 부재를 확인했다. 구현 후
기존 검사 포함 52개가 통과했고, 실제 workflow shell의 정상·backend/frontend
누락·잘못된 값 5개를 추가한 결과 57 passed, 4.32초, exit 0이었다.
최종 commit과 이후 검증은 해당 PR 기록에 연결한다.

이 변경만으로 자동 배포가 적격해지지는 않는다. #1365 보호 통합, #1562의
concurrency 변경과 #1583 action pin의 delta 보존, 실제 artifact 업로드·다운로드,
환경 승인·release 직렬화·readiness·부분 배포 복구·실제 imageID·정상 인증 흐름은
별도 수용 기준이다. 아직 tag 발행이나 클러스터 변경을 실행하지 않았다.

### 후속 계약의 근거

GitHub. (n.d.-a). *Upload a build artifact* [Action definition].
https://github.com/actions/upload-artifact/blob/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a/action.yml

GitHub. (n.d.-b). *Download a build artifact* [Action definition].
https://github.com/actions/download-artifact/blob/3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c/action.yml

## 이미지 경계 참고 문헌

Docker, Inc. (n.d.). *JSONArgsRecommended*. Docker Docs.
https://docs.docker.com/reference/build-checks/json-args-recommended/

Docker, Inc. (n.d.). *Build variables*. Docker Docs.
https://docs.docker.com/build/building/variables/
