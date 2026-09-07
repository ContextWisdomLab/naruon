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

## 기존 배포 쌍의 조건부 복구

상태: Proposed. digest 전달 PR #1586의
`a48aa3a3e81ba58b2fa55cd758e86b9272455b1a` 위에서 개발한다.
backend가 정상 갱신된 뒤 frontend rollout이 실패하면 두 runtime의 버전이
갈라질 수 있다. image만 되돌리면 replica 수나 pod 설정은 새 값으로 남는다.
따라서 `scripts/deploy_runtime_manifests.sh`가 두 Deployment의 사전 정상 상태와
전체 spec을 먼저 확인하고, `scripts/restore_runtime_deployment.sh`가 소유권이
유지된 객체의 이전 spec을 복원하도록 실제 deploy workflow에 연결했다.

두 객체의 server dry-run이 끝나기 전에는 쓰지 않는다. 정방향 변경도 복구도
UID와 resourceVersion을 JSON Patch test로 검사한 뒤 spec만 교체한다.
적용 응답과 직후 readback이 일치해야 이 실행이 소유한 상태로 기록한다.
rollout 실패 시 두 객체의 소유권을 먼저 확인하고 frontend, backend 순으로 복구한다.
각 복구의 rollout과 최종 UID·spec readback이 성공해야 `restore_verified`를 출력한다.
복구 성공은 배포 성공이 아니므로 호출 workflow는 실패 상태를 유지한다.
독립 검토에서 backend 복구 중 이미 복구한 frontend가 다시 바뀌는 공백을 발견했다.
추가 회귀는 기존 코드에서 잘못된 `rollback_verified`를 재현했다
(1 failed, 12 deselected, 31.37초). 두 복구 뒤 이전 snapshot 대비 양쪽 UID·spec을
다시 조회하도록 고쳤다. 이 검사는 관측 시점의 확인이며 두 객체를 원자적으로
잠그거나 마지막 조회 이후의 변경까지 막지는 않는다.
수정 후 복구 검사 전체는 13 passed, 30.10초, exit 0이었다.

전체 객체 replace 대안은 기각했다. server dry-run이 추가한 last-applied annotation이
spec 복구 뒤 남는 반례가 unit test에서 실패했다. spec-only patch로 바꾸고 명시적인
label·annotation 변경은 사전 거부한다. 상태 갱신만으로 resourceVersion이 달라져도
정방향 CAS는 보수적으로 실패할 수 있다. 자동 강제 덮어쓰기보다 안전한 실패를 택했다.

제약은 명확하다. 기존의 정상·digest-pinned Deployment 두 개만 지원한다.
최초 배포, tag 기반 이전 버전, metadata migration에는 별도 승인된 절차가 필요하다.
쓰기 응답 유실은 실제 반영 여부를 확정할 수 없으므로 자동 재시도·복구하지 않는다.
다른 writer의 spec 변경이나 객체 재생성도 복구 대상이 아니다. 운영자가 현재 상태와
승인된 release 기록을 확인해야 하며 이 도구는 모든 부분 실패의 자동 복구를 약속하지 않는다.

snapshot은 같은 실행의 private 임시 디렉터리에서 `umask 077`로 만들고 종료 시 지운다.
원시 Kubernetes JSON, command stderr, kubeconfig를 artifact나 로그로 공개하지 않는다.
이는 지속 보관되는 사고 복구 원장이 아니다. 사고 후에도 필요한 승인된 이전 상태는
별도의 접근 통제·보존 정책이 있는 운영 기록에서 확보해야 한다.

검증은 실제 workflow의 Apply to AKS shell을 실행하되 kubectl을 unit double로
대체한다. server default와 annotation 추가, backend 성공 뒤 frontend rollout 실패,
다른 writer, 응답 유실, 409에 해당하는 충돌, UID 변경, 복구 rollout 실패와 최종
readback 불일치를 다룬다. 합성 Kubernetes 객체는 unit test에만 쓰며 클러스터
admission·컨트롤러·네트워크 동작이 검증됐다고 주장하지 않는다.

```sh
uv run --project backend --frozen --offline python -m pytest --noconftest \
  backend/tests/test_runtime_deployment_restore.py \
  backend/tests/test_release_manifest_digests.py \
  backend/tests/test_runtime_image_targets.py \
  backend/tests/test_release_governance.py -q -W error
shellcheck scripts/restore_runtime_deployment.sh scripts/deploy_runtime_manifests.sh
actionlint .github/workflows/deploy.yml .github/workflows/docker-publish.yml
```

위 구현의 로컬 검사에서 75 passed, 9.57초, exit 0을 확인했다.
Ruff·ShellCheck·actionlint도 exit 0이었다. commit 후 고정 SHA 검증은
PR에 따로 기록한다. 실제 클러스터 쓰기는 실행하지 않았다.

release의 동일 대상 직렬화, 오래된 release 거부, 환경 승인, DB를 포함한 readiness,
정상 인증을 거친 제품 화면의 Visual Inspection은 아직 별도로 완료해야 한다.

## 이미지 경계 참고 문헌

Kubernetes Authors. (n.d.-a). *Kubernetes API concepts*. Retrieved September 7,
2026, from https://kubernetes.io/docs/reference/using-api/api-concepts/#updates-to-existing-resources

Kubernetes Authors. (n.d.-b). *kubectl patch*. Retrieved September 7, 2026, from
https://kubernetes.io/docs/reference/kubectl/generated/kubectl_patch/

Docker, Inc. (n.d.). *JSONArgsRecommended*. Docker Docs.
https://docs.docker.com/reference/build-checks/json-args-recommended/

Docker, Inc. (n.d.). *Build variables*. Docker Docs.
https://docs.docker.com/build/building/variables/
