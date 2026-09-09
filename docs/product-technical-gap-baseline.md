# Naruon Product and Technical Gap Baseline

**Baseline version:** 1.57
**Observed on:** 2026-09-09 (Asia/Seoul; earlier dated receipts remain historical snapshots)
**Observed protected branch (current scan; row Base-SHA values remain historical):** `develop@042b0c70531b229af3acbd0421a2f23098d848b3`
**Observed product version:** `0.14.4`  
**Canonical completion issue:** [#1428](https://github.com/ContextualWisdomLab/naruon/issues/1428)

## Current visual, dependency, and owner-stack repair (2026-09-09)

### 보안 의존성 owner와 두 제품 successor

보안 의존성 owner [#1623](https://github.com/ContextualWisdomLab/naruon/pull/1623)의
현재 head는 `09cb87a25e59b0b5e737f915f77b404cafe245ab`이고 Draft다. 직전
`b97f42f16f2dfedccc1e98812c88117132ef8126`에서 새로 공개된 `js-yaml`
HIGH 두 건과 Vitest moderate 두 건을 수리했다. `js-yaml`은 기존 pnpm
workspace override로 4.3.2에 고정했고 Vitest와 coverage-v8은 4.1.11로
올렸다. ESLint 10은 최신 import·JSX accessibility·React plugin의 peer 범위가
아직 10을 허용하지 않아 기각했으며 peer suppression은 추가하지 않았다.
동시 writer의 `09cb87a25`는 별도 js-yaml 소비자 계약 검사를 보존하고 이
dependency lane의 중복 AGENTS·CLAUDE 변경만 제거했다.

`b97f42f16`과 동일한 dependency tree에서 warning 없는 frozen install,
`pnpm peers check`, audit 취약점 0건, security-floor 7건, frontend 51파일·437건,
ESLint, 16-route production build가 terminal 0이었다. 생성물 디렉터리를 제외한
source·lock·config Trivy HIGH/CRITICAL fixable-only 검사는 취약점·오구성·secret
각 0건이었다. lock 생성 중 나온 ESLint 지원 종료 경고와 ESLint 10 실험의 peer
경고는 실패한 조사 출력으로 남기고 검증 근거에서 제외했다. hosted current-head
Checks와 독립 review는 진행 중이며 이 로컬 결과로 대신하지 않는다.

NetworkGraph successor [#1593](https://github.com/ContextualWisdomLab/naruon/pull/1593)은
현재 `8d18e790ed97ef4caaf028c71e4ea6a77713da3d`, 고객 문구 successor
[#1603](https://github.com/ContextualWisdomLab/naruon/pull/1603)은
`511f7a04d989eed808ac45837ec0b6a2f80f1b3f`다. 둘 다 #1623 branch를 base로 둔
Draft이며 최신 `09cb87a25`를 force push 없이 normal merge했다. 두 branch의
package·lock tree는 owner와 동일하다. #1593에서는 #1603이 소유할 Playwright
설정·locator·screenshot 변경을 normal revert commit으로 제거해 NetworkGraph
source·bounded-options test와 해당 문서만 feature delta로 남겼다. 최신 head의
focused NetworkGraph 3파일·17건, ESLint, audit 0건, 16-route build는 통과했다.
이 restack은 runtime source를 바꾸지 않았지만 새 head의 직접 screenshot은
별도 입증 전까지 미검증이다.

### 고객 표현 Gap의 실제 수리와 Visual Inspection

#1603은 raw `source/thread`, `sender_context`, machine action뿐 아니라 서버의
영문 `action_reason`을 그대로 표시하던 공통 경로도 수리했다. bounded
`next_action`을 제품 소유 행동·판단 근거 문구의 키로 함께 쓰며, 알 수 없는
action은 중립 문구로 실패 폐쇄한다. 상세 provider/model rationale는 API 계약에
남더라도 화면에는 직접 내보내지 않는다. helper test와 signed-session browser
assertion이 이 경계를 고정한다. 동시 writer의 최신 commit은 AGENTS·CLAUDE를
문서 owner [#1549](https://github.com/ContextualWisdomLab/naruon/pull/1549)로
돌려보내 제품 PR에는 Search 구현·검증 delta만 남겼다.

최신 runtime tree에서 focused 2파일·22건, audit 취약점 0건, 16-route build,
Playwright 1건이 terminal 0이었다. 실제 한국어 `/search`를 1280×1024와
390×844에서 열고 정상 검색·발신자 관계·다음 행동·판단 근거·독립 result/detail
scroll을 직접 검사했다. 영문 rationale와 machine key는 보이지 않았고 가로
잘림·겹침도 없었다. 모바일 캡처에서 목록이 상세 위에 겹친 듯 보인 첫 판단은
두 영역의 bounding scroll container와 동작 검사를 대조해 독립 pane scroll로
수정했다. baseline 갱신으로 결함을 숨기지 않았다. loading·empty·permission,
실제품 인증·고객 DB, 8개 locale과 DB 번역 원장은 아직 미검증이다.

### 중앙 Graphify·CodeQL와 네트워크 MCP 경계

중앙 [`.github#2052`](https://github.com/ContextualWisdomLab/.github/pull/2052)는
`f6e87ff21f7427c6bc4338812954ef7a29b6487c`에서 root `opencode.jsonc` 하나와
hash-pinned Graphify MCP를 소유한다. repository-local `opencode.json` 또는
`opencode.jsonc` 복제는 만들지 않는다. 직접 webfetch/websearch 제한은 네트워크
MCP 전체 금지가 아니다. EgressWeave의 released outbound enforcement와 wardnet의
released observation/blocking contract를 exact version으로 고정하고 실패 폐쇄를
검증한 MCP는 중앙 allowlist에 추가할 수 있다. 그 전에는 미통제 직접 송신만
금지한다.

중앙 [`.github#2051`](https://github.com/ContextualWisdomLab/.github/pull/2051)의
현재 head는 `558693e0333e48012beea142f739bc634b0674a7`다. 이전 hosted Agent Review
Runtime Quality run `34330189849`는 2,998 passed·1 skipped와 100% coverage 뒤
`test_codeql_coordinator_skips_dispatch_when_exact_run_has_terminal_jobs`에서
`jq`가 숫자 값에 `.jobs`를 적용해 exit 5로 실패했다. 이를 shell echo나 provider
오류로 오인하지 않고 중앙 coordination owner에 전달했다. 후속 normal commits는
slurped exact-run 응답 fixture와 base-ref 결합을 수리했으며 새 head의 hosted 검증은
대기 중이다. Naruon #1623의 세 CodeQL compatibility job은 실제 분석 결함이 아니라
현재 head scan을 dispatch한 뒤 terminal verdict를 기다리도록 exit 1을 낸 상태다.
같은 head blind rerun이나 consumer workaround 없이 중앙 exact-run·base 결합의 새
검증 결과를 기다린다.

권위 근거: GitHub Advisory Database. (2026, August 6). *JS-YAML: Quadratic CPU
consumption in !!omap resolution (3.x and 4.x)*
([GHSA-5p4m-2wfm-xmqj](https://github.com/advisories/GHSA-5p4m-2wfm-xmqj));
nodeca. (2026, August 26). *maxTotalMergeKeys does not limit CPU use for empty
merge sources* ([GHSA-2883-xcg3-v3hh](https://github.com/nodeca/js-yaml/security/advisories/GHSA-2883-xcg3-v3hh));
GitHub Advisory Database. (2026). *Vitest: Path Traversal / Arbitrary File Read
via @vitest/mocker Redirect Mock*
([GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9)).

## Current clean-summary regression repair (2026-09-07)

### 대시보드 고객용 문구와 누락 시각검증 보완

아래 두 문구 Gap은 [#1578](https://github.com/ContextualWisdomLab/naruon/pull/1578)의
`8b336829ca2bbf978103d1032836bbff7e01174b`에서 수정 후보로 검증했다.
대기 작업은 `미완료`, 일정 비교 정보가 있으면 `원본 변경 비교 가능`, 없으면
`변경 전 원본 확인 필요`로 표시한다. 비교 정보의 존재를 최신 상태·충돌 없음·
쓰기 권한이나 완료로 해석하지 않으며 API 필드와 기존 응답 검증은 바꾸지 않았다.

직전 `ae5f39d5c2001940843a5f6e97e73f231ead5775`의 전체 484개 검사와
production build 통과에는 기존 act 경고 7건이 남는다. 현재 head는 E2E만
29줄 추가했으므로 동일한 runtime/build 입력의 기존 빌드를 사용했으며,
새 전체 검사나 빌드를 실행했다고 주장하지 않는다. 비교 정보 유무 두 상태를
desktop/tablet/mobile에서 실행한 추가 6개 검사는 6.0초에 통과했다.
정확한 문구를 viewport로 이동한 후 캡처한 6장을 작업 Agent와 조정 Agent가
각각 직접 확인했다. 모바일과 정보 없음 상태까지 해당 문구·인접 행동에
잘림·겹침은 보이지 않았다. 이전 캡처 누락은 이 범위에서 해소됐으며, 전체
언어·실제 API·번역 원장·hosted gate·보호 병합은 여전히 별도 미완료다.

### 잘못된 응답의 화면 중단과 공통 검증 수리

#1570의 `c298e4d93dfa5dcdefeac3a9312f92804b234584`는 원격에서 확인한
수리 head다. 최초 배열 항목 회귀 검사 12건을 재현한 뒤 대시보드만 고쳤을
때는 단위 검사 464건이 통과했지만 브라우저의 잘못된 응답 사례 3건은 실패했다.
함께 렌더링된 EmailList가 null 항목의 id를 읽어 화면을 중단했다. 단위 검사의
EmailList mock이 이 경로를 가렸으므로 그 통과를 실제 화면 검증으로 취급하지 않는다.

최종 수정은 받은편지함·보낸편지함·검색 결과 소비 경로에 하나의 메일 형식
검증을 적용하고, 잘못된 항목을 버려 수치를 줄이지 않고 해당 원본을 오류로
표시한다. 응답 전체가 null이어도 내부 예외 문구를 화면에 내보내지 않는다.
최종 동일 tree의 483개 검사가 통과했으나 기존 Calendar·EmailDetail act 경고
7건은 남았다. strict lint와 최종 production build는 exit 0이다. 같은 브라우저
6개 사례는 26.8초에 통과했고 pageerror가 없다는 assertion도 통과했다.
원래 실패 3건과 trace는 보존했다. 실제 API·인증·전체 schema 검증이나 경고
없는 전체 검증, 보호 병합의 근거는 아니다.
[리뷰 수리 기록](https://github.com/ContextualWisdomLab/naruon/pull/1570#discussion_r3944510233).

잘못된 응답의 desktop/tablet/mobile 캡처 3장을 작업 Agent와 조정 Agent가
각각 직접 확인했다. 검사 영역에서 오류 안내·재시도 버튼·정상 원본 카드는
유지됐고 잘림·겹침은 보이지 않았다. 모바일 줄바꿈을 잘림으로 계산하지 않는다.
다만 대기 작업의 `source-linked`, 일정 원본의 `충돌 토큰 있음`은 내부 구현을
노출하는 미해결 문구다. 후속 조치는 사용자 행동 중심 문구와 접근성 이름을
함께 고치고 8개 언어의 versioned DB 번역 원장 계약을 확인하는 것이다.
번역 파일 복제나 프레임워크 추가로 이 수리의 범위를 넓히지 않는다.

### AGENTS 렌더 확인과 stacked gate의 실제 적용 범위

#1566의 `d33f1d7da8a74b4ffb8eec25ef2580bfde1cc8ff`는 공개 GitHub exact-SHA
렌더에서 변경 보존 문단·스킬 지침·검증 절의 desktop/mobile 캡처 6장을
직접 확인했다. 1280×1024와 390×844에서 해당 문단의 잘림·겹침은 없었고
focused 캡처의 scrollWidth는 viewport와 같았다. 관찰한 pageerror는 0건이다.
이 경로는 설치된 Playwright의 새 익명 context를 사용하며 잠긴 Mac 세션이나
저장된 인증을 사용하지 않는다. 초기 상단 캡처와 networkidle timeout은 실패
관찰로 남기고, 실제 목표 문단을 viewport에서 확인한 후속 캡처만 근거로 쓴다.
전체 1,071줄·모든 언어·브라우저 검증으로 확대하지 않는다.
[Visual Inspection 기록](https://github.com/ContextualWisdomLab/naruon/pull/1566#issuecomment-5560206265).

같은 head의 GitHub Checks API는 check run 0개, required-check CLI는 없음으로
응답했다. 리뷰 thread 1개는 resolved/outdated이고 pagination도 끝까지 확인했다.
과거 `27211368`의 CHANGES_REQUESTED가 남아 있으며, 현재 CodeRabbit·Devin
SUCCESS status를 현재 head의 APPROVED review로 바꾸어 해석하지 않는다.

Naruon의 실제 ruleset API에서 상속 규칙 `18156473`의 ref 조건은
`~DEFAULT_BRANCH`뿐이었다. 중앙 workflow 7개와 승인 1개·삭제 금지·non-fast-forward
금지가 한 규칙에 섞여 있다. 로컬 `15586698`, `17214772`도 default branch에만
적용된다. 특히 `17214772`는 승인 1개와 마지막 push 승인도 요구한다.
#1566의 base는 foundation branch이므로 필수 검사 없음은 보호 검증 완료가
아닌 stacked 적용 공백이다. 현행 owner에서 workflow-only 적용 범위와 권한을
결정해야 하며 이 문서 변경은 규칙을 변경하지 않는다. 혼합 규칙을 모든 ref로
넓히거나 승인 수를 낮추는 우회는 하지 않는다. 보호 병합은 계속 미완료다.

### Calendar 브라우저 검사와 고객 표현 Gap

보존 중인 #1569 로컬 통합 head `95dd9e659009061bd0d7fcc9309947623d8b6840`의
기존 Calendar Playwright 2개 사례를 desktop/tablet/mobile 프로젝트에서
실행했다. `--workers=1`로 6개 모두 24.9초에 통과했고 프로세스 exit 0을
확인했다. 서버는 격리된 localhost:18769이며 종료 뒤 listener가 없었다.
API는 기존 mock을 사용하므로 실제 CalDAV 쓰기나 서버의 인증 검증 근거가
아니다. 첫 사례는 viewport를 1280×1024와 390×844로 직접 바꾸므로
프로젝트 이름만으로 세 가지 고유 화면 폭을 검증했다고 계산하지 않는다.
읽기 전용 사례는 각 프로젝트 viewport를 그대로 사용한다.

이 실행에서 생성된 정상 desktop/mobile, 읽기 전용 tablet/mobile 캡처
4장을 직접 검사했다. 원본 선택, 읽기 전용 표시와 비활성 버튼은 보였다.
정상 사례의 가로 넘침·모바일 스크롤 assertion도 통과했다. 그러나 화면에
`intent`, `ETag`, `If-Match`가 남아 고객에게 내부 구현을 노출한다.
후속 조치는 이 용어를 사용자 행동·충돌 확인 결과로 바꾸고 접근성 이름과
E2E 기대값을 함께 검증하는 것이다. 전체 8개 언어, 모든 UI 상태, p95 목표,
실제 provider 연동이나 AGENTS 최신 렌더 검사를 완료했다고 쓰지 않는다.
원본 캡처는 작업 증거 디렉터리 `naruon-1569-calendar-e2e-results`에 보존했다.
외부 삭제 의도 확인 전이므로 이 통합 head의 원격 push는 계속 보류한다.

### 중앙 metadata 검증 범위 수정

[중앙 #1971](https://github.com/ContextualWisdomLab/.github/pull/1971)의
`8a3c2bb95ee6065c8a15515de3f909d5c476c885`는 API 확인 당시 Draft/open이며
기존 metadata workflow와 그 테스트, 두 파일을 변경한다. 조정 Agent는
시간당 metadata 검증의 전체 pytest 호출 하나를 없애고 owner 11파일·60개
검사는 유지했다고 보고했다. 이 lane의 직접 확인 범위는 PR head·상태·파일
목록이다. 로컬 수치를 조직 전체 비용 절감률로 바꾸지 않으며, hosted 결과와
보호 병합 및 별도 concurrency #1899 검증은 미완료로 유지한다.

### Central scan 실패의 소유 경계

중앙 #1879의 [Strix 실행 34031339200](https://github.com/ContextualWisdomLab/.github/actions/runs/34031339200)은
API 재확인 결과 `23eb2833794f829985e3cef81e8da77fe10b91e1`에서
completed/failure다. job `101486795855`는 2026-09-06 13:13:17Z에 시작해
14:54:04Z에 실패로 종료했다. 조정 Agent가 전달한 artifact `9991542931`
분석은 `orchestrator/free` 요청 5,377초 뒤 HTTP 500을 보고한다. 이 상세
분석은 이 문서 작성 lane에서 원시 로그를 다시 읽은 결과와 구분한다.
900초 제한에 걸렸다고 단정하지 않으며 CO의 근본 원인도 아직 미확정이다.
Naruon에서 provider 우회나 scanner 복제를 추가하지 않고 canonical owner의
RCA와 새 exact-head 실행 결과를 기다리는 동안 독립 제품 검증을 계속한다.

### UI 통합 검증과 아직 남은 배포 근거

후속 관찰: #1488의 `22b4c5de4cd3496ef16465cb5ce881fa6abd6add`는
아래 검사 head의 자식이지만 실제로 10파일에서 통합 delta를 제거했다.
commit 메시지의 empty 표현은 tree와 일치하지 않는다. 직전 Jules 댓글은
검증 기록을 확인했다는 내용이며 삭제 이유는 설명하지 않는다. 따라서 아래
결과를 최신 head의 성공으로 승계하지 않는다. 외부 작성 의도를 확인할 때까지
역수정 push를 보류하고, 유효 delta를 보존한 #1569 로컬 통합 head
`95dd9e659009061bd0d7fcc9309947623d8b6840`에서 검증을 이어간다.

#1245의 `38c375e96693b69f5ce14c2a8bd50379f77e79e5`는 의존성 #1244를
정상 병합했고, #1488의 `4d19c69d6d122033f7237acef81a1fc468df8dbf`는
그 변경과 Calendar 수리를 함께 승계했다. 도중에 추가된 외부 empty commit
`a2ecfc37b6585d9e32fc20c0616dc88efc6683da`도 버리지 않고 정상 병합했다.
스택은 #1244 → #1245 → #1488이며 세 PR은 여전히 열려 있다.

#1488의 tracked tree는 검사한 `a9ee00d776750e6bf750c751359d06514e784599`와
동일하다. 전체 55파일·449테스트, 경고를 허용하지 않는 ESLint, 타입 검사는
각각 exit 0이었다. 테스트 로그에서 기존 Calendar·EmailDetail의 act 경고가
사라졌다. 확장 manifest 탐지를 적용한 tracked-head archive의
MEDIUM/HIGH/CRITICAL fixable 취약점·secret·misconfiguration 검사도 exit 0,
발견 0건이다. 결과 JSON SHA-256은
`03832494af9b6ed5282f01a92d60c5ddcf60e495b64460cda5c88c1ceea6a114`다.
[통합 검증 기록](https://github.com/ContextualWisdomLab/naruon/pull/1488#issuecomment-5560116879).

이 기록은 로컬 tree 동등성과 검사 결과만 입증한다. 빌드 로그에는 라우트
출력이 있지만 원래 프로세스 종료 코드를 확보하지 못했으므로 빌드 성공의
독립 근거로 쓰지 않는다. 새 head의 hosted Checks, merge-ref 검사, 100%
커버리지, 보호 병합과 배포는 별도 검증이 필요하다. 최신 AGENTS 화면 검사도
Mac 잠금 때문에 미완료다. 아래 9월 6일 수리 기록은 통합 전 상태를 보존한다.

### Calendar 경고 수리와 운영 지침 전파

기존 #1488의 `f6eb0460efb0d7332762fe3fbdb8aa1702f35506`은 첫 렌더의
비동기 원본 조회가 끝날 때까지 `await act`로 기다린다. 원래 진단 출력을
유지하는 검사만 추가했을 때 1개 실패·9개 통과로 재현됐고, 수리 후 관련
13개 테스트와 strict lint가 Calendar 경고 없이 통과했다. 전체 실행의
53파일·440테스트는 통과했지만 이 브랜치에 아직 상속되지 않은 EmailDetail
경고 4개는 남았다. 두 UI 소유자의 수리를 통합한 뒤 다시 검증해야 한다.
[Calendar 수리 근거](https://github.com/ContextualWisdomLab/naruon/pull/1488#issuecomment-5560051738).

AGENTS #1566의 `a813e6e750e0fe48e350864a01570a118b34e338`에는 실제
manifest 탐지 목록 확인과 경고를 허용하지 않는 검증 절차를 중복 없이
추가했다. 인접 문서·소스 계약 56개는 통과했지만 이 수치가 새 지침의 실제
렌더나 사실 검증을 대신하지 않는다. 최신 Visual Inspection과 보호 병합은
미완료로 유지한다.
[운영 지침 보강 근거](https://github.com/ContextualWisdomLab/naruon/pull/1566#issuecomment-5560051818).

### EmailDetail 테스트 경고 수리와 남은 검증

기존 UI 소유자 #1245의 `885ee0c266c74cda5a19635cbc47ab6d33b488cf`에서
입력 이벤트 4개를 `await act`로 감쌌다. 원래 출력을 유지하는 회귀 검사만
추가했을 때 4개 실패·22개 통과였고, 수리 뒤 관련 테스트 30개가 해당 경고
없이 통과했다. 같은 컴포넌트의 문맥별 선택 콜백 의존성 누락도 strict lint
실패로 재현한 뒤 의존성 한 줄을 추가했다. AGENTS와 기존 doctoring 문서에
재발 방지 절차와 React 공식 근거를 남겼다.
[UI 소유자 수리 근거](https://github.com/ContextualWisdomLab/naruon/pull/1245#issuecomment-5560009693).

전체 strict lint, 타입 검사, 프로덕션 빌드는 exit 0이다. 전체 커버리지
실행은 52파일·442테스트가 통과했지만 CalendarLayout 경고 3개가 남았다.
lines 86.76%, statements 84.06%, functions 85.67%, branches 75.18%로
100% 목표에는 못 미친다. 이 수리는 EmailDetail 경고의 해결이며 Calendar
경고, 전체 제품 검증, 최신 Visual Inspection 또는 보호 병합 완료가 아니다.
의존성 PR에 UI 변경을 섞지 않았고 기존 #1245의 유효 변경은 보존했다.

### Security prerequisite adoption and central coverage owner

Governance #1531 at `bd0135de778a01a51deae536084447ce2481280c` normally
merges its `f2e2ac0e` predecessor with dependency #1244's `156a816c`. Its base
now names #1244's existing branch, making the prerequisite explicit instead of
merging a vulnerable foundation first. The four dependency files are identical
to their owner versions. Full governance harness, 36 source contracts,
ShellCheck and whitespace checks passed. Its tracked archive passed expanded
MEDIUM/HIGH/CRITICAL fixable vulnerability/secret/misconfiguration scans with
11 language manifests and zero findings.
[Governance adoption receipt](https://github.com/ContextualWisdomLab/naruon/pull/1531#issuecomment-5559910149).

CI #1562 at `cdef60348a7da793a24828ec3d2a1bd6cc680f02` normally merges that
parent into `0ec1cf92`; only the scanner hash-lock changes because the js-yaml
repair was already present. Its full harness and 40 source contracts passed.
The PostgreSQL runner exited 0 with 1,877 passed and two live-endpoint skips
in 137.75s; task containers, volumes and networks were independently absent.
Its tracked archive also passed the expanded Medium-or-higher scan with all
11 language manifests present.
[CI adoption receipt](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5559932952).

SMTP #1417 at `489bcbeaf131da123551a187228862b0e47ad549` normally merges
that CI parent into `ec3e361d` while preserving SMTP behavior. Its own full
harness, 40 source contracts and expanded Medium-or-higher tracked-archive
scan passed; all 11 language manifests were present with zero findings. The
PostgreSQL runner exited 0 with 1,892 passed and two live-endpoint skips in
125.69s, followed by independently verified task-resource cleanup.
[SMTP adoption receipt](https://github.com/ContextualWisdomLab/naruon/pull/1417#issuecomment-5559955413).
These head-archive checks are not claims about new merge refs or hosted checks.

The canonical scanner-discovery repair is now
[central #1969](https://github.com/ContextualWisdomLab/.github/pull/1969),
head `61033f205ce058ac3692260dc7a52e4daf05b64b` against `main@dd0b96fe`.
It changes the existing PR/scheduled scanners and their contract tests; it is
Draft and not protected-main evidence. Naruon must not copy those workflows
or treat a local expanded scan as proof the central gate has adopted the fix.
Existing UI-test warnings, hosted reviews/checks, immutable release and current
Visual Inspection remain independent unmet requirements.

### Combined dependency prerequisite, not protected delivery

Existing #1244 now has head `156a816c3e799bc8cc2cf87e5e1a2ffb8cc1c78f`, a
normal merge of its `50351e8c` predecessor and #1571's `3f568412`. Both original
deltas are preserved byte-for-byte: the scanner hash-lock matches #1244 and
the three frontend files match #1571. Both PRs remain open; no valid delta was
discarded or history rewritten. This provides one combined prerequisite before
adopting the repairs into foundation/consumer branches.

A tracked archive of `156a816c` passed the expanded Trivy 0.74.0 scan with
MEDIUM/HIGH/CRITICAL fixable vulnerability, secret and misconfiguration checks.
The actual results include 102 scanner-lock packages with `aiohttp` 3.14.3 and
580 frontend-lock packages with `js-yaml` 4.3.1. The JSON SHA-256 is
`7b8eecdc96f745ebce86087f599ed3846ce363e92bc2af45b0e664d951b9ed17`.
This matches the inspected central gate's severity threshold, but is still
local evidence rather than its hosted SARIF, authorization or review result.
The earlier worktree scan is not used as immutable-archive evidence.

Frozen pnpm installation, lint and the two dependency-lock tests exited 0.
The hash-required uv dry run resolved the scanner lock without installing it;
it is not proof that every published distribution hash has been downloaded and
verified. An initial `pnpm test --` invocation unintentionally ran all 52 files
and 439 tests. Although assertions passed, CalendarLayout and EmailDetail
emitted React `act(...)` diagnostics, so that run is not warning-free acceptance.
Do not hide the diagnostics or substitute the two focused tests for full-suite
cleanliness. A separate frozen-install reproduction on parent `50351e8c`
ran the original Calendar and EmailDetail tests: 33 passed, exit 0, with the
same CalendarLayout/EmailDetail diagnostics (three/four occurrences). This
establishes that the warnings predate this integration, not their full root
cause. Route the existing test defects to their owner without expanding the
dependency diff or suppressing output. #1244 remains Draft while warning
repair and hosted gates are incomplete.
[Combined prerequisite receipt](https://github.com/ContextualWisdomLab/naruon/pull/1244#issuecomment-5559874389).

### Governance and earlier scan evidence

PRD requirement: clean, authenticated review evidence must allow the next
eligible step without allowing a real warning or a forged publisher to pass.
Review #3944130242 reproduced a false blocker introduced by output-first
matching at `b6d6c286`: `No warnings found` and `No actionable comments were
generated` matched the warning patterns. The first whole-string regex repair
still failed. Owner #1531 at `f2e2ac0e9fd84907d49b9646af894e55077cb383`
instead splits output into lines and removes only complete known clean lines
before applying the existing blocker policy. Eleven cases cover clean output,
explicit failure, neutral without skip evidence, forged publishers, mixed
warning lines and same-line qualifications. Unknown wording is not generally
interpreted as negation. The full governance harness exited 0; 36 source
contracts, ShellCheck and whitespace checks passed. Independent source reviews
are separate from hosted approval.
[Owner RED/fix/GREEN receipt](https://github.com/ContextualWisdomLab/naruon/pull/1531#discussion_r3944176985).

CI #1562 at `0ec1cf92e161b9f99d04487435a3dd7f0ce3c15c` normally merges the
complete repair into `938d4b12`, retaining consumer changes. Its gate and
harness blobs match the owner exactly. The full governance harness and 40
source contracts passed; the real PostgreSQL runner exited 0 with 1,877 passed
and two `LIVE_BASE_URL`-dependent skips in 89.41s. Task-labelled containers,
volumes and networks were independently absent after cleanup.
[CI current-head receipt](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5559771293).
SMTP #1417 at `ec3e361d13bff6af09db75e5640c426ede48ebbc` normally merges that
CI parent into `5dea5092`, preserving SMTP throttling. Its own full harness,
40 source contracts, ShellCheck and whitespace checks passed. Its PostgreSQL
runner exited 0 with 1,892 passed and the same two live-API skips in 138.59s;
task-labelled containers, volumes and networks were independently absent.
[SMTP current-head receipt](https://github.com/ContextualWisdomLab/naruon/pull/1417#issuecomment-5559790933).
Both consumer heads were pushed normally. New merge-ref security evidence
below supersedes the earlier bounded zero-finding receipts for these heads.

The default-branch Dependabot API currently reports six open alerts. The
inspected CI head already pins `js-yaml` 4.3.1, `cryptography` 50.0.0 and the
scanner lock's `pyasn1` 0.6.4, but `requirements-strix-ci-hashes.txt` still pins
`aiohttp` 3.14.1. Alerts #88–90 include GHSA-cq5v-8q36-5273 with first patched
version 3.14.3. Central `.github` at protected commit
`dd0b96feded94f66ecf59b25a5a9b58cfc8b4f69` already pins `aiohttp` 3.14.3;
Naruon's existing #1244 at `50351e8cacc65b4124ba2145e00d41aeceef0775`
contains the corresponding one-file hash-lock repair and remains unmerged.
Validate and integrate that existing delta rather than opening a competing
repair or treating the central dependency as still unpatched. Existing
#1571 owns the `js-yaml` change. Neither an open repair nor a local pin proves
the protected default branch is patched.

### Manifest discovery failure reproduced on current merge refs

Trivy 0.74.0 scanned tracked archives of CI merge
`9d7b80413d5b6120302a3f7f677887b271c52c74` and SMTP merge
`1c4c369ebcf6ee752ab10be8c92a96b14634e6c2`. The initial DB-update invocation
used an unsupported top-level flag and failed; the help-confirmed
`trivy image --download-db-only` then exited 0. The default HIGH/CRITICAL
fixable vulnerability/misconfiguration scans and separate all-severity secret
scans exited 0, but their language results covered only four manifests and
omitted `requirements-strix-ci-hashes.txt`.

Adding `--file-patterns 'pip:requirements-.*\.txt'` on the same archives
preserved default discovery and added the missing requirements variants.
Both expanded scans exited 1 with `CVE-2026-69244`, HIGH, in the scanner
hash-lock's `aiohttp` 3.14.1, fixed in 3.14.3. That target contains 102 parsed
packages. The same DB already detected the advisory once the manifest was
included; DB freshness alone cannot explain or repair this missed finding.
[CI failed security receipt](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5559826656)
and [SMTP failed security receipt](https://github.com/ContextualWisdomLab/naruon/pull/1417#issuecomment-5559826830)
retain exact heads, merge refs and expanded JSON digests. Head/base/merge
readback was unchanged after scanning. Local test success does not override
these security failures.

TRD action: the canonical Security Scan owner must make requirements-variant
discovery explicit and assert that expected manifests appear in scan results;
a process exit code alone is insufficient coverage evidence. Keep the
existing #1244 dependency repair distinct from this scanner configuration gap.
Acceptance requires the manifest to remain present after repair, the vulnerable
version to fail, the patched version to pass, and new-head hosted evidence.
Do not remove the target, suppress the advisory or copy a central workflow.

A separate expanded scan of existing #1244 at `50351e8c` retained all 102
scanner-lock packages and confirmed `aiohttp` 3.14.3 with no HIGH/CRITICAL
fixable finding in that manifest. The whole scan still exited 1 because its
frontend lock contains `js-yaml` 4.3.0, GHSA-5p4m-2wfm-xmqj. This establishes
the aiohttp repair's bounded effect, not an overall security pass. Integrate
the existing #1571 and #1244 deltas in a valid prerequisite order; do not merge
a vulnerable foundation first or discard either repair to reduce PR count.

Reference: Aqua Security. (n.d.). *Selecting files*. Trivy documentation.
https://trivy.dev/docs/dev/guide/configuration/skipping/

Visual Inspection of the newest AGENTS and baseline changes remains incomplete
while the Mac is locked. Keep this gap explicit and inspect after manual
unlock. Hosted checks, protected merges, immutable release and customer runtime
outcomes remain unproven; the authority and release-ordering gaps below remain
open. No PR was closed or history rewritten to obtain this state.

## Earlier publisher repair and verified consumer stack (2026-09-06)

PRD requirement: another check publisher must not impersonate robot review,
and a successful check label must not hide its blocking warning. Independent
review identified both pre-existing metadata risks at `fac3437c`; six focused
counterexamples reproduced an incorrect success. The common gate now verifies
App/Bot provenance before selecting evidence and inspects output before
accepting success/skipped conclusions. Owner #1531 at
`b6d6c286040f16d3d6ef93959eff53abe0eb6d3e` retains the prior stale-notice repair;
its ten publisher/output cases, full fake-GitHub harness and 36 source tests
pass. [Owner repair and bounded visual receipt](https://github.com/ContextualWisdomLab/naruon/pull/1531#issuecomment-5559591367).

The complete owner delta was ordinarily merged into CI #1562 at
`938d4b1203bf0573cf94466e9a21935c870dd684`, then SMTP #1417 at
`5dea5092dfb40e86159570bbeda9148b0148e890`. Each inherited exactly three files
(85 added, 13 removed lines), with no conflicts or discarded consumer changes.
Each head has its own passing full governance harness and 40 source tests.
CI full PostgreSQL: 1,877 passed in 133.85s; SMTP: 1,892 passed in 209.96s.
Each skipped two live-API tests requiring `LIVE_BASE_URL`; those live paths
remain unverified. Both runners exited 0 and their task-labelled containers,
volumes and networks were independently confirmed absent.
[CI exact-head receipt](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5559638216)
and [SMTP exact-head receipt](https://github.com/ContextualWisdomLab/naruon/pull/1417#issuecomment-5559638349)
retain redacted JUnit digests and separate merge-ref security evidence.

Those receipts also bind fresh scans to merge refs `11a371d8` and `f0c602de`:
Trivy HIGH/CRITICAL fixable vulnerability/misconfiguration scans including
supported development dependencies, plus separate all-severity secret scans,
all exited 0 with no reported findings. This bounded local evidence does not
certify all vulnerabilities, hosted checks, protected merge or deployed behavior.
The observed #1531 Ready event at 13:42:07 UTC names the shared account, not an
identifiable agent; its head is unchanged. Do not infer a specific writer,
repeat the transition, or treat review admission as merge authorization.

AGENTS #1566 at `29a56150cabe821927b2a9ff5169e4e593b52e1e` records publisher
authentication and durable test-output/exit/cleanup guidance; its 40 document
contracts passed with `-W error`. [Guidance receipt](https://github.com/ContextualWisdomLab/naruon/pull/1566#issuecomment-5559629212).
The Mac was locked at the new visual-inspection attempt. Neither that new
AGENTS text nor this baseline revision has current visual evidence; inspect
both after unlock rather than reusing older screenshots. Foundation CodeQL's
authorized recovery and exact-job callback remain incomplete; preserve the
[authority diagnosis](https://github.com/ContextualWisdomLab/naruon/pull/1564#issuecomment-5559525534)
and repair the existing central owner without expanding dispatch principals.

## Earlier governance repair and stack handoff (2026-09-06)

PRD requirement: a completed review must not leave an otherwise eligible
change waiting indefinitely because a bot's issue comment has not refreshed.
At #1531 predecessor `e058f3ead35f9a19d3c3b20c6ab5fc04d2e2cbb2`, the new
success-check regression failed and the fake publisher emitted `in_progress`.
[Finding 3939597997 and repair receipt](https://github.com/ContextualWisdomLab/naruon/pull/1531#discussion_r3943940937)
connect the source and reproduction to owner
`fac3437c03d928e45632763530a4f130dfe505fd`. Its gate now treats the stale
notice as a wait only without CodeRabbit check/status evidence or qualifying
OpenCode approval. Failed/pending authoritative checks and separate substantive
findings remain effective; this does not authorize merging a failed PR.

The complete owner delta was ordinarily merged into CI #1562 at
`0648eace4186c9ba813102df4f26571e20cea3c0` and then SMTP #1417 at
`cc2c4cbc3fe134787b724b79cde98fe3e7c1b6e0`, without conflicts, force rewrites,
or discarded consumer changes. Each merge adds only the three-file governance
repair (34 added, 10 removed lines); inherited gate and harness blobs match
their parent. Each consumer's focused source tests pass (40, zero skips).
Each committed-head full fake-GitHub governance harness also passed with
exit 0, as did ShellCheck and the whitespace check.
The first CI focused command incorrectly named a nonexistent test file and
exited 4 with no tests; the corrected command uses the actual two collected
test files. That invocation error is not a source regression or a passing run.

TRD acceptance remains separate: each new head needs its own completed
governance harness, hosted checks and review evidence; older real-PostgreSQL
and merge-ref security receipts remain historical, not new-head certification.
No protected merge, immutable release or live customer outcome is claimed.
The release-ordering risks below remain open despite this metadata repair.
The [baseline 1.40 desktop visual receipt](https://github.com/ContextualWisdomLab/naruon/pull/1557#issuecomment-5559337483)
belongs to `75d1126062866029ba71d53296166d38a0ed4390` and covers its visible
heading and handoff section only. Inspect this revision in the actual browser
before marking its newly changed text visually verified.

### Full-suite output failure and retry acceptance

The first real-PostgreSQL runs at these unchanged consumer heads did not
complete: each redacted JUnit report contains 649 tests, one internal error,
zero assertion failures and two skips. The internal error is pytest terminal
flushing with `BrokenPipeError: [Errno 32] Broken pipe`; neither a complete
suite nor a successful runner exit was established. The
[CI failure receipt](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5559385503)
and [SMTP failure receipt](https://github.com/ContextualWisdomLab/naruon/pull/1417#issuecomment-5559385733)
retain the exact heads and JUnit digests. Their task containers and volumes
were absent; only the inspected, empty, project-labelled networks were removed.

Same-head retries redirect runner output directly to durable files and retain
the final exit status separately. This changes observation plumbing, not the
application, test denominator or timeout policy. The initiating cause of the
original output-pipe closure remains unconfirmed. A retry is acceptable only
after the full test result, explicit skip reasons, runner exit, redacted JUnit
digest and absence of that run's containers, volumes and network are verified.
Partial progress or a missing observation handle does not authorize restarting
a live run. This local evidence cannot replace required hosted checks, review,
merge-ref security evidence or protected-branch delivery.

The [CI same-head retry receipt](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5559463002)
now establishes 1,877 passed tests, two live-API skips for missing
`LIVE_BASE_URL`, runner exit 0 and no remaining task-labelled Docker resources.
The redacted JUnit records 1,879 tests with zero errors or failures; its SHA-256
is `a9c20970c9ff1f4b37524fe350b1d28430b165f9dea49cf77a69e0bf92943b3b`.
The local head and worktree remained unchanged. The separate
[SMTP same-head retry receipt](https://github.com/ContextualWisdomLab/naruon/pull/1417#issuecomment-5559469671)
establishes 1,892 passed tests, the same two live-API skips, runner exit 0 and
no remaining task-labelled Docker resources, with unchanged local/remote head
and a clean worktree. Its redacted JUnit contains 1,894 tests, zero errors or
failures, and SHA-256
`5cdcf50c05928dab29ca173a46de5856b13ed8c182762857953cee37afbf4672`.

## Release ordering and foundation verification gaps (2026-09-06)

PRD requirement: an operator must receive one coherent, authorized release;
a slower old run must not replace the selected version or leave frontend and
backend from different releases. At proposed CI head
`1f538b188bf0c6a8193fbea005d0c537a01095ec`, Docker publication groups use the
tag ref, while every tag writes the shared `latest` image alias
(`.github/workflows/docker-publish.yml:13,304-307`). The called
`.github/workflows/deploy.yml:41-68` selects version tags rather than published
digests and applies backend/frontend separately to `naruon-dev`, without a
deployment-target lock. These are source-backed risks, not evidence that a
production overwrite or partial deployment occurred.

TRD action: separate trusted live-head admission and cancellable PR validation
from release/deployment serialization at the shared target. Preserve the
workflow-repository-PR validation identity and independent matrix components.
Adding `run_id` to every group was rejected: it prevents the required older-run
cancellation and does not protect shared release targets. A per-tag lock was
also rejected because different tags still mutate the same target. The
canonical `.github` owner must provide reusable admission/release contracts;
Naruon consumes immutable owner contracts through thin callers rather than
copying a local scheduler. No new release implementation is claimed here.

GitHub's native `queue: max` can retain up to 100 pending entries when
`cancel-in-progress` is false; overflow is cancelled. It can be part of the
serialization mechanism, but cannot alone prove durable release intent or
unlimited non-cancellation. Required evidence covers a delayed older release,
a duplicate rerun, competing component completion, partial apply recovery,
source/digest readback, pending intent recovery and explicit overflow handling.
An approved rollback must remain distinguishable from an accidental downgrade.
[Review finding and alternatives](https://github.com/ContextualWisdomLab/naruon/pull/1562#discussion_r3943841262)
and [GA acceptance follow-up](https://github.com/ContextualWisdomLab/naruon/issues/1428#issuecomment-5559018324)
retain the owner handoff. No image, cluster or protection change was made.

Foundation #1564 at `615be4514add6a21eef743f591a65a5f8fef4dee` has a separate
hosted failure. Central dispatch run `33968978595`, source
`f250638827f8252b0d9e5cb2601f4d333f96162f`, failed job `101314001568` at
`codeql-scan-dispatch.yml:149`: `A sequence was not expected`. An array was
assigned directly to an environment value; the scan job was skipped. Existing
central repair [#1926](https://github.com/ContextualWisdomLab/.github/pull/1926)
merged as `3f88e13af9dcde4b9da6958c02a78ce3b5c85800` serializes it with `toJSON`.
The inspected current-head statuses still lack a terminal `codeql-dispatch/*`
receipt. A fresh authorized execution on repaired source and its exact-job
callback remain required; unrelated CodeQL success or rerunning historical
source does not establish repair. [Exact failure and lineage inspection](https://github.com/ContextualWisdomLab/naruon/pull/1564#issuecomment-5559002855).

Historical visual limitation: the Mac was locked when baseline 1.39 was
first committed. After unlock, its `a508e543` desktop heading and visible
release-ordering section were inspected; [the exact-head receipt](https://github.com/ContextualWisdomLab/naruon/pull/1557#issuecomment-5559170163)
records the bounded result. Neither that screenshot nor prior AGENTS captures
certify a later revision, the entire document, or product UI.

Reference: GitHub. (n.d.). *Control the concurrency of workflows and jobs*.
Retrieved September 6, 2026, from
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

**CI launch ownership repair (2026-09-06):** Existing CI owner
[#1562](https://github.com/ContextualWisdomLab/naruon/pull/1562) advances normally
to `1f538b188bf0c6a8193fbea005d0c537a01095ec`, tree
`c5756d111a71b5eb7d4a1b038a5c29de646f7d03`. A real SIGTERM between background
launch and PID registration left the original command alive after cleanup.
A task-owned DEBUG barrier reproduced RED without changing the tested runner
or reading operator files. The owner now records cancellation during that
short registration interval and handles it after ownership is known.
The cancellation status, group reaping, redaction and cleanup bound remain.

On the committed owner, 19 focused cases pass, followed by **1876 passed /
2 explicit live-only skips / 91.86 s** on a fresh and repeatedly migrated real
PostgreSQL database, with complete scoped cleanup and exit0. The environment
was synchronized to both Actions hash files (113 compatible packages), rather
than substituting the differing local uv lock. JUnit SHA-256:
`6d58e7387c41577302376ebb158ed4ff561cfb8b864d22b9fad110eba9fcdd5e`.
The event observer recorded this run's container stop and destruction; those
events cannot establish what killed an earlier run.

Shared-send owner [#1417](https://github.com/ContextualWisdomLab/naruon/pull/1417)
normally inherits the complete child at
`b7011d2cc6a96c9e153a2771a7cac39749fa2969`, tree
`2d3518f6fe7e3d1cc9f90855ebb35bfc290cd9ac`, retaining its SMTP and migration
history. Its own committed-head full lifecycle passes **1891 tests /
2 explicit live-only skips / 141.87 s**, including fresh/repeated migrations
and completed scoped cleanup, exit0. JUnit SHA-256:
`6b878f5303d34ebef472b148448ceaaa7d8c7d9e249c2f4ee601b5676a074673`.
Both generated projects have no remaining containers, networks or volumes.

Current merge refs `0977ebfec612d5fb6aa98caa9af22ea18e0485d9` (#1562)
and `13488ac848b5573386f42565eec9239ee18f8481` (#1417) have the named
base/head parents and identical source trees. Refreshed local Trivy scans have
zero HIGH/CRITICAL fixable vulnerability/misconfiguration findings including
development dependencies, and zero separate secret findings. Security report
SHA-256 values are `1deff476ca58270ace7085a7b31f575550b35590c0b8f0918d88c7d6fb239bc4`
and `0b48cbc2195c8229d0b4a3b8e9c1283fe712a7f2e42b045b9bc013a3966f9f69`;
the respective secret-report digests remain in the PR receipts.
Hosted checks remain separate gates; no hosted approval or advisory closure
is inferred from these local scans.
Both PRs remain Draft on their unmerged prerequisites. The earlier Docker
exit137 incident remains unproven and open; this independently reproduced
registration gap is not its established cause.
[Decision, exact regression and APA reference](https://github.com/ContextualWisdomLab/naruon/blob/1f538b188bf0c6a8193fbea005d0c537a01095ec/docs/doctoring/application_ci_postgres.md#cancellation-before-process-ownership-is-recorded-2026-09-06).

**Historical SMTP cancellation repair (2026-09-06; heads superseded above):** Existing shared-send owner
[#1417](https://github.com/ContextualWisdomLab/naruon/pull/1417) advances normally
to `dc8b53d38ddf80b726b5dc6cff1d21f2c25d293e`, tree
`b66b0bff2cab33c9ff26301dad6005778c804696`, retaining the complete SMTP child
`56025b17d752b8fbe2c759d9420876a73e26d51c`, its `1666` parent and CI
prerequisite #1562 at `b2e98a52588db72e501c0843b33816e2e5bc698b`.
Its base stays the CI owner branch.

PRD/operability gap: cancelling a send during connection left a real socket
open until later reclamation. The direct sender and registered Connector both
reproduced this failure. TRD action: the common connection helper now closes
the socket for cancellation and re-raises that cancellation; no per-consumer
workaround, success result, destination-policy change, dependency, or model
timeout was added. Two real-socket behavioral cases were RED before the
one-line fix, then the three affected suites passed 55 tests with warnings
treated as errors. A read-only Agent review found no actionable issue within
this delta; it is not a qualifying GitHub approval.

The full SMTP candidate passed 1889 tests with two explicit live-only skips,
but its immutable `5602` rerun failed one CI signal-probe startup precondition
(1888 passed, two skipped). Preserve failed JUnit SHA-256
`27c1ac50cb7073bdb5299170618e6ee204ad437199658285f68cb44621e593bb`;
an isolated rerun's success was not accepted as repair. Owner #1562 adds a
six-second delayed startup case, reproduced RED, then separates the 30-second
startup observation from the unchanged five-second post-signal assertion.
All 18 runner/signal probes pass; no runner shell, model timeout, cleanup or
redaction guarantee changed. #1417 normally inherits the complete owner child.
Both immutable-head test phases completed: #1417 `dc8b` has **1890 passed /
2 explicit live-only skips / 1008.98 s**; #1562 `b2e9` has **1875 passed /
2 explicit live-only skips / 837.94 s**. However, both runners exited **137**
during Docker removal. This is consistent with the unchanged 20-second cleanup
watchdog, but the saved logs do not establish signal attribution or precise
elapsed timing. Neither is a successful full-lifecycle receipt. Sanitized JUnit SHA-256 values are
`3d3a9fec41477cffc8786e7ab4e1006fa9ad09dc73e5afa3e53998e268ebdb6d`
and `b45206540f4683773f8d8dd7aeee66a3cf1b69c198ee2c99043be0e68aca444d`,
respectively. Task-label inspection found one empty CI-test network after both
containers were gone; it was removed by verified exact ID. Both generated
projects now have no containers, networks or volumes. This recovery does not
change either failed exit. Investigate daemon teardown timing and rerun the
complete lifecycle without weakening the cleanup/cancellation boundary; the
underlying cause of the slow Docker operation remains unproven.

Refreshed local Trivy scans of
#1417 merge ref `91212236c1a018859f5fe58551397b924d9477b0` and #1562 merge ref
`6c04a43d3d491fb96e0f9762bbbc53fd2e9d8dec` match the stated current trees.
Both have zero HIGH/CRITICAL fixable vulnerability/misconfiguration findings,
including development dependencies, and zero separate secret-scan findings.
Security report SHA-256 values are respectively
`41a09c0be4cdd3abf1ef5de5059284f2621ffb2b9b5adc08f898fece4c210d6c`
and `b7e1c25d089dbe6c420735c956b4125bc0ac0b2602bcc083d9656e1d45bd2c48`;
separate secret-report digests are recorded in the respective PR receipts.
Keep this owner Draft while its prerequisite is unmerged. These results do not
prove actual mail delivery, browser cancellation, deployed behavior, p95, or
full coverage. Remaining acceptance is exact-head hosted checks and independent
review, prerequisite-first protected integration, and customer-path evidence.
[Root cause, alternatives, contradictory generated documentation and APA source](https://github.com/ContextualWisdomLab/naruon/blob/56025b17d752b8fbe2c759d9420876a73e26d51c/docs/doctoring/shared_send_postgres.md#smtp-connection-cancellation-follow-up)
remain linked to the implemented shared path.

**Visual inspection (2026-09-06):** The actual GitHub-rendered
[AGENTS.md playbook](https://github.com/ContextualWisdomLab/naruon/blob/8ec73818dc74ffb9f06173b062433162067e7d9e/AGENTS.md#agent-pr-lifecycle-playbook)
and verification section were inspected in a real browser at the immutable
head of [#1566](https://github.com/ContextualWisdomLab/naruon/pull/1566).
Desktop viewport: 1292 × 1040 CSS pixels; narrow viewport: 390 × 844.
The captured sections have readable headings, lists and links with no observed
text overlap or clipping. Long inline code wraps over multiple lines on the
narrow screen. DOM width cross-checks were 1277 and 375 pixels respectively,
within their viewports. The linked repository repair skill loaded at the same
head. Temporary viewport overrides were reset after inspection.

Retained task screenshot receipts (SHA-256): `agents_desktop.png` =
`544c1f7d945525b72b230c17ddf0018814fc4a1a1ffbf1109cbf6f96770b31ac`;
`agents_mobile_playbook.png` =
`3a8d3cfc528b93915101d9242353e9da20905c07de05883adadb63a3125b705c`;
`agents_mobile_verification.png` =
`500909b5e074ab2804dae4a3f52fe3c17b7eaa54cba086773ad7b72d519ab857`.
These are bounded documentation-rendering observations, not an accessibility
conformance audit, all-locale coverage, Storybook validation, product UI state
coverage, mail delivery or deployment evidence. No UI code or design was
changed, and no product-wide visual pass is claimed. Product-facing changes
must still retain actual normal/loading/empty/error/permission, responsive,
interaction and affected-locale screenshots tied to their own exact heads.

**Historical shared-send receipt and nested CI isolation refresh (2026-09-06;
#1417's 1666 head is superseded by the cancellation child above):** Existing Draft
[#1417](https://github.com/ContextualWisdomLab/naruon/pull/1417), head
`1666f76cf94c31e34c2762c9d75f52ea3040b9a2`, tree
`2a6aa3759b94e923325df7c6568cc6db3f8f63ca`, now normally inherits complete
CI prerequisite [#1562](https://github.com/ContextualWisdomLab/naruon/pull/1562)
at `30d8476b5fa1d4379684acaf2f334414597e97c4` and targets that branch.
The original `a9f334a442538b666e03e694731745d8aab4b45a` send delta is retained.
Real installation first failed on two Alembic heads; the no-DDL
`0020_merge_send_registry` joins both parent histories without deleting data.
The existing limiter runtime and its request rollback remain unchanged.

Its committed head passes **1887 tests / 2 explicit live-only skips, 120.85 s**,
with fresh/repeated real migrations and completed test-only DB/network cleanup.
Four database cases cover 80 concurrent attempts over independent user/org/
workspace scopes, the actual 61-second expiration wait, observed lock-wait
cancellation with no leaked pool slot, and a signed backend send on a one-slot
pool. A local mutation removing request rollback fails with HTTP 503 and was
restored before commit. SMTP and DNS validation remain external-boundary doubles;
these tests do not prove delivery, browser cookies, representative load or p95.
JUnit SHA-256: `f581d06533152c7a5f70246abf32398bc59cb604c525c6974e5a960effac7ff2`.

CI owner #1562's ordinary child fixes three migration-test subprocesses that
discarded the parent's explicit configuration-file selector. Three intercepted
dispatch cases failed before the fix, without executing an unsafe child or
reading operator files. On its own committed head/tree
`89a68659baeab385f195ec37c11ffe6b73b52d3f`, the complete migrated suite passes
**1874 tests / 2 explicit live-only skips, 54.82 s** with scoped cleanup.
JUnit SHA-256: `ced9e9330ccc670588f59e52b4bdf8cf288ca6e8368cc414875b918c9b3d7f7b`.
The actual configuration boundary is child-process dispatch, not merely the
parent shell. No production default or credential authority was changed.

| Requirement / owner | New local evidence | Remaining acceptance |
| --- | --- | --- |
| PRD: shared send quota survives concurrent sessions; #1417 | Production 10/60 quota, independent scope dimensions, real expiration and durable counts | Hosted exact-head checks, protected integration, delivery and multi-process/load evidence |
| TRD/operability: request and limiter share bounded capacity; #1417 | Signed route and cancellation use real PostgreSQL connections; dropped rollback is detected | Browser cookie/proxy path and deployed interruption |
| Security/test: nested migrations exclude operator configuration; #1562 | Three RED-to-GREEN child-dispatch probes plus full migrated suite | Independent current-head review and Linux Actions |

Refreshed local Trivy scans of #1417 merge ref
`abc115c644c408681206712d59a916eee5f7dcfb` and #1562 merge ref
`72206670444ee0e775de7c72631bdb0592aedcc4` match their respective current trees.
Both have zero HIGH/CRITICAL fixable vulnerability/misconfiguration findings
including dev dependencies and zero separate secret-scan findings. Their
security report hashes are respectively
`603aff0b0fe41bb7fc5bbd9287799132886ced2eec349ff08f53bd004907c8a4` and
`c5b36a42a166e67bcc3412273c51dc8b4d0da4f5cbb08127f02c29576aa6e99f`;
secret report hashes are recorded in each PR. Current-head hosted backend,
frontend, security and image checks remain queued. Both PRs remain Draft and
unmerged; no coverage percentage, release or protected advisory resolution is
claimed. [Send decision and APA references](https://github.com/ContextualWisdomLab/naruon/blob/1666f76cf94c31e34c2762c9d75f52ea3040b9a2/docs/doctoring/shared_send_postgres.md)
and [CI root-cause record](https://github.com/ContextualWisdomLab/naruon/blob/30d8476b5fa1d4379684acaf2f334414597e97c4/docs/doctoring/application_ci_postgres.md)
retain failures, alternatives and reproduction boundaries.

**Review admission repair (2026-09-06):** Existing dependency owner
[#1571](https://github.com/ContextualWisdomLab/naruon/pull/1571) was marked
Ready for independent review at unchanged head
`3f568412da61f12ba36c71765bf915acc8abb85d`; the timeline records
`ready_for_review` at `2026-09-06T09:26:51Z`. Its own 52 frontend files / 439
tests, lint/typecheck and frozen installation pass. Its merge ref
`beaaf7415a9ae57caaff9c53d0cb612924da7ec0` (tree
`21bb392248542c8b8c7b498dd4f2af292d8c1d51`) has zero local HIGH/CRITICAL
fixable Trivy vulnerability/misconfiguration findings with dev dependencies
included; report SHA-256
`5a0016d6af002ed06cc6ab3425d78d3265f435eddf05db8f171c79fa5097e2bb`.
No unresolved review thread was returned. This is a standalone owner receipt,
not borrowed #1562 evidence.

Requiring approval before leaving Draft prevented central review dispatch:
[protected OpenCode admission source](https://github.com/ContextualWisdomLab/.github/blob/43024633eba9d96b0456970391360da5a171fbda/.github/workflows/opencode-review.yml#L360-L369)
declines a live Draft. Ready enables review but does not waive any merge gate
or make a Proposed foundation consumable. Current-head OpenCode run
`34024017879` remains queued; no new post-transition run was observed in the
queried inventories. The metadata transition is not dispatch or approval
proof. Retain other incomplete owner stacks as Draft and obtain exact-head
hosted evidence plus qualifying review before protected landing.

**Historical migrated PostgreSQL CI receipt before nested-child repair (2026-09-06):** Existing Draft
[#1562](https://github.com/ContextualWisdomLab/naruon/pull/1562) was measured at
`4d2e4abc2c369d5e85bced4027b6f81857721ea2`, tree
`4a140dca9ffb2f5a182794a7e40375f0e7df5edd`. It normally merges the complete
#1503 prerequisite `19d5860bc27e860acba940390f5792721cd99e5e`, including #1565,
while retaining #1531 base `550798ccafebea4b1a9a65018e63b9661ff25a53` and all
#1554/stacked-trigger history. The old head exited zero with all five search DB
tests skipped; a real empty DB then failed in migration 0001. The existing
migration owner repairs installation; the CI owner supplies the execution path.
Ordinary merges also preserve dependency owner #1571's complete original delta
and compatibility repair `3f568412da61f12ba36c71765bf915acc8abb85d`.

On the committed head, the shared test-only Compose runner installed fresh
history, repeated Alembic, and ran **1871 passed, 2 skipped, zero failures/errors
in 29.29 s**. The two skipped cases require `LIVE_BASE_URL`; all ten PostgreSQL
tests executed. No customer mailbox, actual provider, browser cookie/proxy,
deployed service, representative p95 or full-coverage claim follows. Generated
DB/network cleanup completed; JUnit SHA-256 is
`e2f2ac6593cd0a088b23624d4c4506a5a479346c7eb99becbffd8215d7001b40`.
Frozen pnpm 11.5.3 installation, all 52 frontend test files / 439 tests
(4.28 s), lint and TypeScript checks pass on this same committed head.

| Requirement / owner | Verified local scope | Remaining action |
| --- | --- | --- |
| PRD: storage/search regressions cannot hide behind unavailable DB; #1562 | Real fresh/repeat migrations and complete suite; required DB skip/xfail and skipped collection fail | Terminal exact-head Linux Actions and prerequisite-first protected integration |
| TRD/security: tests cannot inherit operator provider/replica settings; Naruon bootstrap | Explicit existing bootstrap selector, minimal child environment, task-owned negative probes | Hosted security evidence; no new tenant credential authority or provider routing |
| Operability: cancelled tests preserve failure and finish scoped cleanup; #1562 | Real SIGTERM command doubles, owned process groups, report redaction before bounded cleanup, timer reaping | Independent current-head review; live product recovery is separate |

[Exact-head doctoring, failure receipts and APA sources](https://github.com/ContextualWisdomLab/naruon/blob/4d2e4abc2c369d5e85bced4027b6f81857721ea2/docs/doctoring/application_ci_postgres.md)
records the decision before merging prerequisites. The independent agent's two
signal probes passed; they are not GitHub approval or database tests. Required
hosted checks and default-branch dependency alerts remain separate. No PR was
closed, no provider source copied and no release claimed.

Historical RED: the refreshed HIGH/CRITICAL fixable Trivy scan of GitHub merge
ref `a7d2d409d146a134817df4c258ece4ab8e171508`, tree
`67dab67ba5534258c690a110724d9ef6da503623`, for the preceding #1562 head
`ef858172152615d54b393ea3ca5748ab2c4e03db` exited **1** for
`frontend/pnpm-lock.yaml`: `js-yaml@4.3.0`,
[GHSA-5p4m-2wfm-xmqj](https://github.com/advisories/GHSA-5p4m-2wfm-xmqj),
patched in `4.3.1` / `3.15.1`. No HIGH/CRITICAL misconfiguration was found;
a separate secret-only scan exited zero. Neither cleared that dependency
finding. The first integration candidate then passed Vitest but failed
TypeScript with TS1503: its named regular-expression capture was incompatible
with the product's ES2017 target. #1571 repaired the test with a numbered
capture, preserving the target, override and lock blob
`018f0382c815ea7a35899e64ddb6c3645399fcb6`; owner focused tests, typecheck and
lint passed before integration. No duplicate patch or suppression was added.

Historical local GREEN: GitHub merge ref
`0ca44cfa8302e6b0228de24a4eed284f1d0c4a99` has parents #1531 base plus then-current
#1562 head and the same tree `4a140dca9ffb2f5a182794a7e40375f0e7df5edd`.
Trivy vulnerability/misconfiguration scanning, including development
dependencies and fixable HIGH/CRITICAL findings, exits zero with no findings.
Report SHA-256:
`cc64d4f5ad685b52e98079a243915a636e35ea04fc51a38220ab079897354933`.
A separate all-severity secret-only scan of that committed archive also exits
zero; report SHA-256:
`c148c3f0eb704a9c50b7a74fa24fb19d8f467cb26b09d57853c98546ac533c8e`.
These scans do not prove protected-branch advisory resolution or deployed
safety. Earlier-head Application CI `34024085621` and image validation
`34024085830` are queued; Bandit `34024085668` is pending, not completed
evidence. The workflow lookup is PR-trigger-filtered and first-page only,
not an exhaustive required-check inventory.

**Import physical-lease and signed backend refresh (2026-09-06):** Existing
Draft [#1317](https://github.com/ContextualWisdomLab/naruon/pull/1317) now has
exact head `af362d58190c0bf2ed122d718473fe3c2bd503c4`, tree
`027eb9d28c2a3677dd11d2ffd878fd4ef1c3fe29`. Its normal merge retains original
head `1b422f15e6e5f56be679f691c8ff925c9a420fb1` and migration owner #1503
`19d5860bc27e860acba940390f5792721cd99e5e`; the PR is retargeted to
`fix/workspace-document-registry-migration` at that exact prerequisite. No valid
delta or existing migration identifier was removed. The no-DDL
`0020_merge_import_registry` reconciles both revision branches; local-runtime
ADR-0001 is Proposed, not protected acceptance.

The clean committed head passes **242 tests, zero failures/errors/skips,
11.41 s**, after locked dependency sync and fresh/repeated real PostgreSQL
migrations. It reproduces provider lookup before import with one pool slot,
actual repeated cancellation and backend termination, simultaneous same-account
and different-user/organization imports, and an actual signed backend ASGI
import with unsigned rejection. Connection cleanup and task-only DB/network
removal were confirmed. No old mocked API fixture name is treated as signed
DB proof. The public-mail excerpt is anonymized and bounded, not a customer
inbox or representative performance workload.

| Requirement / owner | Verified scope | Remaining action |
| --- | --- | --- |
| PRD: importing or cancelling mail must not strand later imports; Naruon import | Source retained after committed-item interruption; independent replica can reacquire; duplicates and other accounts remain separate | Browser HttpOnly cookie/proxy, deployed interruption and user-visible recovery |
| TRD: one physical lease covers per-item commits; Naruon import | Native transaction adoption, strict unlock confirmation, repeated-cancel cleanup, no SQL on a replacement connection, owner-scoped new graph IDs | Caller must have only settled/read-only work; flushed/raw-SQL writes are not detected by the pending-ORM guard |
| CI installation contract; existing #1562 / #1503 owners | Local tests use real migrations; #1562 now has its own committed-head full-suite receipt above | Finish exact-head hosted checks and protected integration; no workflow copy or unavailable-DB skip |

- Exact JUnit SHA-256: `238da7ad1c6e772cd087a3576f7c81d4d81780a6f0f0b4b3986a229910da965c`.
- [Exact-head decision, UML, failure receipts, source attribution and APA references](https://github.com/ContextualWisdomLab/naruon/blob/af362d58190c0bf2ed122d718473fe3c2bd503c4/docs/doctoring/import_lease_lifecycle.md).
- [Shared migrated-PostgreSQL CI owner request](https://github.com/ContextualWisdomLab/naruon/pull/1562#issuecomment-5557877080).

Focused Ruff and whitespace checks pass. Required hosted checks and qualifying
review, predecessor-first integration, released owner contracts, actual provider
embeddings, representative p95, and measured full coverage remain open. The
existing default-branch dependency alerts are not resolved by this result.
Hourly instructions preserve these boundaries and their existing schedule.

**Reply-task scheduler and conflict recovery refresh (2026-09-05):** Existing
Draft [#1486](https://github.com/ContextualWisdomLab/naruon/pull/1486) advances
without force from `b32954dbf6066bc0d953887e8ca06820588f2c5f` to
`1709ebb8d79f55c688a141aa932fa00468bf836d`, tree
`5a39d4eef5a936969b14f649af21638df24a90f1`, retaining its full calendar,
attachment, migration and Noema proposal. The direct base remains
`develop@042b0c70531b229af3acbd0421a2f23098d848b3`.
Its own actual PostgreSQL RED reproduced a stranded lease after task commit
(worker and reader PID 79), owner rollback failures, and lost-backend continuation.
Independent review then exposed real competing task-insert failures at bulk
commit and savepoint boundaries, plus stale configuration after deletion between
workspaces. Each was reproduced and repaired; no sibling worker pass was reused
as scheduler evidence.

The exact corrected head passes **165 tests, zero failures/errors/skips, 2.49 s**,
after locked dependency synchronization and fresh/repeated migrations to
`0022_noema_orchestrator_gateway`. Both changed runtime modules measure
**259/259 statements, 82/82 branches, zero exclusions**, with **24/24 documented
class/function/method definitions**. Twelve real PostgreSQL cases cover the
observed-mail replay, independent replicas, one-slot execution, cancellation,
connection loss, commit/savepoint races and committed configuration deletion.
Twelve additional scripted edge cases remain unit-only evidence. Existing API
smoke fixtures do not establish live signed-auth or realistic inbox accuracy.

| Requirement / owner | Current evidence | Remaining action |
| --- | --- | --- |
| PRD: saved follow-ups must not halt later work; Naruon scheduler | Replica excluded during work and admitted after cleanup; later owners recover after healthy rollback | Signed browser behavior, deployment interruption, realistic workload/capacity |
| TRD: coordination and source-task identity survive concurrent writes; Naruon task service | Existing task UID preserved, both source workspaces processed, no work after observed mailbox deletion | Hosted contract/security checks, manual API authorization and broader proposal validation |
| Operability: no unleased continuation or hidden test-client fallback | Lost backend aborts; one-slot cleanup verified; dev-only `httpx2==2.5.0` declared and obsolete warning ignore removed | Protected integration and immutable release; direct/session-affine PostgreSQL deployment contract |

- Exact JUnit SHA-256: `7ab943b0ceffcb26a72c802272cde48f410282c4cfe6e76bee5905725333a69f`.
- Two-module coverage JSON SHA-256: `207cd65f29b945c2f9f3d40f75bcb081f29da0c4e1744648edd7ebdea24a4c5d`.
- [Decision, UML sequence, APA references and failed-receipt history](https://github.com/ContextualWisdomLab/naruon/blob/1709ebb8d79f55c688a141aa932fa00468bf836d/docs/doctoring/reply_sla_physical_lease.md).

ADR-0005's premature Accepted label is corrected to Proposed without dropping
its history or allocating a new identity. An intermediate test-only import
rename failed collection and is explicitly not GREEN; the forward correction
was fully rerun on the pushed head. Fresh REST enumeration finds 26 check-runs
(queued work and skipped non-applicable jobs), no current-head reviews, and an
open Draft PR, not a merge-ready or released product. GraphQL quota failure was
handled with REST, not interpreted as an empty gate. Test-owned DB and network
cleanup is verified. Repository default-branch security alerts remain separate
work; this repair does not claim alert closure, whole-product 100% coverage,
exactly-once processing or realistic latency acceptance.

**Physical-connection lease and interruption recovery refresh (2026-09-05):**
Draft [#1469](https://github.com/ContextualWisdomLab/naruon/pull/1469) advances
normally to `a312ea5e516fe1d696cfb35ffff7d3a731ad9cd2`, tree
`83bf3605c961dc7be1c304585762a58de0124ba7`, preserving the complete
`1b757d5` delta and direct #1427 base `cb08b1c3ea2aba8844fc29ef703c34368cc55e47`.
Actual PostgreSQL commit/rollback contention exposed two stranded leases: an
unrelated pool reader received the worker's still-locked backend, and another
replica could not acquire after the worker completed. The repair holds one
physical connection across both phases and per-item transactions. It requires
confirmed unlock, aborts a disconnected cycle without unleased reconnection,
invalidates before session-close rollback, and resumes after the last completed
item rather than skipping unattempted prefetched rows.

The exact final head passes **305 tests, zero failures/errors/skips, in 225.30 s**
with clean-lock synchronization, fresh/repeated migrations, the complete 17-file
suite, and `-W error`. The worker measures **258/258 statements, 58/58 branches,
zero exclusions, and 22/22 documented function/class definitions**. The unchanged
40,758,835-byte NASA PDF remains intact in migrated PostgreSQL with active
indexes. Real DB cases cover commit/rollback contention, one-slot completion,
acquisition/processing cancellation, backend termination, and failed release.
An actual task-cancellation case gates session close to verify invalidation
ordering; the gate simulates blocked cleanup, not a real network black hole.
The two independent review findings first failed five tests and then passed;
final read-only re-review found no remaining actionable finding in that scope.

- Final JUnit SHA-256: `a7bf4bab7352c8c1fd9e720b48f59d63057de29a5fdf049ebe2faef8ff3d6ea2`.
- Worker coverage JSON SHA-256: `025ff2ea21aa66efc15bdbc9afc8ab3499591d085219b327d278b240a60b7363`.
- [Exact-head doctoring and sequence](https://github.com/ContextualWisdomLab/naruon/blob/a312ea5e516fe1d696cfb35ffff7d3a731ad9cd2/docs/doctoring/bounded-attachment-parse-source-contract.md)
  records RED/GREEN, rejected alternatives, primary PostgreSQL/SQLAlchemy
  references, and retained source/ADR lineage. ADR-0023 remains Proposed.

| Requirement / owner | Verified scope | Remaining action |
| --- | --- | --- |
| PRD: pending files resume after interruption; Naruon recognition | Independent-replica reacquisition and original-byte retention; unattempted cursor recovery | Signed browser recovery, actionable retry states, live interruption evidence |
| TRD: lease covers the complete sweep; Naruon worker | One held connection, supported one-slot pool, explicit unlock, fail-closed disconnect | Pool capacity and representative concurrent load; external provider idempotency is not proved |
| Sibling root repair; import #1317 / scheduler #1486 | Each now has its own exact-head migrated PostgreSQL receipt above | Keep the three lease implementations' evidence separate; finish their own hosted/owner prerequisites |

No new dependency, shared model timeout, mutable provider adoption, schema/index
removal, or protection change was introduced. Test-owned PostgreSQL/network
cleanup completed. Required hosted checks and qualifying current-head review,
the protected prerequisite stack, immutable NewsDOM release/pin, actual 64 MiB
recognition, and realistic p95/capacity evidence remain open. Passing this worker
module's coverage does not establish whole-product 100% coverage, exactly-once
external execution, security-alert closure, or a protected/released product.

**Historical bounded source retention and worker recovery receipt (2026-09-05):** Draft
[#1469](https://github.com/ContextualWisdomLab/naruon/pull/1469), exact head
`1b757d5aa25c469157f8f03301964eb3061ed0fe`, tree
`6b520c3cbe824d4017b97c39ef61fa702434e04a`, normally inherits #1427
`cb08b1c3ea2aba8844fc29ef703c34368cc55e47` and concurrent remote
`facadfb1ce535c5d124e2a463a844942a7704ba5`. Neither history nor the
prerequisite CHANGELOG was discarded. The former attachment ADR-0006 remains
Proposed as ADR-0023; the complete old ADR-0005 body is preserved as a historical
snapshot alongside canonical ADR-0021. All 161 open PRs were inventoried; a
10:07:23 UTC recheck found the other 160 head/base pairs unchanged and no
unrelated ADR-0023 collision.

Actual PostgreSQL fault injection exposed a separate worker defect after the
size-boundary fix: rollback expired every prefetched row, and the error logger
and next item attempted implicit I/O. Two real-PDF cases failed with
`MissingGreenlet`. Cached primitive IDs plus explicit recovery-only reloads
produce 29 focused passes. Subsequent test/fix commits `220c7d0` and `1b757d5`
preserve provider HTTP 413 as the same size-rejection category when the provider
has a smaller limit; this transport check uses MockTransport, not a live provider.
The exact pushed commit passes **277 tests, zero
failures/errors/skips, in 73.71 s**, after clean-lock synchronization and fresh
and repeated migrations to `0020_search_trigram_storage`. The unmodified,
hash-verified NASA PDF is 40,758,835 bytes. Fresh sessions compare complete
bytes and identities through pending, actual size rejection, transaction
rollback, and processing the next item. Full-size synthetic boundaries remain
unit-only. JUnit SHA-256 is
`5ec09d7152e0f3551fa670ac15567282ae02ac71170cd51eb5e3e51433abab10`;
task-owned PostgreSQL and network cleanup completed. The
[exact-head doctoring](https://github.com/ContextualWisdomLab/naruon/blob/1b757d5aa25c469157f8f03301964eb3061ed0fe/docs/doctoring/bounded-attachment-parse-source-contract.md)
records the primary SQLAlchemy/NASA evidence, RED/GREEN distinction, full test
command, retained proposal history, and concurrent-delta reconciliation.
The prior `db083c9` 276-pass receipt remains historical; no earlier test or
review was transferred to the later head without re-execution.

| Requirement and owner | Current evidence | Remaining acceptance action |
| --- | --- | --- |
| PRD: preserve an admitted original and continue unrelated files after one failure; Naruon ingestion | Real-PDF persistence and two-item rollback regression; no source truncation or identity replacement | Signed upload/browser recovery and actionable document failure/retry states |
| TRD: bounded admission, per-item transaction recovery, and separate provider transport; Naruon worker / NewsDOM provider | Proposed 64 MiB retention; existing 20 MiB client guard rejects before network; successful batches have no added query | Protected owner integration, immutable bounded NewsDOM release, exact consumer pin, actual 64 MiB recognition |
| Operability: retain full-size indexes and measure realistic capacity; Naruon storage/runtime | Migrated indexes stay enabled; complete bytes survive writes and rollback | Concurrent heap/storage/index/lock costs, tenant quotas, representative p95 ≤ 20 ms; no performance claim from test duration |

Fresh post-push required check-run enumeration returned zero checks and no
current-head approval. Keep Draft; earlier checks do not transfer. The push
also reported six default-branch dependency advisories (four high, two
moderate), which require independent owner diagnosis and are not negated by
this local suite. PR count, provider release, security readiness, and protected
merge are not claimed complete.

**Default-branch dependency triage (2026-09-05 10:15 UTC):** all six GitHub
alerts remain open with `fixed_at: null`. The protected source remains
`develop@042b0c70531b229af3acbd0421a2f23098d848b3`. Read-only alert and manifest
checks identify the following existing repair lanes; no alert was dismissed.

| Alerts and current source | Existing owner / next action |
| --- | --- |
| Alerts [88](https://github.com/ContextualWisdomLab/naruon/security/dependabot/88)/[89](https://github.com/ContextualWisdomLab/naruon/security/dependabot/89)/[90](https://github.com/ContextualWisdomLab/naruon/security/dependabot/90): `aiohttp==3.14.1` in `requirements-strix-ci-hashes.txt`; the strictest first-patched version is 3.14.3 | #1244 `50351e8cacc65b4124ba2145e00d41aeceef0775` proposes the 3.14.3 hashed lock. Repair its exact CodeQL/noema evidence; do not duplicate the dependency PR or count it as protected-patched |
| Alert [91](https://github.com/ContextualWisdomLab/naruon/security/dependabot/91): frontend `js-yaml@4.3.0`; first patched 4.3.1 | Ready-for-review #1571 `3f568412da61f12ba36c71765bf915acc8abb85d` owns the override/lock and ES2017-compatible regression (owner refreshed 2026-09-06). Complete exact-head security/review gates; #1459's inspected 4.3.0 lock is not this repair |
| Alerts [87](https://github.com/ContextualWisdomLab/naruon/security/dependabot/87)/[86](https://github.com/ContextualWisdomLab/naruon/security/dependabot/86): alert ranges exclude `cryptography==50.0.0` and `pyasn1==0.6.4`, already present in protected manifest/locks, but alerts are still open | Reconcile dependency-graph/manifests and the security record; do not call these closed or suppress them. #1494's 50.0.1 proposal is separate and retains pyasn1 0.6.4 |

**Noema owner-boundary refresh (2026-09-04):** Noema protected
`main@e1ac9d50f6c646f04be8c137c8acdc7200182fcd` defines Noema as the
credential and maintenance control plane for governed GitHub automation and
assigns provider discovery and routing to `contextual-orchestrator`. Naruon
PR #1384 (`0fd330137cdd19068fa8903dc70e1dc88f42cdc9`) and #1486
(`b32954dbf6066bc0d953887e8ca06820588f2c5f`) remain draft consumer lanes.
Noema #536 (`5531a5327d822028c4be59e290b4d101b34d49db`, verified
2026-09-04T13:38Z; supersedes the earlier `a14cbe02` observation) is a draft
shared-package proposal, not a released dependency. Naruon #1527
(`23680b13b443bb4eb7659b9a75073ecc1b67e133`) has no common Git history with
current `develop` and contains mutually contradictory owner claims; ADR-0006
therefore records the repair as Proposed rather than transferring its evidence.
Its supersession record preserves the predecessor's valid implementation and
stack-overlap observations, rejects the unproven shared-runtime conclusion, and
replaces the absent directive, edited-as-verbatim text, and mutable line-number
references with exact owner evidence. #1527 stays open until protected merge and
exact merge-result verification prove full-delta succession.
Contextual Orchestrator #1004
(`6a992538b6efcc34b957f72fc599bb33ac40c152`) is the current owner candidate
for distinct-provider structured-output recovery; its focused 31-test suite
passes after a non-force merge of current `main`, while hosted current-head
checks and independent review remain pending.

**Search storage and owner propagation refresh (2026-09-05):** Naruon Draft
[#1572](https://github.com/ContextualWisdomLab/naruon/pull/1572), exact head
`cd8ff413d4ed8a5f2855c47a21a31db5661cd487`, is the bounded search-schema
owner on #1503 `19d5860bc27e860acba940390f5792721cd99e5e`. Real migrated
PostgreSQL exposed whole-document GiST leaf overflow on all four search
surfaces. A forward GIN candidate preserves complete text and exact ranking
SQL: four regression failures before repair become 131 passed, zero
failed/skipped, after exact dependency synchronization and fresh/repeated
migration. A catalog assertion prevents a false pass from removing all indexes.
GIN does not accelerate the existing distance-only top-k query. Representative
search p95, migration lock/build/storage costs, current-head required Checks,
and qualifying independent review remain acceptance gates; this is not a
released search-performance repair. Proposed ADR-0020 and the
[exact-head doctoring receipt](https://github.com/ContextualWisdomLab/naruon/blob/cd8ff413d4ed8a5f2855c47a21a31db5661cd487/docs/doctoring/search_trigram_storage.md)
record the alternatives, primary PostgreSQL evidence, and retained-data rollback.
ADR-0008 was already present in #1418; all 160 then-open PR file lists were
checked before selecting the unused local proposal number 0020.

The search prerequisite is now non-force propagated and pushed through the
existing stack: #1468 `53ce38ed6683d01a9d113069f5ac5a8f17e133a2` passes
131 strict PostgreSQL/search tests; #1427
`cb08b1c3ea2aba8844fc29ef703c34368cc55e47` passes 132. Both fresh/repeated
migrations reach `0020_search_trigram_storage` without skipped tests. #1468
retains its unique bootstrap assertion. #1427's 64 MiB PDF admission remains
a Naruon proposal, not proof of an immutable NewsDOM release; its colliding
ADR-0005 proposal is preserved as ADR-0021.

Draft #1497 `69f50ae684f50c501ff2f49be2969f1d211d7f3c` now normally
inherits that chain and passes **345 tests, zero failed/skipped**, with exact
dependency sync, fresh/repeated migration to `0021_merge_provenance_workspace`,
and `-W error`. The unchanged 8 MiB-class cited-segment regression now passes.
Retained portable identities survive rollback/re-upgrade; forced incompatible
imports leave one successful writer and no losing rows/mappings. Proposed
ADR-0022 preserves the former ADR-0007 lineage, which collided with #1361.
The earlier unpushed checkpoint's 288-pass/1-failure result is historical.
See the [exact-head combined receipt](https://github.com/ContextualWisdomLab/naruon/blob/69f50ae684f50c501ff2f49be2969f1d211d7f3c/docs/doctoring/tenant_provenance_integration.md).
Current-head required Checks, independent approval, signed HTTP/browser restore,
representative search/migration performance, and owner release gates remain
open. No delta or PR was discarded to reduce the queue, and these local passes
do not transfer approval or hosted evidence between stack heads.

**AGENTS operating knowledge refresh (2026-09-06):** Draft #1566 exact head
`8ec73818dc74ffb9f06173b062433162067e7d9e` preserves normal parent
`7beb0fa6c2d67611f67518d9e43fe206266585cb` and the prior skills/procedure
playbook. It distinguishes general JSON Schema from a provider-supported
subset, an offline counterexample from a hosted root-cause claim, and an owning
transport's cleanup from borrowed stream helpers. It also requires safe
task-owned negative probes, real process exit checks, cancellation cleanup,
and the verified `trivy image --download-db-only` command. The exact-head
documentation/governance suite passes **48 tests, zero failures/errors/skips,
0.09 s**; JUnit SHA-256
`668953583b5bbcb4349433f09105ea35f566dcb7ce57f806170bb98f0fc0ac13`.
The latest guidance separates Ready review admission from merge authority,
preserves incomplete foundation Draft state, and requires head/base checks
before and after transition. An independent instruction-consumption check
classified four scenarios without permitting any merge: complete independent
slice, incomplete foundation, changed head, and stale approval. Its scope and
identity-check ambiguities were clarified. No new text-presence assertion was
added and this bounded exercise is not a GitHub review or runtime gate test.
These source checks do not establish a repaired provider/runtime or central
Noema #1641 GREEN. The PR stays on #1564's
`codex/agents-pr-lifecycle-knowhow@615be4514add6a21eef743f591a65a5f8fef4dee`,
open/Draft/unmerged. Earlier 45-test receipts below remain historical.

**Historical AGENTS operating knowledge receipt (2026-09-05):** Draft #1566 head
`54e79d054f6f13c639f30d89882ed079e0122752` preserves `162c0df8049126944c60041c3374b4e47d8c16b4`
and adds physical lease ownership, invalidate-before-close cancellation,
last-completed cursor recovery, real independent-replica checks, and explicit
source-only/runtime boundaries. It also retains the recurrence rule to test
application behavior on the actually migrated database, retaining indexes,
constraints, full-size high-entropy content, and portable identities across
rollback. It now also records conflict rollback refresh, savepoint detachment,
fresh configuration-authority checks and actual between-operation interleavings.
Its **45 focused source/governance tests pass in 0.11 s** with `-W error` and
`--noconftest` in the existing environment; this is not a clean-lock, database,
or browser receipt. Exact JUnit SHA-256 is
`0ebdd903f8ca1697f3187dad484d6dc6e97f28fb774e90ceadeef19ee3ca88fa`.
Fresh REST enumeration found
zero qualifying current-head reviews and zero required check-runs.
The PR remains Draft on #1564; required hosted evidence is not inferred from
historical status contexts. Confidence (#1559) and fail-closed tool mutation (#1300)
rules formerly recorded only in its body are now proposed AGENTS source.
Strict confidence rejection is scoped to frontend consumers; backend coercion
is not claimed fixed. Tool registration/update/delete restrictions explicitly
preserve supported built-in execution and catalog reads. Normal merges retain
concurrent remote heads `847ef38ce09ba7deea7b10b3eda731b66d90c1ac` and
`10ee05c7b1b50b205560fd147ba0c67237a966b0`; their source-guard intent is
preserved while duplicate wording is consolidated. The combined suite first
failed one stale wording assertion, then passed 44 tests after alignment.
An independent consuming-agent scenario review clarified the frontend scope;
it is not a GitHub approval or product-runtime test.

**Historical tenant provenance portability evidence (2026-09-05T06:57Z;
current propagation and remaining acceptance gates are above):** stacked
Naruon PR #1497 (`705d8ece2c97edc8575ea59766fd8f68bf4cdb82`)
keeps export/import identity mappings scoped by target user, organization, and
workspace, validates archive closure before mutation, and restores records in
one transaction with PostgreSQL advisory locks for portable identities and
email imports. Global content identifiers remain collision-detecting rather
than silently overwriting another tenant's records. The previous
`93 passed, 114 skipped, 17 deselected` observation is superseded by a disposable
PostgreSQL 16.15 + pgvector run: `224 passed, 0 skipped`, including import,
re-import, rollback, scope isolation, and concurrent successful imports. An
explicit pytest `-W error` rerun also passes 224 tests. These fixtures create
the schema through ORM metadata; the API success tests mock the import/export
service, so they do not prove an end-to-end HTTP restore or deployment.
The actual fresh Alembic path on this same head fails at
`0011_email_read_state` with `relation "emails" does not exist` before reaching
the provenance migration. The repair owner is existing #1503, now non-force
stacked on #1565 at `19d5860bc27e860acba940390f5792721cd99e5e`: exact-lock
fresh/repeated migrations and 75 strict PostgreSQL/dependency tests pass.
That observation predates the now-pushed owner propagation and combined repair
described above. #1497 remains Draft/Proposed. See the
[reproducible evidence and dependency decision](doctoring/provenance_migration_evidence.md).

**Governed review evidence refresh (2026-09-05T06:08Z):** Naruon PR #1564
(`615be4514add6a21eef743f591a65a5f8fef4dee`) records the reusable exact-head,
non-force restack, isolated-test bootstrap, successor-delta, and protected-merge
procedure in `AGENTS.md`. Its current revision separates pre-merge readiness
evidence from post-merge commit verification and names the applicable
current-head CodeRabbit or structured OpenCode fallback contract. It also
inherits PR #1558's unique valid delta: repository-local security-skill routing,
review-only mutation boundaries, existing-branch remote-head equality plus the
verified absent-ref initial-push path, fail-closed GitHub API handling, truthful
commit attribution, NIST SSDF grounding, and safe independent work during gate
waits. Shared lifecycle skills now have direct procedural fallbacks, signing is
tied to actual repository policy, and metadata-only PR Governance is explicitly
excluded from canceling review concurrency. The repository OpenCode config now
uses only `contextual-orchestrator/orchestrator/free`; the stale-context exception
matches the reversible merge-gate procedure, verified complete-delta succession
is an explicit phase terminal state, and the public-domain NIST SP 800-218 PDF is
retained with a focused governance regression test. The OpenCode gateway
contract pins the token destination to the owner's documented loopback endpoint,
removes the arbitrary base-URL environment input, and disables the supported
client request timeout so long-running model work is not cut off at the default
limit. The current repair also replaces the provider's implicit API-key option
with an explicit standard `Authorization` header. The fixed loopback origin and
header configuration are source evidence only; this run did not verify the
effective transport's redirect behavior or prove token non-forwarding. Exact-head focused proof is
`36 passed`; CodeRabbit and hosted checks are pending on the repaired head. With
no source failure or merge conflict, the PR remains Ready for independent review.
Canonical workflow
owner PR ContextualWisdomLab/.github #1850
(`8eccc85378a842986e767e056960d8f544803c1d`) repairs two evidence losses. It
retains only allowlisted, secret-free gateway failure fields and stops creating
a line-1 source receipt when a deletion-only or unchanged file has no real
current-head changed-side line. The exact-line validator remains fail closed.
After review, a changed file with two receipt candidates now proves that
`max_receipts=1` returns exactly one while unchanged files still produce none.
The head is non-force restacked on protected
`main@f871694a4e5bbfaca75d999354d7944787e9340f`; 12 focused receipt tests and
the full owner suite (2,817 passed, one skipped, 21 subtests) pass. Both heads
are mergeable but their required
current-head checks and independent review remain pending, so neither local
result is protected-branch evidence yet.

**Utility boundary refresh (2026-09-04T17:06Z):** Naruon Draft PR #1505 is
the verified full-delta successor of closed PR #1547 for URL encoding/decoding
and JSON formatting. Exact head
`3bf2f42ab8c854046f16b516073c13b13af77c6b` closes a remaining RFC 3986
contract gap: Python `urllib.parse.unquote(errors="strict")` rejects invalid
UTF-8 but preserves incomplete or non-hexadecimal percent escapes, so the
canonical handler now rejects `%`, `%2`, `%ZZ`, and `value%4G` before decoding.
The focused backend suite passes 87 tests with warnings as errors; Ruff, seven
frontend console tests, TypeScript, and diff checks pass. The central scheduler
dispatch is run `33898524781`, currently queued. Hosted exact-head checks and
current-head independent review remain pending; this is not protected-branch or
release evidence.

**Structured-output confidence refresh (2026-09-05T02:43Z):** Naruon Draft
PR #1553 exact head `4643e3404e01a3c860cdbddb225000493357bb07`
repairs the product-owned project-graph response schema. The predecessor accepted
negative, greater-than-one, `NaN`, and infinite confidence and heuristically
clamped finite outliers downstream, allowing a provider value such as `7.5` to
become maximum confidence. Object and relation payloads now reject every
non-finite or out-of-range value at the provider boundary and projection uses
only the validated 0.0–1.0 value. Seventy-seven focused structured-output,
project-graph, LLM, and grounded-answer tests pass with warnings as errors, plus
Ruff and diff checks. The superseded hosted runs were cancelled; central review
run `33939894339` is queued for this exact head. Current-head hosted Checks and
independent review remain pending, so the inference-confidence Gap is not yet
closed on protected `develop`.

**Mail-list performance evidence refresh (2026-09-04T18:03Z):** Naruon PR
#1542 exact head `918579729e3153f0b3b8c1c8d0dfcaf8aa12f025` now
contains an observable memoization acceptance test rather than only functional
selection coverage. It instruments the fetched email array's `map`, triggers an
unrelated search-input state rerender, and proves the stable list is mapped only
once; the existing test separately verifies selection and callback dependency
changes. Unmeasured fixed claims about 50-plus rows and exactly two rerenders
were removed. The current forward repair also deletes four completed
self-modifying patch scripts, restores the stronger two regression tests, and
removes unrelated Jules/E2E drift; its tree matches verified predecessor
`6113f76e1f7c1c56adc89f932ef423f34ef83566`. The current audit revalidated
seven focused tests, TypeScript, ESLint, and diff checks; all review threads are
resolved. Exact-head central review run `33940551294` is queued while the older
hosted runs remain cancelled. The PR stays Draft pending current-head hosted
checks and independent review;
no buyer-visible latency claim or protected-branch completion is recorded.

**Backend test-runtime dependency refresh (2026-09-05T04:42Z):** Minimal
protected-base prerequisite PR #1565 exact head
`52dfc863d1a5d6e4e80b6366f719dd09f2aa6172` removes the Starlette `TestClient`
warning suppression and promotes the already used optional-agent
`httpx2==2.5.0` pin into the core development, direct test, project lock, and
hash lock contracts. The current head also includes that pin in the shared
SHA-256 digest-format assertion instead of checking only record presence, and
a runtime test proves Starlette selects the `httpx2` module rather than its
deprecated fallback. PyPI's 2.5.0 trusted-publishing attestation and wheel
digest match the lock; the Starlette release history, exact provenance, rollback,
and APA 7th references are recorded in
`docs/doctoring/starlette-httpx2-testclient-dependency.md`. This
was found while validating utility consumer PR
#1538 (`c0eeca396904ec8baa1ec90d22986e94734567fd`): its source tests could not
collect under Python 3.14 with warnings as
errors because protected `develop` omitted the direct test dependency. Frozen
sync and the predecessor's 65 focused tests passed without the warning; the
current head independently passes the two focused manifest/runtime tests with
warnings as errors, Ruff, and diff checks. Broad dependency-upgrade PR #1494 exact head
`8ac9cfbe882bddfb85c44e84aca5c8ee841a3453` remains the successor owner for
`httpx2==2.12.0` and its other package migrations; it also removes the
suppression rather than reviving it. PR #1538 remains Draft until the minimal
prerequisite is protected-merged and its own unchanged-head review and Checks
complete. Its release note now names only the two effective tools and does not
claim the removed URL extractor. It distinguishes MD5/SHA-1 compatibility
fingerprints from the SHA-256 security hash and retains `usedforsecurity=False`
at that boundary. Seventy-three focused tests, Ruff, and diff checks pass, while
current-head hosted checks are queued. A fresh frozen-sync run also passes the
pin contract and a real FastAPI `TestClient` API path (`7 passed`) with warnings
as errors. With no unresolved thread, source failure, or merge conflict, PR
#1565 is Ready; 21 exact-head checks are queued and five are skipped. No gate
evidence transfers between the owner, upgrade, and consumer heads.

**Frontend dependency security refresh (2026-09-05T02:38Z):** Dependabot alert
#91 identifies GHSA-5p4m-2wfm-xmqj in transitive `js-yaml@4.3.0`. Draft PR
#1571 (`c3cf4efc478a264a0a010df82d1ea90b48776610`) uses the existing pnpm-native
workspace override to require patched 4.3.1 and carries an executable lock
contract. Pinned pnpm 11.5.3 reproduced lock hash
`018f0382c815ea7a35899e64ddb6c3645399fcb6` byte-for-byte; a narrower update
command was rejected because it changed unrelated Vite and WASM closure entries.
Both focused tests and diff validation passed at that historical head; the
2026-09-06 integration exposed TS1503 despite Vitest success. The current
owner repair and new merge-ref security receipt are recorded above. Protected
completion and independent current-head review remain pending.

**DAV authorization boundary refresh (2026-09-05T01:08Z):** Ready PR #1345
(`8146c56587acea5c4aa859ba9366eef0f39540d7`) is now non-force merged with
`develop@042b0c70531b229af3acbd0421a2f23098d848b3`. It preserves the framework's
single decode, rejects nested encodings that would expose traversal dots,
separators, backslashes, or control octets, and keeps owner and organization
scope on DAV and document reads. The 82 focused authorization/network tests and
Ruff pass. Both information-only review threads are resolved. The previous
Strix failure was fail-closed provider evidence (NVIDIA rate limiting and an
unsupported direct-OpenAI request contract), not a completed vulnerability
finding; fresh exact-head Checks and independent review remain required before
protected merge.

**CardDAV and identity successor boundary (2026-09-05T01:23Z):** Draft PR
#1206 (`aba2a03f3ca87914fcf1ca1c751b173097852bca`) remains a separate successor
for CardDAV TXT discovery single-decode semantics, opaque Prompt Catalog API
identity, and OIDC-only administrator authority. Its unique delta does not copy
#1345's DAV route, document-scope, or local-provider network changes. Sixty-one
focused tests and Ruff pass on `develop@042b0c70531b229af3acbd0421a2f23098d848b3`;
the current head has an independent approval. Keep it Draft until #1345 reaches
protected `develop`, then non-force restack, rerun both prerequisite and unique
contracts, and collect fresh exact-head Checks before Ready promotion.

**Semantic configuration naming refresh (2026-09-05T02:34Z):** Draft runtime-config
PR #1521 (`1269f6d8f09d54b24795ad32dc2fc05ec220491d`) preserves the published
`version` and `features` wire keys while translating them to qualified internal
product fields. The frontend now rejects malformed successful wire payloads
before caching and uses the existing fail-closed fallback. Thirteen frontend and
39 backend focused tests plus ESLint, TypeScript, Ruff, and diff validation pass;
21 hosted jobs are queued for the exact head. The aggregate changes-requested
state predates this head and is not completion evidence; keep the PR Draft until
current-head review and required Checks pass.
Connector schema PR #1520
(`e2043884a34fd08a5c2cc17726a6a615fa29d647`) confines legacy `capabilities`
and `status` names to JSON aliases while using semantic owned fields internally.
Both wire and owned names validate independently, conflicting duplicate inputs
fail closed, and default serialization preserves the legacy keys. Two focused
tests, Ruff, and diff validation pass; central exact-head review run
`33940315065` is queued after predecessor review lanes were cancelled.
Tasks bounded-context PR #1515
(`8a532ef30b295f59daa890ca82aa3eeaf4e5077e`) preserves established HTTP aliases
while exposing ticket-task semantic names internally. A fresh CodeGraph audit
found three dead reply-SLA helpers duplicated in the API after behavior moved to
`reply_sla_escalation_service`; the API copies are removed so the service is the
single behavior owner. Forty-six naming, Tasks API, and reply-SLA tests pass with
one skipped, and Ruff/diff checks pass. Twenty-one hosted jobs are queued for the
new exact head; predecessor review and check evidence does not transfer.
Draft agent-registry PR #1537
(`7665a2efaeaae75b3123a73a6291a1c2abba2b87`) similarly keeps legacy generic
JSON keys only in its anti-corruption loader and publishes semantic fields to
application callers. Its latest repair rejects an entry when canonical and
legacy names carry different values instead of guessing which value controls
dispatch; exact duplicate values remain accepted during staged migration.
Eight focused registry tests, Ruff, and diff checks pass. Twenty-one hosted
jobs are queued for the new exact head; predecessor checks, reviews, and local
tests do not transfer as merge evidence for either head.

**Customer documentation refresh (2026-09-04T16:20Z):** Naruon PR #1519
(`a9f0bf97ce8bec2d518824c1c0a25b162e6a1155`) is the current customer-facing
README and public Pages lane. Its latest repair restores the tested ownership
boundary: repository workflows own product tests, while the
ContextualWisdomLab central required workflows own OpenCode review, Strix
analysis, branch updates, auto-merge, and mechanical merge actions. The same
head preserves reviewed dotenv duplicate-assignment handling and applies mode
`0600` before generated local secrets are written. The current repair also
opens the dotenv target with `O_NOFOLLOW`, so an existing symbolic link cannot
redirect generated credentials into an operator-owned file. Seven focused
setup tests, including target-preservation on symbolic-link rejection, and Ruff
pass. The PR is Ready with 21 fresh hosted jobs queued; the prior 41-test result
and earlier requested review do not transfer to this head.

**Authentication owner prerequisite refresh (2026-09-04T16:27Z):** Naruon
Draft PR #1532 (`d93aabcc134ae461cf7f42d6cf26c6ca29deb9f5`)
remains a consumer lane and must not restore ROPC. Its login and signup routes
fail closed before parsing credentials, while Authorization Code with PKCE uses
a nonce-bound same-origin popup completion channel. Thirty focused frontend
authentication tests, TypeScript, and ESLint pass with the repository-pinned
pnpm 11.5.3. The previous seven review findings targeted predecessor code;
current-head source preserves their security outcomes without implementing an
unreleased password/session contract. Keyverse Draft
PR #128 (`e1cf0807d6b15e8d8300eb252533aa05b20b93c9`) disables that path while a
standards-compliant headless session contract is unfinished. Its merge-ref
account-unification failure was traced to a retired repo-local hourly PR steward
test. Closed PR #145's deletion is fully preserved by Ready owner PR #146
(`e6da5dd3762b45acf4e0a70b672327f38f4ba04b`). PR #128 is now ordinary-merged
above #146 and retargeted from the closed #145 branch to
`codex/keyverse-orchestrator-free-development`; the deleted test no longer
appears in the child-unique diff. The complete account-unification suite, realm
validation, actionlint, and child diff check pass. #146 must reach protected
`main` first; then #128 must be non-force restacked and retargeted to `main`,
with fresh owner-contract Checks and independent review on that resulting head.

**Exact-head execution refresh (2026-09-04T17:03Z):** protected `develop`
remains `042b0c70531b229af3acbd0421a2f23098d848b3`. Naruon #1558
(`e5c5eee14050db40ae54ac1b33319b8c2feb7478`) is now a predecessor of #1564,
which carries its complete valid delta plus the newer exact-head repair rules.
#1558 remains open until #1564 reaches protected merge or an independent
equivalence check confirms succession; no count-only closure is authorized. #1538
(`6a09b3ab90325a9045e90495e77a88b0f58fad27`)
is the single writer for bounded ASCII email and selected Korean/North American
phone masking. A second remote acknowledgement commit again removed verified
behavior; the non-force corrective head restores the complete ASCII dot-atom
boundary, bounded malformed-input regression, and North American cases. Its
hash-generator contract labels MD5 and SHA-1 as compatibility fingerprints,
keeps `usedforsecurity=False`, and identifies SHA-256 as the security-capable
output. The release note now names only the two implemented tools rather than
the removed URL extractor. Seventy-three focused tool/API/privacy/dependency
tests, Ruff, and diff checks pass. The tool single-writer chain is now #1565 ->
#1300 -> #1301 -> #1302 -> #1538; the four-file feature delta preserves all
fail-closed mutation and source-bound removals. The shared matcher now rejects
malformed empty domain labels and restores selected North American phone forms;
84 combined contracts pass. Draft PR #1496
(`17b732a71dd9f77fd8cce083e1cd065774380665`)
is non-force restacked on that current owner head. Its three-file, 226-addition
delta contains only the URL extractor and tests; 103 combined contracts pass
without warnings. GitHub reports the stack clean, while protected parent integration and fresh exact-head
review/Checks remain required. Draft PR #1512
(`c5582d64ad096e68079799d992dedba44ef8f55e`) follows current #1496 head
`17b732a71dd9f77fd8cce083e1cd065774380665`, consumes the canonical matcher,
rejects empty domain labels and trailing ellipses, and records its RFC 5322
ASCII subset. A review acknowledgement had deleted the parent URL implementation
and regressions, causing a reproduced 404; the repaired head restores the exact
parent files and leaves a four-file, 131-addition email-extractor delta with no
deletion. The combined 106 tests pass with warnings as errors, alongside Ruff
and diff checks. Draft PR #1555
(`369b7a3a862390ec168c7b0565e44ecd679de322`) follows #1512 and carries
only the first/last-sentence extractor. It consumes both parent matchers and
preserves U+FF0E, decimal/title periods, URL/email periods, repeated terminators,
and trailing quotation or bracket punctuation. After a non-force parent merge,
the current stack passes 117
combined tests, Ruff, and diff checks. No predecessor gate evidence transfers
after these base/head changes. Draft PR #1482
(`052f79e11da8f1d465cbf95dbdcc44be3f44f519`) is restacked last on exact #1555
head `369b7a3a862390ec168c7b0565e44ecd679de322`,
reuses the canonical email and phone matchers, and adds bounded Unicode-email,
French-phone, and separator-optional Korean resident-registration masking. Its
catalog claim excludes complete de-identification, and NIST SP 800-188 grounds
that boundary. A concurrent acknowledgement ancestry was absorbed without a
force-push while preserving the validated tree. The effective child delta is
three files with 163 additions and no deletion; the combined tool and privacy
contract suite passes 120 tests with warnings as errors, plus Ruff and diff
checks. Timeline evidence on #1538, #1496, and #1482 shows that posting repair
evidence as an issue comment caused `google-labs-jules[bot]` to reply and was
followed by an unsigned, user-attributed rewrite from a stale agent workspace.
Those rewrites deleted validated parent security and dependency contracts.
Until the bound Jules sessions are terminated, this stack records evidence in
the PR body and this baseline instead of posting new trigger comments. PR #1502
(`0b9e324a91fd2148b2b2759cca875ac7d50c86a0`) pins its PostgreSQL service
image by digest and has local migration, real PostgreSQL, and 97-test evidence.
Its previous frontend failure occurred before tests because Corepack resolved
mutable `pnpm/latest` and received `ECONNRESET`. The PR now non-force inherits
workflow prerequisite #1562 and targets its exact branch; the effective
database/bootstrap delta remains eleven files. Actionlint, 40 governance and
stacked-workflow tests, and 62 focused migration/bootstrap/data tests pass
locally, with two PostgreSQL-service tests explicitly skipped in that focused
no-service run. Fresh hosted exact-head evidence is queued. The PR was returned
to Draft because its #1562 foundation, current-head review, and terminal hosted
evidence are not complete; the database/bootstrap delta remains preserved.
The Draft email-writing stack now carries every prerequisite delta by non-force
merge. Task 7 PR #1524
(`cc1da5125e761d80caa7b0e81bd346e1004fad2e`) adds deterministic race coverage
for cancelled queued Judge work and concurrent lazy executor creation; 65
focused tests and all 250 statements/54 branches pass. Task 8 PR #1530
(`e7bc7b5dc97b312ca907d2e1def15b399a51cd48`) consumes that head and closes the
publication-integrity boundary: the schema requires validated calibration and
complete evidence identities, while the loader resolves immutable evidence
bytes, recomputes every digest, binds artifacts to the preregistered protocol,
and rejects missing, malformed, mislabeled, modified, self-referential, or
pre-protocol evidence. Twenty-four focused tests and all 396 statements/188
branches pass. Task 9 PR #1535
(`d07c68ff36c7ed7fb1022138ac10134aa5654128`) consumes Task 8, initializes only
ephemeral isolated-test bootstrap values, and covers owner, clock, context,
Candidate, Judge, policy, confidence, cancellation, timeout, persistence, and
rollback failure paths; 32 focused tests and all 274 statements/64 branches
pass. Task 10 PR #1536
(`59fe843e0c04c6e8d920967ee73f16fceed5a5da`) consumes Task 9 and verifies the
production route through FastAPI's public reverse-routing contract; 11 focused
tests and all 39 statements/8 branches pass. All four lanes pass Ruff and diff
checks without warning output. GitHub had not materialized Actions runs for
these new heads at the observation time, so local results are not protected
merge evidence and predecessor checks or reviews do not transfer.
Draft PR #1563 (`b1169e26949e7f75ebdccbdb9bb1f07eeacc163b`) repairs the prompt-provider
error boundary. Provider-controlled exception messages and tracebacks no longer
enter application logs; operations retain only a fixed event name and exception
class, while the signed API returns fixed actionable copy. Client cleanup
failure cannot replace that response or leak a second exception message.
Provider URL/client setup failures now use the same fixed boundary, and an SDK
constructor failure closes the already-created safe HTTP client. The PR
non-force inherits and targets prerequisite #1565
(`52dfc863d1a5d6e4e80b6366f719dd09f2aa6172`) instead of copying its dependency
manifest. The effective child delta remains three files: the prompt boundary,
four focused regressions, and its doctoring record. The combined prompt, pin,
and release-governance suites pass 41 tests with warnings as errors; Ruff and
parent-base diff checks also pass. Doctoring connects the contract to OWASP
logging guidance and NIST SP 800-92. GitHub had not materialized a Check Run for
the new exact head at observation time, so the PR remains Draft and local
results are not protected-merge evidence.
PR #1511 (`f78222dda6ac961fa3c1c4fb2acd9d7625e7b672`) repairs Context Search
identifier language end to end. Backend and frontend runtime models use
`email_id`; the legacy `id` exists only at the `/api/search` wire boundary and
is translated once on receipt. Selection, React keys, ontology lookup, and
product events consume the semantic identity. Seventeen backend tests plus the
frontend SearchLayout regression, TypeScript, ESLint, Ruff, and diff checks
pass. Fresh hosted evidence is required because earlier failed review runs do
not transfer to this head.
Draft PR #1503 (`19d5860bc27e860acba940390f5792721cd99e5e`)
repairs the persisted Data workspace registry. Incremental databases that had
already run the original bootstrap lacked `workspace_entities` and
`workspace_documents`, while document creation did not provision the signed
workspace foreign-key row. Structured idempotent migrations and the shared
race-safe PostgreSQL provisioning service now cover both document creation
paths without accepting client workspace authority. The earlier 73-test rerun
used an undeclared local `httpx2` installation and is not clean-lock evidence.
Exact synchronization exposed the missing dependency; a normal merge of #1565
preserves both parent deltas and supplies the declared TestClient dependency.
On the resulting exact tree, fresh and repeated Alembic upgrade reach
`0019_email_read_state_repair`, and 75 tests pass with explicit `-W error`,
including historical, stamped-repair, and data-preserving downgrade cases.
Ruff and diff checks pass. #1565 is now its direct prerequisite; the historical
#1502-before-#1503 proposal is superseded, not a mutual dependency. Hosted
PostgreSQL, security, and independent review evidence remain required.
Draft PR #1497 (`69f50ae684f50c501ff2f49be2969f1d211d7f3c`)
implements Naruon's bounded tenant provenance archive: deterministic BagIt,
RO-Crate 1.3, and PROV metadata; OIDC-authoritative export/import; tenant and
workspace closure; portable identity remapping; transactional conflict checks;
and bounded archive parsing. CodeGraph review traced the shared service and API
authority paths. The delta is non-force stacked after #1427 in the prerequisite
chain #1565 -> #1503 -> #1572 -> #1468 -> #1427 -> #1497; its conflicting
ADR proposal is now ADR-0022, with former 0007 and 0005 history retained,
not prematurely Accepted. Earlier
157-fast/117-database receipts are historical scope-specific runs, not evidence
that the deployment migration chain succeeded. The new combined suite passes
345 tests after fresh/repeated real Alembic migration; the unchanged large-content
failure is repaired, and remaining acceptance paths are recorded above. Binary payloads,
credentials, provider state, embeddings, and audit-history portability remain
explicit non-goals. The head stays Draft until fresh central review controls and
protected checks replace historical malformed/absent reviewer evidence.
Ready PR #1493 (`997e18cf51ed7e8265a111c7637274a1f097db08`)
updates the self-hosted connector to websockets 17.1 and repairs the missing
runtime release boundary discovered during review. The existing image workflow
validated only backend, combined, and frontend images, so the connector change
could pass without building or publishing its owner runtime. PR and semver-tag
matrices now build `naruon-connector` for amd64 and arm64. The first arm64 build
failed on the x86-only hash lock; the verified Python 3.14 arm64 wheel digest is
now pinned alongside amd64. A second review found that the image copied only the
WebSocket client: configuring `DATABASE_URL` would fail before loading the
canonical database-backed mail and DAV adapters. The image now installs the
shared backend lock, copies that owner runtime, and verifies seeded adapter
imports at build time without embedding a credential-shaped test value; both
backend and connector locks resolve websockets 17.1.
Seventy-five focused tests, Ruff, actionlint, and warning-free adapter import
smoke pass for both platforms. After the central queue-owner repair, Application
CI, Bandit, and Docker attempt 2 plus bounded central review run `33934191278`
were requested on the unchanged head and remain queued. Deleted or dynamic
workflows that GitHub refuses to rerun remain non-passing; fresh hosted
`validate connector image` and protected review evidence are still required.
Canonical workflow-owner PR `ContextualWisdomLab/.github#1871`
(`25083c8b006db8ec8234aa02661d0c23a05c44df`) repairs stale schedule and
inactive-review test oracles against current protected main, closes Python 3.14
HTTP-error response leaks in the Noema, GitHub policy, Pages, and sandbox
readiness paths, and completes missing CodeQL rollout, admission, scheduler,
and direct-import contracts. A current-head P1 review exposed a daily-cadence
regression in the consolidated 18-repository recovery caller; the owner now
restores all 17 staggered cron triggers to hourly execution and rejects that
regression across the focused and full contract suites. The warning-fatal full suite passes with 2,900
tests, one skip, and 21 subtests; all 13,115 production statements and 5,294
branches are covered with no missing or partial branch. The PR remains Draft
until fresh hosted checks and exact-current-head independent review complete.
Attempts 1 and 2 of eleven current-head workflows were each cancelled in a
single timestamp cluster without a source-failure log; on attempt 2 the current
head coalescer itself remained queued. No third rerun or cancellation-cause
claim is made until authoritative runner or cancellation audit evidence exists.
PR #1539 (`acd8a8412475a38a86c2749958b59e589de6d1e6`) removes only the duplicate
local Dependency Review after confirming the central Security Scan retains the
exact-base/head moderate-severity hard gate; 36 governance tests and actionlint
pass. #1543 (`4d84882bc6864ab2ba63d068e1b2252a93dfc57a`) remains Draft and keeps the
trusted-base local evaluator for non-default bases. Synchronize workflow runs
cancel only older synchronize evaluations, while every same-PR event publishes
through one non-cancelling job lane so stale same-head snapshots cannot race on
the shared check/comment. Thirty-eight governance tests, the shell harness,
actionlint, and diff checks pass. Central scheduler main still does not prove the
structured adversarial fallback contract, so #1543 is not a complete successor
for #1531 and must not delete that delta.
Contextual-orchestrator successor #1066
(`6e7a08fc1a77f8be6a536f2de5426dad2fbb5225`) carries the complete #1060
stacked-security trigger delta on a trusted base-repository branch after the
fork head could not materialize long-running required review. Actionlint,
thirteen security metadata tests, and diff checks pass. #1060 remains open until
#1066 reaches protected main and exact-tree equivalence is verified; queued
hosted Checks and review are wait states, not protected integration evidence.
Contextual-orchestrator successor #1067
(`845d09dc666bee4a212710f517b0f1c9f38a0c52`) likewise preserves fork PR
#1058's complete psychometric-routing performance and research delta on a
trusted base-repository branch. Both heads resolve to tree
`db3ee97813c93df4bdebae41eb335523e882039f`; #1058 remains open until the
successor is protected-main integrated and that equivalence is reverified.
Contextual-orchestrator #1068
(`fa5446294ae7ae69f1c2958aa1ab6c071fa760bc`) carries fork #1063's current
NVIDIA hosted-access evidence above #1066. The predecessor/main and
successor/#1066 effective diffs share SHA-256
`2a79c5600dd54b3a47a27f70d9e75daeba80d5b886a9ab93005ce47d65c7d7f5`;
139 NIM, release-acceptance, and stacked-workflow contracts pass. EgressWeave
consumer PR #1046 (`7ebe9128245c3ad212f8f2d6456bd6d968cc5139`)
is stacked on #1068 with only its six owner-boundary files in the three-dot
diff; 47 focused tests and the exact stacked full suite (`3396 passed, 2
skipped`) pass. Both PRs remain open and mergeable while hosted Checks and
current-head review are pending; neither is protected-main or release evidence.
Contextual-orchestrator PR #1044
(`95bc9a7e7b9ad0b455c44715724c2998ad93868d`) removes a provider-embedding
batch test race by waiting on the existing completion contract before reading
terminal usage. Source, security, Strix, and quality Checks pass; the remaining
Noema failure is a 96.4-second gateway 502 with no source finding, so central
review retry run `33910613120` is queued without changing the exact head.
Contextual-orchestrator PR #1043
(`414e2340f5c23d2bca732ecd53234d69b941df42`) corrects the stale proposal to
cap the entire serial provider loop: the shared application, agent, and gateway
default remains unbounded, while upstream termination and durable candidate
health evidence govern failover. Its review thread is resolved and source,
security, quality, CodeQL, Semgrep, and Strix gates pass or are policy-skipped;
Noema retry `33910784180` is queued after an 1814.3-second gateway 502.
Admin-state PR #1039 (`ae9a331994bc075b2c2148c9f5ff29c53dd8fe9e`)
keeps successful model-group mutations distinct from refresh failures and
rerenders current agent assignments without erasing client-enriched analytics
or readiness state. All review threads are resolved and the current source,
quality, CodeQL, Semgrep, and repository-security evidence passes; central
review retry `33910863565` is queued after Noema infrastructure failure.
Contextual-orchestrator PR #1034
(`b03f3b10211e188e81313cba5e1cf641991a6f71`) is stacked on #1068 and uses
Thompson-sampled per-member stability for live model-group serving while admin
and report reads remain deterministic. Integer outcome counts survive
fractional-prior floating drift; zero-observation cold start retains static
order. Thompson (1933), Chapelle and Li (2011), and Agrawal and Goyal (2012)
ground the sampling mechanism, but do not prove optimality for the product's
composite stability-sample/EWMA-latency score. Ninety-three focused contracts
and the exact stacked full suite (`3399 passed, 2 skipped`) pass; hosted Checks
are queued and no protected-main or buyer-traffic optimality claim is made.
Contextual-orchestrator PR #1032
(`95b164542ba462d8015107ae6492fa36f22cc357`) is non-force restacked on #1068
and feeds successful `orchestrator/free` synthesis into the existing realtime
fast-mlsirm judge as observation-only routing evidence. Request eligibility,
ZDR, file-replica, and operator-budget boundaries remain in force; rejected
observations preserve incurred provider usage and never replace the served
answer. CodeGraph confirms the serving path from orchestrated completion through
`conduct` to model-judge verification. Two hundred three focused contracts and
the exact stacked full suite (`3426 passed, 2 skipped`) pass. The six-file delta
remains Proposed while current-head CodeRabbit and hosted Checks are pending;
it is not protected-main, release, or buyer-quality evidence. The live PR was
returned to Draft after its successor contract identified #1564 as a predecessor
whose full exact-head succession is still unproven; its delta remains intact.
AGENTS entry PR #1528 (`57254cb61ecc67dd593ea96ae878bf651682a501`)
adds verifiable read-first product, Project, gap, issue, Figma-decision, and
organization-governance links plus a regression contract. Reopened foundation
PR #1549 (`4c31028fa3e058515bd7203001de8ad05fc951b1`) is non-force stacked on #1528
and removes direct provider/model
routing from Naruon guidance and OpenCode configuration. Central workflows pass
only the gateway token to `contextual-orchestrator/orchestrator/free`; provider
discovery, capability routing, free-pool membership, and fallback remain with
the canonical owner. Consumer adoption still requires an immutable protected
owner release, and open PRs or unreleased branches remain Proposed evidence.
Historical stacked PR #1566 (`104ecf39d6affae7716ca81b4d167bf09abafcb1`)
was non-force restacked directly on canonical AGENTS writer #1564 and
normally merges current LLM-owner foundation #1549
(`f038377d7d95d445a0e9f3e37707278d792213a2`). Its operating delta adds
`agents-md`, Context7, DeepWiki,
sequential-thinking, remote-MCP ZDR handling, Superpowers test-first debugging,
the Ponytail minimal-solution ladder, truthful `Co-Authored-By` attribution,
and current `contextual-orchestrator/orchestrator/free` wording to `AGENTS.md`,
with two assertions in the existing lifecycle contract test.
That repair restores #1549's deleted LLM-authority regression and missing
CLAUDE/architecture owner boundary while retaining #1564's loopback-only
OpenCode endpoint and unset request timeout. Thirty-nine focused governance
contracts, Ruff, and diff checks passed on that head. Hosted suites were absent
because leaf branch filters do not attach them to this stacked base. #1566
therefore has one bounded central exact-head scheduler dispatch, run
`33941908363`, queued with review enabled and merge, auto-merge, and branch
updates disabled; duplicate current-head dispatch was absent before enqueue.
The dispatch is wait-state evidence, not an approval or hosted-check substitute.
#1566 remains Draft; the newer exact head and 44-test source-only scope are
recorded at the top of this baseline. #1564 protected merge, fresh exact-head hosted
Checks and independent review remain required after restacking on `develop`.
Former child #1567 was restacked to
`4456fabe0d4906f29d07f2b54fbf374462108798`; its sole prior child test failed
three current parent contracts and was removed rather than weakening the
canonical guidance. The resulting #1567 and #1566 tree SHAs are identical, so
#1567 was closed only after exact-head zero-valid-delta succession was proven.
Contextual-orchestrator PR #911
(`e80949188f0afa86052f10f5a9b627da1ee1ef0b`) is non-force restacked on #1068
and repairs durable routing-observation invariants found in current-head review:
successful batches need not invent latency, failed startup leaves no retention
lease, embedding failover contains persistence faults, and batch quality stays
bound to the execution-time routing context. Active unexpired leases govern
pruning; the historical maximum-window row is compatibility/audit metadata,
not live retention authority. One hundred ninety focused contracts and the
exact stacked full suite (`3452 passed, 2 skipped`) pass. The five verified
review threads are resolved, but hosted exact-head Checks and independent
approval remain pending; this is Proposed owner evidence, not a released
consumer contract.
Naruon PR #1553 (`4643e3404e01a3c860cdbddb225000493357bb07`)
keeps product-owned structured payloads fail closed for unknown fields,
implicit scalar coercion, and non-finite or out-of-range project-graph
confidence. A later OpenAI SDK namespace migration and private serializer test
were removed because transport selection belongs to the released
contextual-orchestrator consumer contract, not this six-file payload slice.
Seventy-one focused contracts and the full backend suite (`1820 passed, 33
skipped`) pass. The PR remains Draft while current-head hosted Checks and
independent approval are pending; existing direct SDK seams remain explicit
migration debt rather than an approved owner-boundary exception.
Canonical owner release PR contextual-orchestrator #1030
(`f753f453ce4fc3dbc612bb9bdbb8db4cbfd93c16`) now implements the missing
immutable publication mechanism: exact tag-namespace identity, annotated-tag
peeling, protected-main freshness, read-only verification, mandatory
exact-commit CycloneDX SBOM, and resumable asset attachment. It non-force
inherits Python/fast-mlsirm prerequisite #995 and the current NVIDIA hosted
prototype evidence from #1063; official NVIDIA guidance still separates free
prototype access from production licensing. Actionlint, Ruff, 83 focused
release contracts, 209 combined release/NIM contracts, and the full suite
(`3477 passed, 2 skipped`) pass. The PR remains Draft, ADR 0129 remains
Proposed, hosted exact-head evidence is pending, and the owner still has zero
published GitHub Releases; consumers therefore remain fail closed.
Draft PR #1525 (`8225123257400be29f72fe0e3039512e6c95ac78`) repairs the
project-graph selector boundary and its executable tests. `keyword` remains an
explicit deterministic mode; `llm` and `orchestrator` neither choose provider
details nor substitute keyword output when their requested capability is
unavailable. Stale tests that still constructed deleted authority-bearing
fields or monkeypatched the removed raw transport are gone. Ruff, 68 focused
tests, and the full warning-as-error backend suite (`1801 passed, 33 skipped`)
pass. The predecessor Strix artifact failed before scanning because its central
compatibility launcher lacked `httpx2`; canonical `.github` PR #1851 has since
merged the hash-locked dependency into protected main
`769691526f8c73cf714de8fe8ba51ae6cfa2901a`. Fresh #1525 exact-head hosted
evidence must prove that owner repair; prior failure evidence does not transfer.
Draft PR #1514 (`22a3ddff94c29f51a4f56590a85a7b723c454ecc`)
repairs Naruon's Relationship Context naming boundary while preserving the
published network-graph JSON keys. Current-head review also found that set and
database encounter order leaked into response arrays, so equivalent email
evidence could perturb client layout, cache, screenshot, and incident evidence.
The shared endpoint now emits nodes in email-identity order and edges in
source/target order. Eleven focused warning-as-error tests and Ruff pass; fresh
hosted Checks and independent review remain required, and no p95 improvement is
claimed without a measured buyer path.
PR #1522 (`d65b05992cee54964114c9011a2bbbddd663062f`) remains the bounded
NetworkGraph option-materialization parent and owns its repository-local Strix
lock prerequisite. Failed job `101062515199` proved the scanner stopped before
analysis with `ModuleNotFoundError: No module named 'httpx2'`; the target lock
now directly pins `httpx2==2.12.0`, its generated hash lock is unchanged, and
a hash-required Python 3.13 install imports that exact version. Its merged
#1568 child contributes behavioral cap and ordering tests without a duplicate
source owner; all review threads are resolved and 21 hosted jobs are queued.
#1526 was
repaired non-force at
`cd99fef3245d1097a0422e9b1f48cb42d51ab6e0`: it restored early-terminating
option loops, executable option-limit coverage, and a real parent-rerender
memoization assertion. Its current exact head `9a6be24a30c76497510b1de19f7cabe1254864a9`
then overwrote those repairs with full-array materialization and a private
React-marker assertion. The PR remains open for lineage; the overwrite does not
invalidate the verified delta. Stable successor #1560
(`e9e356c054d9935fa7918e980644bbd377c0eed4`) now inherits the repaired #1526
commit and current parent #1522 by non-force merge, removes the duplicate
private-marker assertion, and restores a behavioral parent-rerender regression
test in a focused test file. Its validated tree is
`e76963913d102ed3059ce790f1655110b52cb9d5`. The complete frontend suite (53
files, 439 tests), TypeScript, focused ESLint, and diff checks pass. No
predecessor gate evidence transfers, and #1526 may close only after #1560 merges
and exact protected-main equivalence is reverified. #1560 remains Draft while
non-default-base hosted review and validation evidence are incomplete.
Stacked successor #1568 merged into canonical parent #1522 at
`d65b05992cee54964114c9011a2bbbddd663062f` on 2026-09-05. The parent now owns
the first-wins lookup implementation plus empty, under-limit, exact-limit, and
over-limit relationship/node option tests covering insertion order, public ids,
user-visible labels, and the five-relationship/eight-node caps. The focused
21-test file, TypeScript, and ESLint pass. This is stack integration only:
#1522 remains Draft against `develop`, and its new exact-head hosted Checks and
independent review are still required before protected integration.
Governance owner #1531
(`550798ccafebea4b1a9a65018e63b9661ff25a53`) retains the CodeRabbit/OpenCode
fallback and stacked-base contract. Historical trigger-repair receipt #1562
(`bc91b36dec70c14e0cde526e2330638f5e0ce352`) is non-force restacked on that
owner. It removes pull-request base
filters from Application CI, Bandit, and image validation, scopes validation
concurrency by workflow/repository/PR, and keeps tag publication
non-cancellable. Its authoritative merge-gate policy now matches that behavior;
it also installs the repository-pinned `pnpm@11.5.3` before `setup-node` asks
for the cache path. This removes the mutable `pnpm/latest` lookup that failed
#1502's frontend job on `ECONNRESET`. The current head also completely inherits
#1554's rerun-isolation delta while preserving #1562's stacked-base identity.
Its first-attempt current-head Application CI, Bandit, and image-validation runs
were externally cancelled together while queued; attempts 2 of runs
`33927276046`, `33927276079`, and `33927276320` are now queued on the same exact
head. Earlier-head local and hosted results do not transfer.
Bandit-only PR #1554
(`6b7ad6ccb4a7a021d74381781f40af7cc97233f8`) removes the undeclared
Application CI and image-validation experiment from its effective delta and
keeps only the Bandit workflow plus parsed-YAML regression test. First-attempt
PR runs share the PR-number lane and cancel only superseded first attempts;
manual reruns use a `run_id` lane, so GitHub's pending-run replacement cannot
evict newer current-head evidence. The focused test and actionlint pass, all
current-head review threads are resolved, and fresh hosted evidence remains
pending. #1554 remains predecessor provenance until #1562 protected-merges and
an exact merge-result comparison proves complete succession; no check or review
evidence transfers.
PR #1500 (`dfee7c12a535a79ca43daa14b17c9580bcbf2658`) is likewise Draft after
repeated empty CI-trigger commits kept replacing its exact head while retaining
tree `9014b174aa1a07a2b6fee60c7211e1f3e9b09b4c`. Stable successor #1561
(`dea8edb64d4ae492aec8815798edad8b4200c1dd`) carries the full source delta
directly on protected `develop` and now inherits both current predecessor
findings: the explanation remains hit-testable across pointer movement, while
Escape dismisses a focus-triggered overlay without moving focus. Thirteen unit
tests, one isolated real-browser Playwright regression, TypeScript, ESLint, and
diff checks pass. No predecessor gate evidence transfers, and #1500 remains
open until the successor merges and equivalence is reverified.
PR #1488 (`5a5789e04b9e8bcb50ddd22fbc411fc7581a24d8`) repairs the calendar
sidebar's deceptive enabled controls. Location, delete, copy, and close actions
had no product-backed behavior and are removed; the remaining update check uses
the existing signed-session calendar writeback-intent callback and stays
disabled until source readiness. The interaction test now clicks the enabled
action and proves callback dispatch. The same test rerenders a selected event
with source writeback disabled and proves the callback cannot fire; two focused
tests, TypeScript, ESLint, and diff checks pass. Hosted exact-head evidence
remains required.
Stacked accessibility child #1569
(`b98abeef1259b6e23c82921a0dbe99a91ad29b06`) keeps sidebar ownership in
#1488 and repairs the reusable writeback section. It now evaluates the selected
source with the canonical writable-source predicate rather than treating every
non-null stale selection as writable; a read-only stale selection cannot enable
create, update, or provider execution and cannot display a false selected badge.
The latest tip had removed native disabled/writeback behavior, deleted the
validated tests, and rewritten parent-owned sidebar files; a non-force revert
restores the complete child delta. Eighteen focused tests, TypeScript, ESLint,
and diff checks pass. A warning-free desktop Chromium regression also proves
all four read-only actions remain disabled, the reason is visible, no selected
badge appears, no writeback request fires, and a screenshot is produced. The
non-default-base head remains Draft until #1562 supplies required hosted
validation and independent review evidence.
PR #1559 (`4d6b697e97f7f0d98700292680970b41e7b12c48`) independently succeeds the
confidence-boundary finding from conflicted #1436: it removes the frontend's
unit-guessing discontinuity and follows the backend's documented 0--100
percentage contract. The shared display boundary now rejects non-finite,
non-integer, and out-of-range values instead of rounding malformed `0.856` to
`1%`, `85.5` to `86%`, or `150` to a false `100%` claim. Its unit and
EmailDetail fixtures, pilot and full-product smokes, and AGENTS.md recurrence
rule share that unit; 28 focused tests, TypeScript, lint, and diff validation
pass on the current head. Twenty-six hosted checks were regenerated, so
predecessor GREEN does not transfer. Independent review and
current-head hosted success are still required; this remains Draft.

PR #1485 (`796083106d46cff494836004937bb767fbb9672e`) remains predecessor provenance
for the Today-dashboard recovery lane. Draft successor #1570
(`a48e8ba85b6d3a4ceb78e110582b3d5bc76d0d7c`) now preserves independent reads,
bounded abort and stale-generation rejection, and derives login recovery from
all five source statuses. Calendar 401 and WebDAV 403 no longer offer a
transport retry while core reads succeed; malformed successful payloads remain
fail-closed instead of appearing as legitimate empty states. Thirty-eight
related tests, TypeScript, ESLint, and diff checks pass. Fresh exact-head hosted
Checks and independent review are pending, so neither protected succession nor
closure of #1485 is proven.
PR #1531 (`550798ccafebea4b1a9a65018e63b9661ff25a53`) now honors an exact-head
structured OpenCode approval when no CodeRabbit check exists even if a pending
issue notice is present. On the current tree, 36 release/stacked-workflow
contracts and the full shell gate harness pass with warnings as errors, and
current-head unresolved threads are zero. The PR is Ready. The historical scheduler handles
`33871200407`, `33871251541`, and `33872054770` belong to predecessor heads and
are not reusable evidence. Canonical `.github` PR #1878 merged as
`1b65dbc35e7183722ad77894e2d80b39993be90d`, removing the organization-wide
queue sweep, and PR #1877 followed as
`b5efbc2762e472e4a380b0503b1f050f76fbb008`, repairing the Strix admission and
Noema cleanup contracts on protected `main`. The later central CodeQL, Strix,
and coverage jobs were cancelled and cannot be rerun from this consumer
repository because their reusable-workflow identifiers return 404. They remain
failed evidence rather than source findings. Fresh exact-head review and Checks
are still required; predecessor-head results remain non-transferable.

**Inventory observation:** the 106-PR open surface below is a fresh live
scan captured at `2026-08-25T15:52:01Z`, which returned 106 open PRs after
PR #1337 merged into protected `develop` at `2026-08-25T00:10:39Z` and
the later governance stack merge (#1448) and additional PR wave opened since
the previous observation. The
v0.2 baseline's 93-row snapshot from `2026-08-21T19:25:43Z` remains historical
context, as do the earlier 92-PR state after PR #1442 merged and the initial
83-PR observation in issue #1428; all counts are point-in-time evidence, not
current merge state.

**Follow-up delta observation:** a seventh live scan at
`2026-08-25T15:39:22Z` found the active exact-head work relevant to this
baseline: #1465 (`70596e26…`, tenant-archive import sanitization and duplicate
identity rejection), #1466 (`a3e6762f…`, origin-integrity port validation),
PR #1467 (`6816bc7f…`, utility-tool JSON boundary and Strix-trigger restoration),
PR #1468 (`1da167de…`, PostgreSQL smoke fixture schema alignment), #1469
(`de6d7128…`, bounded 20–64 MiB deferred attachment parse-source admission),
and #1455 (`d8757e65…`, attachment filename traversal hardening). The
governance root #1443 now has exact head `62a0d645…` after child #1448 merged
normally into its stack branch. #1448 merged at
`2026-08-25T15:31:39Z` with merge commit `62a0d645…`; its tree retains the
parent gate fix and the multiline, stale-head, and current-finding regression
cases. The merge-result Checks for that commit remain queued and are tracked
as post-merge canary evidence, not success.
The newly opened #1470 is now `aba77cf5…` (NetworkGraph edge-description
lookup cleanup); the predecessor `f8a70d37…` was discarded after a remote
commit reintroduced the dead argument and its callers. The current head also
removes the tracked 452-line `NetworkGraph.tsx.out` pre-refactor copy found by
Devin, with the 11-test focused suite, TypeScript, zero-warning ESLint, and
diff checks passing locally. Hosted Checks and independent approval remain
required.
These PRs remain open until their current-head required Checks and qualifying
independent approval satisfy the protected ruleset; this follow-up does not
reuse predecessor evidence or claim a merge. #1448 is historical after its
normal merge; #1443's current head is `62a0d645…` and must be reviewed and
checked again from that exact head.

Draft PR #1541 (`2eaf6134434a2ad29ad8fe0365aa1b34b848dd5f`)
separates attachment display sanitization from parser authority. MIME filename
percent signs and character references remain literal identity, while path,
markup, C0/C1, and bidirectional controls fail closed instead of manufacturing
a trusted extension. Fifty-five filename/parser/EML tests and Ruff pass locally
with warnings as errors. Prior OpenCode and Strix runs were externally
cancelled; central exact-head review run `33940228096` is queued, and the stale
metadata failure does not prove a source defect. Keep Draft until current-head
review and required Checks complete.
An exact two-tree comparison against `develop@042b0c70531b229af3acbd0421a2f23098d848b3`
still shows all four implementation, test, and doctoring files as a 344-line
effective delta, so no protected successor has fully inherited this work.

Draft PR #1570 (`a48e8ba85b6d3a4ceb78e110582b3d5bc76d0d7c`)
keeps Today-dashboard source failures distinct from legitimate empty business
data and gives the correct recovery action without hiding successful partial
sources. The latest repair makes calendar and WebDAV authorization failures use
the same login-recovery path as core data, while malformed successful payloads
cannot masquerade as empty business data. Exact-head local evidence is 38
related tests, TypeScript, ESLint, and diff checks; fresh hosted
Checks, independent review, and predecessor-equivalence evidence remain
required.

**Live exact-head queue refresh (2026-08-25T17:51Z):** the following
post-snapshot states supersede only the matching historical SHA references
above; the full inventory remains a point-in-time record and is not silently
rewritten. #1468 is `1da167de26b442be6961622f15bb36ae9374e6c4`; its source,
backend, and frontend evidence is successful, while the retried Strix run is
queued after the earlier NVIDIA NIM provider failure. #1469 is now
`575b0c24fd9cb98106989eb101de74c5ce383db3`, after a remote follow-up removed
the unreachable document-size branch; 109 attachment/import/NewsDOM tests
pass locally, and the PR remains stacked behind #1468 because the selected
full suite exposes the base fixture defect repaired by #1468. #1470 remains
`aba77cf5b6a47985b352e8d2c2d76413579ea88a`; backend, frontend, Strix, and
metadata checks are successful, and its exact-head CodeRabbit approval is
present, but the ruleset still requires the second qualifying approval and
the exact-head OpenCode dispatch is queued. #1455 remains
`b2b4701366bc6bb2de1347b19eac9b4ed64cc614` with backend/frontend evidence
successful and Strix still running. #1429 remains
`b93caf0e00d09de0f836d8e4b869054d792e674b`; its refreshed hosted checks are
queued or in progress. #1347 remains
`f9e1751e2d5069841b279ecd2414fbbcad2e5692`; its newest metadata result is
not merge evidence and the remaining hosted checks are queued. None of these
states satisfies the two-approval protected ruleset, and none is a force-merge
candidate.

**Live exact-head queue refresh (2026-08-25T18:06Z):** a subsequent
re-fetch supersedes only the matching queue entries above. PR #1436 moved to
exact head `034d2ff4e0d120d1e7b7669b35ea8eea7d8c1221`; its frontend, backend,
and Strix checks were recreated and queued, with zero unresolved review
threads and no qualifying approval. PR #1470 remains
`aba77cf5b6a47985b352e8d2c2d76413579ea88a`; its metadata, OpenCode,
frontend, backend, Strix, and security checks are successful, but only the
exact-head CodeRabbit approval exists and the protected ruleset requires a
second qualifying approval. PR #1467 remains
`6816bc7f938fe361f2eb7a0ecee427f87170fbcb`; source/security checks are
successful, metadata is still in progress, and only CodeRabbit has approved.
PR #1466 remains `a3e6762f01666f5b4e9d202932012de23b942c59` with all
observed required checks successful but no current approval. PR #1468 remains
`1da167de26b442be6961622f15bb36ae9374e6c4`; its source checks are successful,
the retried Strix check is queued, and its metadata gate is not a merge
result. PR #1469 remains `575b0c24fd9cb98106989eb101de74c5ce383db3`; its
source checks pass while image validation and Strix are running and metadata
is failed pending current review evidence. PR #1455 remains
`b2b4701366bc6bb2de1347b19eac9b4ed64cc614` with image checks successful,
coverage and metadata pending, and Strix running. PR #1347 remains
`f9e1751e2d5069841b279ecd2414fbbcad2e5692`; its three informational review
threads are resolved, but metadata is failed and Strix/coverage are still
running. PR #1429 remains `39d796d14b93484e004c13d7e2db4cc2eee5cdb1` with
the refreshed hosted suite queued. No entry satisfies the two-approval
ruleset, and no entry is a force-merge candidate.

**Current Checks inventory:** the same live scan found 106 open PRs. Completed
failures were limited to `metadata-only gate evaluation` and `strix`; the
metadata gate reports the underlying Strix failure and, on some heads, a
current-head CodeRabbit quota/provider warning. The Naruon hosted Strix logs
for the observed #1468 run show NVIDIA NIM HTTP 429 rate limiting followed by
an unavailable direct fallback. This describes that run's provider evidence,
not the central Strix default documented in `AGENTS.md`; it is failed
infrastructure evidence rather than a clean security result or a source defect.
These PRs remain blocked and are not
force-merged; the exact head must receive a successful hosted security result.
PR #1466 has successful required Checks but remains in GitHub's protected
auto-merge queue with `REVIEW_REQUIRED` and no qualifying independent
approval, so it is also not treated as manually merged.

The latest exact-head follow-up also records: #1347 at
`e97fa1e4…` with its governance regression tests passing but hosted required
Checks queued and no qualifying approval; #1433 at `b84255e5…` with source
checks passing but Strix failed closed after NVIDIA NIM HTTP 429 retries and a
configured direct OpenAI HTTP 404 fallback; #1450 at `073408ce…` with all
other Checks successful while the metadata gate remains in progress; #1455 at
`d8757e65…` with all hosted Checks successful but no current-head approval;
and #1466 at `a3e6762f…` with all hosted Checks successful but no qualifying
independent approval. These are live queue observations, not merge evidence.
The provider failures are retained as infrastructure evidence and are not
converted into source changes or clean security claims.

**Exact-head maintenance ledger (2026-08-26):** PR #1347 now has exact head
`f9e1751e2d5069841b279ecd2414fbbcad2e5692` on this protected base. Its
governance normalization wrapper now fails closed when the review-unavailable
`jq` parser fails or emits a non-numeric count, and its early-exit cleanup trap
removes the wrapper-created comments snapshot when no PR number is available.
The exact-head local contract suite is 14 passed and the shell self-test remains
green. Hosted required Checks
were recreated and remain queued, so this is not a hosted pass or merge claim.
PR #1364 now has exact head
`3a3baa6b8dc9ea224f46395cb78c91a45be2090c` on this protected base. Its scoped
S3 document lifecycle, encrypted provider registry, compensation/orphan cleanup,
migrations, API, and LocalStack/PostgreSQL integration contract passed 195
focused local tests, Ruff, compileall, and diff checks. Hosted required Checks
and independent approval remain required; protected auto-merge is enabled but
no merge is claimed. The attachment and UI work continued on independent
branches while hosted runners were queued. PR #1419
now has exact head `2924b5598d4f527d493e1fc88cebd8fe87e1a3c4` on this protected
base, with 263 focused attachment/inline-image/email tests plus Ruff passing;
its hosted required checks were recreated for that head and remain queued, so
the normal protected squash auto-merge is enabled but not claimed as complete.
PR #1436 now has exact head
`1573be3332725bfbd05053943988d652df22a846` on the same base, with 446 frontend
tests, lint, typecheck, Next production build, Storybook build, and desktop /
mobile Storybook screenshots for source-open, low-confidence,
blocked-execution, and shared-scale states passing locally. It intentionally
remains pending because it carries a UI overlay at this document path while
PR #1429 owns the canonical commercial baseline; merge #1429 first, then
reconcile #1436 against the canonical file before enabling auto-merge. These
observations are exact-head evidence, not a release or hosted security claim.
PR #1415 now has exact head `f576eefce98bdc44dc03eed88510f60c3e6cccd9`;
the OIDC `kid` selection and strict administrator-role boundary passed 98
focused authentication tests. Its prior Noema failure was malformed model and
repair JSON rather than an auth-test failure; Noema, Strix, and OpenCode have
each been rerun once as attempt 2 on the same head and remain queued. PR #1417
now has exact head
`ad3ba4e44a015a9da9da221c841d1d9f345b0947` after a non-force merge of current
`develop`; its PostgreSQL smoke seed explicitly supplies `is_read` after a real
existing-schema NOT NULL failure. Current-head review also replaced the fixed window
with an exact trailing-60-second count over existing scoped audit evidence,
moved the limiter into its own READ COMMITTED transaction, and coalesced denial
audits to one per scope/window. This prevents boundary double bursts, caller
commit leakage, stale repeatable-read snapshots, and denial-storm write growth;
86 limiter/email/parser tests pass with one PostgreSQL-only skip, and all five
review threads are resolved. Fresh hosted Checks are queued. PR #1455 now has exact head
`b2b4701366bc6bb2de1347b19eac9b4ed64cc614`; bounded filename decoding and
Windows-separator traversal protection passed 130 focused parser/import tests.
All three have recreated hosted Checks and remain normal protected-merge
candidates; no hosted pass or merge is claimed.

The protected-branch SHA in this header identifies the baseline's observation
point. The inventory's `Base-SHA` column is captured independently for each PR
at its scan time, so an older `develop` SHA in a row is expected snapshot
metadata rather than a second claim about the current protected branch.

**Live exact-head queue refresh (2026-08-25T18:38Z):** PR #1468 remains at
`1da167de26b442be6961622f15bb36ae9374e6c4` and its current hosted check rollup
has no failed or pending run; it still has zero qualifying approvals and zero
unresolved threads, so protected auto-merge has not occurred. PR #1469 remains
at `575b0c24fd9cb98106989eb101de74c5ce383db3`; its source checks are passing,
while the metadata gate remains failed on current review evidence and
OpenCode is queued. PR #1429 remains at
`f2143f9d997736040eb3152f59ce058dc22ea72b` with the refreshed hosted suite
queued or in progress. PR #1436 remains at
`034d2ff4e0d120d1e7b7669b35ea8eea7d8c1221` with frontend image, coverage, and
Strix work still running. PR #1470 has a successful current check rollup and
one exact-head bot approval, but still lacks the second qualifying approval.
None of these observations authorizes a bypass merge.

The owning upstream sidecar `Seongho-Bae/newsdom-api` PR #682 remains at
`585bb4e0fb719ab6a576cf46d1ef12b77872557b`. Its bounded 64 MiB source and
boundary tests are present, while its only failed hosted check is the
provider-infrastructure Strix run (NVIDIA NIM rate limiting followed by an
unavailable fallback); no source vulnerability report was produced and the
normal rerun workflow is unavailable. The provider PR therefore remains
`WAIT_AND_REMEDIATE`, not a clean security pass or a force-merge candidate.
NewsDOM issue [#707](https://github.com/Seongho-Bae/newsdom-api/issues/707)
owns the follow-up resumable-upload contract for documents above 64 MiB, so
the current synchronous fallback must not be mistaken for the target
commercial large-document UX.

The central `ContextualWisdomLab/.github` control plane has two related
current-head repairs: PR #1331 (`a1408f52…`) separates the direct-OpenAI
fallback API base from the primary provider and has all observed checks passing
except queued coverage, while PR #1333 (`5454a196…`) adds bounded provider
retry/attempt-log handling with OpenCode still queued. Both have zero
qualifying approvals and remain normal protected-merge candidates; their
changes overlap in `.github/workflows/strix.yml`, so the first protected merge
must be re-fetched before the second is restacked.

This document defines the evidence-backed boundary between what Naruon currently
ships on protected `develop`, what is present only in open pull requests, what is
still a product-plan aspiration, and what a buyer must be able to complete before
Naruon is described as a generally available commercial product.

Counts, branch SHAs, checks, reviews, and pull-request state are point-in-time
evidence. They must be re-fetched before a merge or release decision.

---

## 1. Executive decision

Naruon is no longer a small prototype. The protected branch already contains a
substantial, security-conscious **customer-owned communication and context
control plane**:

```text
customer-owned mail / calendar / contact / file systems
→ Naruon ingest, thread, search, context, evidence, task, and action control
→ explicit human approval or correction
→ conflict-aware provider writeback through an outbound connector
```

Naruon must **not** become an SMTP server, IMAP mailbox host, public MX provider,
calendar source of truth, or file source of truth. Customer providers remain
authoritative. Naruon owns scoped context, policy, recommendation, intent,
connector command state, retry/reconciliation evidence, and the user-visible
decision/action experience.

The accurate current product classification is:

> **Production-oriented pre-GA communication control plane with substantial
> protected-branch capability, an unconverged ~100-open-PR integration surface (102 at the 2026-08-25 snapshot), and an
> incomplete buyer-visible release/operations contract.**

The first sellable boundary is **GA-1: Customer-owned Mail, Calendar, Contact,
and File Control Plane**. The complete dense knowledge graph, no-ask
correct-by-exception reasoning, minimal-disclosure bridge, and third-party plugin
platform remain the north-star after GA-1 rather than prerequisites for the
first commercial release.

---

## 2. Evidence hierarchy

When sources disagree, use this order:

1. exact protected-branch code, migrations, tests, runtime contracts, and
   security boundaries;
2. exact protected-branch architecture and operations documents;
3. exact current pull-request code and current-head evidence;
4. open Issues and accepted ADRs;
5. older product plans, README limitations, and historical PR descriptions.

A plan marked `[LIVE]` is not proof if the protected implementation contradicts
it. Conversely, an old README statement that calls a protected implementation
“future work” must be corrected rather than used to hide shipped behavior.

---

## 3. Point-in-time repository snapshot

| Item | Observation |
|---|---|
| Protected branch | `develop@e5e99b4e3bb081b92c602358878856536030e2ca` |
| Product/package version | `0.14.4` |
| Open pull requests | **102** (live scan at `2026-08-25T00:26:45Z`, post-#1337 merge) |
| Open issues | **61** (live count at the same 2026-08-25 snapshot; 59 were open before this baseline program) |
| New completion issue | #1428 |
| Required backend runtime | Python 3.14 exact-head lane |
| Core runtime | Next.js frontend, FastAPI backend, PostgreSQL + pgvector |
| Default data authority | customer-owned mail, CalDAV/CardDAV, and WebDAV providers |
| Default merge posture | strict exact-head checks plus qualifying independent review |

The **102-open-PR** count is the live inventory snapshot captured on
2026-08-25 against the protected branch shown above, after PR #1337 merged.
The v0.2 baseline recorded **93 open PRs** on 2026-08-21 after PR #1448
opened, an earlier same-day snapshot recorded **92 open PRs** after
PR #1442 merged, and the initial completion issue #1428 recorded **83 open
PRs** on 2026-08-20 against `develop@c9bfba2...`; these are historical
baselines, not contradictions. Later live counts can change as PRs open,
close, or merge, so every release decision must re-fetch the REST state.

The protected branch requires exact-head backend, frontend, security, CodeQL,
dependency review, Scorecard, OSV, Trivy, Strix, source/evidence coverage,
backend/frontend/combined image validation, and OpenCode review contexts. Pending,
queued, stale, predecessor-head, skipped-required, neutral, author-only,
model-only, or local-only evidence is not passing evidence.

---

## 4. Protected-branch product truth

### 4.1 Shipped communication and workspace surface

Protected `develop` exposes buyer-recognizable product surfaces for:

- Today execution dashboard;
- Mail, thread history, search, reply, and pending-reply work;
- Calendar views, source-backed coordination, and writeback intent;
- Tasks and source-linked ticket work;
- Projects, project graph, and evidence-linked records;
- Context Search and hybrid retrieval;
- AI Hub and provider-neutral AI workflows;
- Data/document ingestion and controlled materialization;
- Security/policy/audit views;
- Settings, identity, provider, and deployment controls.

The product already distinguishes simulated local send from real delivery,
preserves `In-Reply-To` and `References`, scopes email/provider records by owner
and organization, keeps opaque public identifiers separate from sequential
surrogates, and applies deny-first RBAC/ABAC policies.

Proposed PR #1534 (`bbcd3c5376102964d5e375821524a80b61b84599`)
qualifies internal ABAC vocabulary while retaining the historical
`action`/`conditions` wire aliases and read-only compatibility properties. All
repository callers pass the evaluator policy positionally, 13 focused tests and
Ruff pass, and both current review threads were verified as informational and
resolved. Although `gh run view` cannot resolve the deleted workflow file, the
raw Actions run, jobs, and logs remain available. They prove a single
gateway-owned attempt served by
`google/gemma-4-31b-it` ended after 310.3 seconds with an upstream HTTP 502 in
`response_error`; this is provider failure rather than source evidence. The
remaining metadata gate also records a cancelled Strix run. Contextual
Orchestrator PR #1049 (`87612a68b3af1f305bb7b09bd0be860bad1b7fd6`)
owns the missing `orchestrator/free` 502 failover: its focused tests and package
quality checks pass, its review thread is resolved, and its current Noema,
Strix, OpenCode, CodeQL, Semgrep, and security jobs remain queued. Naruon
Noema run `33596312910` attempt 2 and bounded central review scheduler run
`33942317426` now revalidate the unchanged #1534 head; both are queued and do
not yet prove protected completion.
Central `.github` PR #1888
(`b61d8287a4a9aed3722868358b49116ada2999dc`) repairs a separate owner defect
exposed by #1049: one-language CodeQL dispatches for the same repository and PR
shared a concurrency group, so sibling Python, JavaScript/TypeScript, and
Actions runs cancelled one another. The group now includes the already
validated `required_language`; 25 focused contracts, Ruff, actionlint, and diff
checks pass, and ADR 0025 records the live run evidence and rejected full-matrix
alternative. It is non-force stacked on runner-image owner PR #1886 exact head
`7bd5b02ddb84d7887c5d9984bd144302235cdfdf`; the parent lint finding is fixed,
the combined 31-test suite passes, and the child retains a three-file effective
delta. It remains Proposed pending both parent and child protected-main review
and Checks.
Naruon #1505 independently reproduced the same owner gap at exact head
`3bf2f42ab8c854046f16b516073c13b13af77c6b`: Noema's sole gateway attempt
served `deepseek-ai/deepseek-v4-flash-0731` and ended in HTTP 502 after 2,375.2
seconds. The annotation contains no Naruon source finding. Central run
`33936495146` now targets owner PR #1049 with merge and branch updates disabled;
it is queued, not passing review or release evidence.

### 4.2 Source-of-truth and writeback sovereignty

Protected `develop` already enforces important commercial boundaries:

- customer mail, calendars, contacts, and files remain durable provider truth;
- browser input selects an opaque source reference but cannot assert ownership,
  region, credential, or capability;
- writeback is intent-only unless the user explicitly requests provider
  execution;
- provider execution re-reads server-authoritative source records;
- CalDAV and WebDAV updates preserve ETag/If-Match conflict semantics;
- private-network provider access uses an outbound-only connector rather than
  inbound firewall holes or public mail hosting;
- provider credentials and command payloads are excluded from browser and
  aggregate observability surfaces.

### 4.3 Durable writeback retry is implemented

The current protected source-of-truth document records behavior that the root
README still describes as future work:

- scoped `provider_writeback_retry_items` rows;
- encrypted retry command payloads;
- retry dispatch with retry enqueue disabled for the nested attempt;
- exponential backoff;
- `succeeded`, rescheduled retry, and `failed_exhausted` outcomes;
- persisted connector signal events for dispatch, timeout, transport, and
  adapter outcomes;
- organization-admin aggregate queue-depth reads without exposing payload,
  credential, runner, source, or retry identities.

This is a material product-truth correction. The remaining gap is not “create a
retry queue.” It is **finish connector packaging, identity/enrollment, complete
protocol coverage, dead-letter/reconciliation operations, and buyer-visible
support evidence**.

### 4.4 AI and scientific boundary

Naruon has grounded content segments, hybrid search, named/versioned KG
extractor seams, deterministic fallback, contextual-orchestrator routing, and
batch-embedding integration boundaries. It does **not** have a protected live
Structural Topic Model endpoint or fitted topic artifact. Deterministic keyword
metadata must not be marketed as STM or temporal event psychometrics.

TEPP may be consumed only through a separately accepted, immutable, versioned
scientific artifact/API with preprocessing, vocabulary, covariates, posterior
uncertainty, diagnostics, provenance, and abstention. Naruon owns identity,
authorization, adapter envelopes, and disclosure policy; TEPP owns the
scientific payload.

---

## 5. Product-truth and release-truth inconsistencies

| Inconsistency | Current evidence | Buyer risk | Required correction |
|---|---|---|---|
| README says durable retry/audit remains future work | protected operations document describes encrypted retry rows, retry worker, backoff, exhaustion, and aggregate visibility | buyers and contributors cannot tell what is shipped | merge a customer/operator README based on protected truth; keep unsupported behavior explicitly limited |
| Release architecture says first candidate should be `v0.1.0` | `VERSION` and backend package are `0.14.4` | release procedure may publish or validate the wrong identity | replace historical hypothesis with current release-train policy and immutable release manifest |
| Product plan marks typed Person/Event/Commitment/Plugin concepts as new/planned | current code search does not prove authoritative `graph_persons`, `graph_events`, `graph_commitments`, or `plugin_registrations` stores | UI/marketing can imply dense-KG/product-platform completion that does not exist | keep north-star language, implement typed domains through bounded PRs, and gate claims on protected code |
| The live open-PR population (93 on 2026-08-21; 102 on 2026-08-25) contains many overlapping, stacked, micro, dependency, governance, and broad integration changes | current GitHub inventory | predecessor evidence, writer collision, stale branches, and integration starvation | establish a release train, classify every PR, close duplicates, merge parent-first, and use one writer per authority cluster |
| Required independent review exists but the current human reviewer path is unresolved | #1371 | green automation cannot produce a lawful protected merge | resolve reviewer governance without weakening rulesets or self-approval |
| Connector is described through a self-hosted-runner analogy | protected code has protocol adapters and retry behavior but no complete released connector lifecycle | operators may deploy test infrastructure as production relay | deliver signed installable connector artifacts, enrollment/rotation, source health, fleet SLO, and runbooks |

---

## 6. Current pull-request surface

The current open PR count is too large to treat as one releasable integration
unit. This baseline does not claim that every one of the 102 PRs has been
line-by-line approved. It records the product-significant active lanes observed
and defines the inventory that must be completed before GA.

### 6.1 Product-significant active lanes

| PR | Lane | Baseline judgment |
|---:|---|---|
| #1364 | scoped S3 document-object backend | high-leverage GA durability lane; Draft until real PostgreSQL + S3 lifecycle, backfill, cleanup, failure, and exact-head evidence are complete |
| #1417 | shared PostgreSQL-backed email-send throttle | necessary multi-replica safety; keep isolated and merge only with current-head concurrency/security evidence |
| #1416 | provider-backed CalDAV create writeback | relevant to GA scheduling execution; preserve create vs update precondition distinction and integrate into the broader #978 contract |
| #1353 | HWP/HWPX deterministic recognition boundary | useful Korean enterprise document admission; does not complete parsing/conversion/search semantics |
| #1397 | inline-media admission/tracking-pixel classification | valid evidence-protection slice; remain Draft until the #1350 stack and independent review are coherent |
| #1419 | common image metadata | bounded local evidence extraction; no OCR/VLM claim |
| #1418 | auditable URL/contact hygiene | deterministic tool/evidence lane; ensure contact redaction is not represented as complete anonymization |
| #1317 | broad macOS/local-AI/runtime/governance integration | valuable evidence but unusually broad; must be decomposed or reconciled carefully because many active PRs overlap its surfaces |
| #1392 | customer/operator README rewrite | directly addresses product-truth debt and has reported exact-head checks; still requires independent current-head approval |
| #1300 | fail closed on unsafe global tool mutations | exact head `e3485b4dfed763cdcd846c7894dc5c5f69e445e0` is non-force stacked on TestClient foundation #1565; five-file product delta and 86 warning-free focused contracts preserve the safety posture until durable tenant-scoped plugin/tool registry exists; links directly to #976 |
| #1264 | EgressWeave integration | correctly dependency-blocked on an immutable released EgressWeave package and hash lock; mutable VCS dependency is forbidden |
| #1390 / #1391 | 56- and 78-package dependency groups | excessive blast radius, including major runtime and OpenAI client changes; split by compatibility/authority and rehearse migrations before merge |
| #1426 / #1414 | review-governance gate refresh | metadata-only governance repair; must not dismiss review, weaken rulesets, or turn stale aggregate state into false success |
| #1241, #1320, #1408, #1410, #1411, #1421, #1422 | accessibility micro-lanes | useful but numerous; consolidate non-overlapping UI fixes into bounded component-level trains to reduce 17-check amplification |
| #1424, #1412, #1401 | micro performance lanes | require real benchmark or stable complexity contract; do not let automated micro-PRs displace GA integration work |
| #1455 | path-traversal attachment parser hardening | high-value Sentinel security lane; prioritize within the new wave and merge only with exact-head Strix evidence once the provider outage clears |
| #1347 | rate-limited review status governance | current head constrains repository API-scope identifiers and merges the protected base; local tests pass, while hosted Checks and independent review are still required |
| #1433 | Message-ID whitespace hardening | source/security checks pass; the observed Strix failure is provider infrastructure (NVIDIA NIM 429 and direct OpenAI 404), so retry exact-head evidence without weakening the gate |
| #1450 | stray scratch/debug cleanup | all source and security Checks passed; wait for the in-progress metadata gate and current-head independent review |
| #1465 | scoped tenant archive import hardening | Draft head `e0b04d74…` non-force consumes Starlette TestClient prerequisite #1565 at `52dfc863…` and is retargeted to that owner branch; the effective archive delta remains nine files, rejects duplicate identities before writes, and sanitizes archive-controlled display fields; 76 archive/API/review/main/release/pin tests pass with warnings as errors, and an isolated `pgvector/pgvector:pg16` run passes the real export-delete-import-reimport PostgreSQL smoke with duplicate rows fully skipped; #1565 protected integration and fresh exact-head hosted evidence remain required |
| #1466 | origin-integrity URL validation | current head rejects explicit zero/out-of-range ports; keep the signed-session and SSRF contract tied to exact-head regression evidence |
| #1467 | utility-tool JSON and governance repair | deterministic URL/HTML/JSON utility surface; current head rejects non-standard JSON numbers and preserves the central Strix workflow trigger, while full smoke evidence still depends on #1468's schema fixture repair |
| #1468 | PostgreSQL smoke fixture schema alignment | Draft head `53ce38ed6683d01a9d113069f5ac5a8f17e133a2` non-force consumes #1572 at `cd8ff413d4ed8a5f2855c47a21a31db5661cd487`, preserving its unique bootstrap assertion; exact sync, fresh/repeat migration 0020, and 131 strict PostgreSQL/search tests pass without skips. Owner performance acceptance, protected integration, and fresh exact-head hosted review/Checks remain required |
| #1443 | CodeRabbit approval-notice governance root | current source/test lane narrows approval-notice parsing to the exact current head and ignores pending-review prose while retaining explicit findings; the predecessor Strix provider failure is historical, while the current head requires fresh queued Checks and a qualifying independent approval |
| #1448 | stacked governance regression coverage | merged normally into #1443's stack branch at `62a0d645…`; parent gate logic plus multiline JSON, stale-head unrelated prose, mixed blocker, and explicit current-head finding fixtures passed locally; merge-result hosted Checks remain queued and are post-merge canary evidence |
| #1469 | deferred attachment parse-source admission and worker recovery | current `a312ea5e516fe1d696cfb35ffff7d3a731ad9cd2` preserves #1427 and the full `1b757d5` delta; exact migrated 305-test receipt and worker 258 statements/58 branches 100% are recorded above, including real-PDF retention, lease contention/cancellation, transaction recovery and HTTP 413 classification; ADR-0023 remains Proposed; required Checks/review, released provider pin, real 64 MiB recognition and representative capacity remain open |
| #1427 | bounded PDF DOM upload | Draft head `cb08b1c3ea2aba8844fc29ef703c34368cc55e47` non-force consumes #1468 at `53ce38ed6683d01a9d113069f5ac5a8f17e133a2`, preserving PDF admission and deferred-worker contracts. Exact sync, fresh/repeat migration 0020, and 132 strict PostgreSQL/search tests pass without skips. Proposed ADR-0021 retains the former 0005 identity; the 64 MiB Naruon proposal is not actual NewsDOM release proof. Owner performance/release and fresh exact-head review/Checks remain required |
| #1572 | complete-document search storage | Draft head `cd8ff413d4ed8a5f2855c47a21a31db5661cd487` on #1503 replaces four overflowing GiST indexes through forward migration 0020; four RED regressions become 131 passing strict migrated-PostgreSQL tests. The unchanged large archive case also passes in descendant #1497's 345-test integration. Exact ranking SQL is retained, but GIN does not accelerate distance-only ordering; measured p95, migration cost, and current-head protected gates remain open |
| #1470 | NetworkGraph lookup optimization | bounded frontend performance slice; current head `aba77cf5…` preserves first-instance duplicate-ID selection, removes the dead `describeEdge` input, and deletes the tracked pre-refactor `NetworkGraph.tsx.out` copy; local 11-test, TypeScript, zero-warning ESLint, and diff checks passed, while hosted Checks and independent approval remain required |
| #1477 | SearchLayout lookup optimization | a comment-triggered deletion rewrite was absorbed without force into current head `52c914c3…`; the effective delta remains the memoized result lookup plus its task record, and all 437 frontend tests, TypeScript, earlier ESLint, and diff checks pass; the historical Strix result was `STRIX_PROVIDER_UNAVAILABLE`, so only fresh exact-head hosted evidence can satisfy the gate |
| #1456 | email-detail UX density | buyer-visible mail surface polish; hold to the responsive/accessibility evidence contract in the UI quality section before protected integration |
| #1462 | utility tool trio (URL codec, hash generator) | bounded deterministic tooling consistent with #1418/#1361; must not be represented as AI judgment or topic evidence |
| #1457–#1461 | refreshed dependency-group bumps | successor waves to the v0.2-flagged groups; the 64- and 86-package backend/CI bumps remain excessive blast radius and still require splitting and migration rehearsal |

### 6.2 Required complete inventory

Before a release candidate is cut, create a machine-readable and human-reviewed
inventory for **all** current open PRs with:

```text
pr_number
head_sha
base_ref_and_sha
draft_state
mergeability
changed_authority_cluster
stack_parent
stack_children
current_review_state
unresolved_threads
required_check_summary
product_lane
disposition
next_action
```

Allowed dispositions:

- direct GA-1 slice;
- ordered stacked child;
- dependency-blocked;
- governance-blocked;
- duplicate/superseded;
- experimental/north-star;
- unsafe or unrelated and to be closed.

The inventory must be regenerated after every parent merge or branch movement.
It must not embed provider credentials, customer data, review-body secrets, or
large copied PR bodies.

### 6.3 Merge-loop progress since v0.2

Point-in-time progress observed between the v0.2 snapshot (2026-08-21) and
this v0.3 observation (2026-08-25). None of this is merge evidence; every
claim requires a live exact-head re-fetch before any decision:

- **Merge-gate progression:** #1337 completed its gate progression (CodeRabbit exact-head approval obtained, branch updated onto the base) and merged into protected `develop` at `2026-08-25T00:10:39Z`; #1438 was non-force restacked on current `develop`, so its previous approval is stale and it remains open pending fresh exact-head review and terminal required-check states.
- **Stale-snapshot repair:** #1241, #1368, #1412, and #1320 received systemic develop-baseline restores that preserved each PR's intended delta while removing predecessor-base drift from the diff surface.
- **Thread remediation waves:** unresolved review threads progressed through repeated remediation cycles on #1264, #1332, #1347, #1349, #1361, #1380, #1339, #1376, #1412, #1452, #1454, #1449, #1457, #1436, and #1441.
- **External blocker:** Naruon hosted Strix runs have observed NVIDIA NIM provider rate-limit failures (HTTP 429) since approximately 2026-08-24, emitting zero model-reported vulnerabilities before infrastructure failure. This is an observation of the affected hosted runs, not a change to the central GitHub Models default in `AGENTS.md`; per repository policy it is failed evidence, not clean-scan evidence, and Strix-dependent gates cannot pass until the provider path recovers.

### 6.4 UI/UX quality contract and Storybook event inventory

The UI is a buyer-facing control surface, not a decorative shell. The current
design-system implementation is carried by PR #1436 and ADR-0013; it uses the
production stylesheet as the Storybook token source and records Figma file ID
`68b5XB58w8nwT2LYOOnikK`. Until that PR is protected-branch code, its stories
are current-PR evidence rather than shipped capability.

The UI/UX Pro Max checklist and Anti-Slop UI heuristics are adopted as review
inputs, not as normative standards or automatic approval. They help select one
coherent design direction, expose generic UI defaults, and force explicit
review of accessibility, touch targets, hierarchy, and state behavior. WCAG
2.2 and the repository's security/accessibility gates remain authoritative.

The latest local fixed-origin capture for #1470 used `/` at desktop (1440×900),
tablet (834×1112), and mobile (390×844). Tablet and mobile presented the
responsive shell and an explicit mail-loading state. Desktop presented the
navigation shell but no data surface while the backend was intentionally not
running; the Next development server also reported a hydration mismatch for
the search-input caret style. This is local diagnostic evidence, not hosted
release evidence, and is tracked as a separate UX/runtime gap rather than
mixed into the bounded NetworkGraph change.

| Quality axis | Required definition and applied evidence | Audit gate before GA-1 |
|---|---|---|
| Accessibility | WCAG 2.2 AA; keyboard order/focus-visible; accessible names; labels; live/status announcements; color is never the only signal; Storybook a11y test is `error` for applicable stories | axe/Vitest Storybook results, keyboard journey, screen-reader name assertions, and zero unresolved accessibility findings |
| Touch & interaction | primary pointer and keyboard paths; at least 44×44 CSS-pixel target or documented exception; 8px separation; loading/disabled/pressed feedback; no hover-only action | Storybook `play` events queried by role/label plus touch viewport browser test |
| Performance | reserved media dimensions, no avoidable layout shift, route/component splitting, virtualized long lists, and responsive feedback for async work | production build budget, responsive capture at 375/768/1024/1440, and measured CLS/input-latency evidence |
| Style selection | one documented design direction, consistent icon language, semantic tokens, deliberate radius/elevation, and no generic gradient/card/emoji defaults | ADR/Figma decision, token source review, and Anti-Slop heuristic checklist with human disposition |
| Layout & responsive | mobile-first hierarchy, no horizontal scroll, readable line length, safe-area/fixed-bar offsets, and synchronized desktop/tablet/mobile navigation | Storybook viewport stories and Playwright route/drawer assertions at each supported viewport |
| Typography & color | semantic foreground/surface/status tokens; body text and line-height contract; contrast ≥4.5:1 for normal text; wrapping/overflow for IDs and user content | token lint, contrast scan, long-content story, dark-mode story, and i18n expansion test |
| Animation | shared duration/easing tokens, causal motion, transform/opacity preference, interruptibility, and `prefers-reduced-motion` behavior | reduced-motion Storybook story and browser assertion that action remains usable during transitions |
| Forms & feedback | visible labels, field-local errors, helper text, async progress, retry/undo or next action, and server error preservation | valid/invalid/loading/success/timeout/permission stories with submit and recovery events |
| Navigation patterns | predictable back/deep links, stable route identity, focus restoration, drawer parity, and one primary action per surface | route matrix, keyboard navigation journey, refresh/deep-link test, and mobile drawer test |
| Charts & data | legends/tooltips or accessible table, empty/loading/error/partial states, textual values, and color-independent meaning | chart stories for every state, keyboard/tooltip test, screen-reader text, and deterministic snapshot/visual evidence |

Each reusable component must have a Storybook story for its meaningful states.
Each interactive story must use a `play` function and user-like queries such as
role or accessible label; `data-testid` is a last resort. Storybook render,
interaction, accessibility, and visual tests are complementary: a passing
render story does not prove keyboard, async, responsive, or data correctness.

The minimum scene/event matrix is:

| Scene | Required event or assertion | Failure prevented |
|---|---|---|
| initial/ready | render, accessible name, primary action | dead or unnamed control |
| loading/pending | click or submit, disabled state, progress/status update | duplicate request and silent wait |
| empty/no-result | filter/search/reset, next-action copy | inert workspace |
| success/recognized | inspect, open, confirm, source/provenance text | unsupported product claim |
| validation/error/timeout | invalid input, server error, retry/recovery | error only in console or lost user work |
| unauthorized/forbidden | attempted action, denial explanation, no sensitive data | privilege disclosure |
| offline/connector unavailable | degraded read path, retry/backoff affordance | false provider success |
| long content/large dataset | wrap, scroll/virtualize, pagination or summary disclosure | layout collapse and browser lock-up |
| keyboard/touch/reduced motion | tab/enter/escape, pointer/touch, reduced-motion media query | inaccessible or motion-sensitive flow |

The inventory must record component, story name, state, event, expected
customer-visible outcome, accessibility rule, token source, viewport, and test
command. A story that only renders a static screenshot is incomplete for a
button, form, navigation, chart, or asynchronous data surface.

### 6.5 Queue convergence rules

1. One active writer owns each overlapping file/authority cluster.
2. A stacked child is not promoted before its parent reaches protected
   `develop` and the child is revalidated on the new exact base.
3. Predecessor-head checks and reviews never transfer.
4. Dependency changes that cross runtime majors are separated from unrelated
   feature work.
5. Historical one-shot, repair, finalizer, and self-modifying workflow identities
   are handled through #1324; do not add another write-capable cleanup workflow.
6. Independent approval remains mandatory; #1371 is resolved by establishing a
   legitimate reviewer path, not by weakening protection.
7. A micro-optimization requires measured evidence or a stable tested complexity
   invariant, not only an assertion that `Map` is faster than array lookup.
8. A PR that claims to close an umbrella issue must prove the full umbrella
   acceptance journey, not one narrow slice.

---

## 7. Buyer-visible Gap matrix

### P0 — Release and integration control

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Release-train convergence | buyers cannot assess an unconverged release train; 102 PRs is the historical 2026-08-25 inventory, not a current count | strict gates exist but queue topology is fragmented | #1428, #1371, #1324 | classify every current PR; preserve each valid delta through protected merge or independently verified complete successor transfer; retain predecessor links and deletion rationale; parent-first integration; one immutable RC SHA. A duplicate label alone never authorizes closure |
| Product/release truth | documentation conflicts with protected behavior/version | retry is shipped; release doc says `v0.1.0`; version is `0.14.4` | #1392, this PR | README, architecture, version, changelog, release manifest, and operator guide agree |
| Independent review path | automation cannot lawfully self-approve | effective rulesets require independent post-last-push approval | #1371 | verified reviewer route and normal protected merge without bypass |

### P0 — Connector and provider action

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Installable connector | adapters in source are not an operable product | outbound-only architecture and several adapters exist | #998 | signed packages/OCI, enrollment, rotation, upgrade/rollback, supported matrix |
| Source lifecycle | configuration does not equal observed provider capability | source IDs, eligibility, consent, and revisions exist in slices | #998, #978 | create/rotate/disable/delete, capability discovery, health, stale-capability invalidation |
| Durable reconciliation | retry exhaustion alone does not tell the buyer what happened remotely | retry/backoff/exhaustion and signal events exist | #998 | idempotent command, late-success reconciliation, dead-letter action, buyer receipt |
| Shared send safety | process-local throttles fail with multiple replicas | Proposed rolling PostgreSQL quota; current local concurrency/expiry/isolation/cancellation evidence above | #1379, #1417 | exact-head hosted checks, independent review, foundation-first protected integration and delivery/load evidence |

### P0 — Data durability, portability, and customer exit

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Binary object lifecycle | large/deferred document bytes cannot remain an inline database strategy | S3-compatible implementation is Draft | #1076, #1364 | upload/read/recognize/retain/delete/backfill/orphan round trip with real integration |
| Disaster recovery | a release is not enterprise-ready without restore evidence | Ready PR #1464 at `2ce32a89fbef0719f13cbab712aab5e843aa6432` adds WAL archive and same-volume retargeted PITR. The current repair force-recreates both restore containers before the existing applied/requested-target stamp comparison, removing stale Compose environment reuse. Bash, ShellCheck, Compose rendering, and diff checks pass; two review threads are resolved. An exact-commit archive run inside Colima completed both recovery targets: first-target marker inclusion/exclusion, post-promotion write, same-volume earlier retarget, exclusion of all later rows, and full stack/volume cleanup all passed | #1428, #1464 | terminal exact-head hosted checks and independent review, failover fencing, backup retention and scheduled clean-restore rehearsal |
| Tenant export/reimport | customers need exit and migration without losing provenance | Draft #1497's bounded project-evidence slice passes 345 tests after actual fresh/repeat migration, including full-size cited content, retained identity rollback, and incompatible concurrent imports; full tenant/mailbox/binary/provider/audit portability and signed browser restore remain unverified | #1428, #1497 | export → clean instance import preserving source, opaque IDs, history, evidence, policy |
| Retention/legal hold/disposition | deletion and evidence preservation conflict unless modeled | partial security/key/retention work exists across repository history | #1428, #1364 | purpose-scoped retention, legal hold, verified disposition, object/DB reconciliation |
| Attachment parser admission and unsupported formats | a file above 20 MiB can pass import transport but fail later at a hidden parser limit; one failed transaction also aborted subsequent files | Draft #1469 proposes 64 MiB retention and preserves real-PDF bytes/identity after size rejection and rollback; the separate 20 MiB guard rejects before network. This is source/local-test evidence, not a released 64 MiB capability; unsupported formats remain metadata-only | #1427, #1469, #1353, #1419; NewsDOM #665; Proposed ADR-0021/0023 | protect and release the canonical provider contract, pin it, verify real 64 MiB recognition and signed upload/retry, measure concurrent capacity and p95, and complete object-backed lifecycle before increasing the bound again |

### P0 — Evidence-based AI and document intelligence

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Canonical evidence identity | OCR/media/attachment/model slices can disagree about the same source | source segments and several deterministic admission slices exist | #1350, #1353, #1397, #1419 | one source identity/provenance chain across email, thread, document, attachment, media, model result |
| Judgment explanation | model output without evidence/calibration is not defensible | grounded extractor seam exists; wider evidence pipeline incomplete | #1350 | evidence IDs, claim support, abstention, correction, verifier result, prompt/model/version receipt |
| Confidence unit integrity | adjacent values can appear as 100% and 2% when a client guesses whether a score is a ratio or percentage | backend extraction contract is 0--100; protected frontend still guesses the unit at runtime | #1436, #1559 | one explicit unit at the API boundary, current-head UI tests for low/high values, independent review, and protected merge evidence |
| Provider-neutral route | raw provider coupling spreads credentials and failure behavior | contextual-orchestrator boundary exists; EgressWeave integration is blocked on release | #1262, #1264 | released hash-locked adapter, route/fallback evidence, no raw secret in products |
| Noema workspace-agent boundary | buyers cannot rely on an assistant that bypasses governed routing or imports unreleased owner code | Noema protected `main` owns governed GitHub capability and delegates model routing; no released shared runtime is proven | #1384, #1486, #1527, Noema #536, Contextual Orchestrator #1004, ADR-0006 | tenant/workspace-authorized released orchestrator contract, distinct-candidate structured-output recovery, no direct-provider fallback, fail closed when the released `contextual-orchestrator` contract is unavailable, Naruon-owned domain tools, immutable owner release, and consumer conformance tests |
| Scientific claim discipline | keyword labels can be mistaken for topic/event measurement | architecture explicitly says no live STM | TEPP dependency path | accepted immutable TEPP artifact/API or explicit feature absence; no lexical-as-STM claim |

### P1 — Typed context and scheduling differentiation

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Responsive shell hydration and unavailable state | a buyer can see a polished navigation shell but no actionable content when a data request is unavailable, and hydration drift can produce inconsistent controls | Draft PR #1570 at `a48e8ba85b6d3a4ceb78e110582b3d5bc76d0d7c` stops converting mail, pending-reply, task, calendar-source, and project-folder failures into false zero states; all five sources settle independently, every authorization failure routes to login recovery instead of generic retry, and malformed successful payloads fail closed. Thirty-eight related tests, TypeScript, ESLint, and diff checks pass. This is local Proposed evidence, not a hosted or deployed result | #1485, #1570; keep predecessor open until full-delta succession is independently proven | current-head hosted checks and review, deterministic server/client markup, backend-backed desktop/mobile Playwright screenshots for loading/partial-error/auth/retry-success, and no hydration warnings |
| Stacked PR current-head review dispatch | a dependent PR can show successful metadata without enforced central review and security checks on its non-default base | central #1644 at `82ef13ac35e4046e2eafba68bd1650ffc32b3470` audits ruleset 21732164 in evaluate mode with only OpenCode; its mutation manifest covers 17921150 and 18156473, not the stacked ruleset. Historical #1448 dispatch/merge is not proof of current stack coverage | ContextualWisdomLab/.github #1644; [exact-head owner audit](https://github.com/ContextualWisdomLab/.github/pull/1644#issuecomment-5560607081) | separately reviewed workflow-only enforcement scope and authorized owner administration path; every supported stack base receives current-head/base required review and security evidence; verify live enforcement and protected merge. Do not broaden mixed default-branch protection or reduce approval requirements to obtain coverage |
| Typed Person/Event/Commitment graph | generic string graph cannot safely drive high-stakes action | planning spec marks types as new/planned | #977, #978, #1000 | normalized temporal/multi-membership identities, evidence/confidence/correction on every inferred edge |
| Status-weighted scheduling | calendar CRUD does not prevent harmful double booking | CalDAV source/writeback/retry foundation exists | #978, #988, #989, #990, #1416 | confirmed/tentative/desired + organizer/attendee + recurrence/free-busy/resource end-to-end |
| Minimal-disclosure bridge | personal context can influence work availability without exposing private reason | policy substrate exists; product bridge is planned | #979, #991 | consented consequence-only propagation, revocation, audit, regression tests |
| Correct-by-exception inference | asking users to reconstruct context defeats the product mission | extractor/search foundations exist; dense-KG resolution remains incomplete | #977, #992, #1001 | one recommendation, evidence/calibration, hold/override, correction learning, no silent irreversible action |

### P1 — Platform and ecosystem

| Gap | Buyer problem | Protected/current evidence | Existing work | Completion evidence |
|---|---|---|---|---|
| Plugin lifecycle | internal extension seams do not create an enterprise platform | extractor/parser seams exist; durable custom tool mutation fails closed | #976, #1300 | signed manifest/release, tenant grant, sandbox, compatibility, upgrade/rollback/uninstall |
| Stable cross-repository contracts | copying sibling code creates a distributed monolith | several adapters are planned or dependency-blocked | #976, #1262, #1350 | released SDK/API/event/OCI contracts pinned by version/digest; no direct sibling SQL |
| Buyer administration | operators need source, connector, policy, health, retention, and support controls | settings/security surfaces exist but not one completed admin lifecycle | #998, #1428 | role-specific admin console with next-action explanations and audited high-risk changes |

---

## 8. GA-1 product definition

GA-1 is complete only when a buyer can perform the following journey on one
released, immutable product version:

```text
install or access Naruon
→ authenticate through the supported enterprise identity boundary
→ install and enroll a signed outbound connector
→ register customer-owned mail/calendar/contact/file sources
→ verify observed source capabilities and health
→ synchronize source records with provenance
→ receive a source-cited judgment or action recommendation
→ inspect evidence, confidence, authorization, privacy, and provider impact
→ approve, hold, or correct the recommendation
→ execute an idempotent provider action with current revision protection
→ observe success, retry, conflict, exhaustion, or reconciliation evidence
→ restore, export, or migrate the tenant without losing provenance
```

Naruon is not GA if the demonstration substitutes mocked provider success,
process-local state, local-only credentials, predecessor-head checks, synthetic
review approval, hidden manual database edits, or an unreleased sibling branch.

---

## 9. Delivery sequence

### Wave 0 — Product truth and queue convergence

1. Merge this baseline after exact-head documentation checks and independent
   review.
2. Keep #1428 as the single completion gate.
3. Maintain the complete open-PR inventory (section 13) and classify every PR as it arrives.
4. Resolve #1371 without weakening protection.
5. Merge/close governance and stale-workflow lanes through normal protected
   integration.
6. Correct README/release/version contradictions.

### Wave 1 — GA-1 runtime and operations

1. Finish #998 connector artifact, enrollment, capability, fleet, retry, and
   reconciliation lifecycle.
2. Integrate shared send throttling (#1379/#1417).
3. Finish binary object lifecycle (#1076/#1364).
4. Complete PostgreSQL WAL/PITR/failover/restore evidence.
5. Complete OIDC/SCIM/tenant administration and privacy-safe OpenTelemetry/SLO.
6. Publish independent backend, frontend, connector, and compatibility artifacts.

### Wave 2 — Buyer differentiation

1. Implement typed temporal/multi-membership Person/Event/Commitment graph.
2. Complete status-weighted scheduling (#978/#988/#989/#990).
3. Complete evidence-based mail/document/media resolution (#1350).
4. Add tenant export/reimport and customer-exit evidence.
5. Run the full buyer journey and failure/restore variants.

### Wave 3 — North-star platform

1. Minimal-disclosure privacy bridge (#979/#991).
2. Dense-KG correct-by-exception resolution (#977/#992/#1001).
3. Signed plugin platform (#976) with one real independently released CWL
   plugin.
4. Optional TEPP and other ecosystem adapters through accepted immutable
   contracts.

---

## 10. Release and quality gate

### Product correctness

- real IMAP/SMTP and DAV interoperability fixtures;
- duplicate/replay, late response, partial failure, provider conflict, connector
  restart, network partition, and source-capability-change tests;
- recurrence, timezone, DST, organizer/attendee, free/busy, and resource
  scheduling tests;
- full tenant export/reimport and backup/restore rehearsals;
- buyer-visible provenance completeness and unsupported-claim rate gates;
- no silent confirmed-commitment break;
- no private reason crossing a context boundary without explicit authorized
  disclosure.

### Code and documentation

- production statement coverage 100% for owned production code;
- production branch coverage 100%;
- public API/module/class/function docstrings 100%;
- frontend component, interaction, action-edge, design-token, accessibility, and
  i18n tests;
- no documentation that represents planned behavior as shipped or shipped
  behavior as future work;
- ADR, PRD, TRD, architecture, data model, runbook, and standard traceability
  updated with each release-relevant decision.

### Database

- normalized ownership and provider mappings;
- descriptive two-or-more-word `snake_case` object names;
- no direct cross-service SQL;
- bitemporal/effective-dated facts where provider state, membership, consent,
  policy, or source mapping changes over time;
- tenant enforcement and hot-partition/load evidence;
- clean install, N-1 upgrade, expand/backfill/contract, rollback, and restore.

### Security and supply chain

- OAuth/OIDC threat controls aligned with the current OAuth 2.0 Security BCP;
- signed connector and release artifacts;
- digest-pinned OCI images;
- SPDX 3.0.1 SBOM;
- SLSA 1.2 provenance;
- dependency/license/vulnerability evidence;
- secret, prompt, message, event, contact, and file-content exclusion from
  ordinary telemetry;
- no mutable VCS dependency in production;
- no self-modifying or broad-token workflow used to compensate for product code.

### Operations

- liveness, startup, readiness, and drain semantics per independently deployable
  component;
- OpenTelemetry trace, metric, and log acceptance;
- low-cardinality label contract;
- SLO, error budget, burn-rate alert, dashboard, on-call, incident, and support
  bundle;
- connector offline/backpressure and safe rolling upgrade;
- backup/PITR/failover/restore and customer-exit runbooks;
- versioned support, deprecation, compatibility, and security-fix policy.

### Protected integration

- one exact current head and one exact protected base;
- all live required contexts terminal-success;
- zero actionable unresolved review threads;
- qualifying independent non-author post-last-push approval;
- no bypass, self-approval, force push, dummy commit, empty requeue, or stale
  predecessor evidence;
- immutable release source SHA and artifact digests recorded in release evidence.

---

## 11. Issues established or strengthened by this baseline

| Issue | Purpose |
|---:|---|
| [#1428](https://github.com/ContextualWisdomLab/naruon/issues/1428) | new umbrella: GA scope, release train, and buyer-visible acceptance |
| [#976](https://github.com/ContextualWisdomLab/naruon/issues/976) | strengthened: signed plugin SDK, registry, permissions, compatibility, sandbox, lifecycle |
| [#978](https://github.com/ContextualWisdomLab/naruon/issues/978) | strengthened: typed Event/Commitment model, iTIP/CalDAV scheduling, free/busy/resource, conflict and privacy contract |
| [#998](https://github.com/ContextualWisdomLab/naruon/issues/998) | strengthened: installable connector, enrollment/identity, protocol capability, reconciliation, OpenTelemetry/SLO |

Existing linked implementation and blocker issues remain authoritative for their
bounded scopes, including #1022, #1076, #1229, #1262, #1324, #1350, #1371, and
PR #1379.

---

## 12. Standards and research traceability

The following standards are not decorative references. They define protocol,
security, accessibility, observability, or supply-chain acceptance tests in the
issues above.

For the DiskSage boundary specifically, PROV-O supplies the provenance
relations, DCAT supplies catalog/dataset/service discovery terms, OpenLineage
supplies run and facet vocabulary, and NIST SP 800-209 supplies storage
protection and recovery controls. The implementation must keep these as
metadata relationships and receipts; a provider upload or local path alone is
not an eviction or lineage claim.

### APA 7th references

Anomaly. (2026). *Providers: Custom provider*. OpenCode.
https://opencode.ai/docs/providers

Crispin, M. (2003). *Internet Message Access Protocol—Version 4rev1* (RFC
3501). RFC Editor. https://doi.org/10.17487/RFC3501

Daboo, C. (2010). *iCalendar transport-independent interoperability protocol
(iTIP)* (RFC 5546). RFC Editor. https://doi.org/10.17487/RFC5546

Daboo, C. (2011). *vCard extensions to WebDAV (CardDAV)* (RFC 6352). RFC
Editor. https://doi.org/10.17487/RFC6352

Daboo, C., Desruisseaux, B., & Dusseault, L. M. (2007). *Calendaring extensions
to WebDAV (CalDAV)* (RFC 4791). RFC Editor. https://doi.org/10.17487/RFC4791

Daboo, C., & Desruisseaux, B. (2012). *Scheduling extensions to CalDAV* (RFC
6638). RFC Editor. https://doi.org/10.17487/RFC6638

Daboo, C., & Quillaud, A. (2012). *Collection synchronization for Web
Distributed Authoring and Versioning (WebDAV)* (RFC 6578). RFC Editor.
https://doi.org/10.17487/RFC6578

Gellens, R., & Klensin, J. (2011). *Message submission for mail* (RFC 6409).
RFC Editor. https://doi.org/10.17487/RFC6409

Jenkins, N., & Newman, C. (2019). *The JSON Meta Application Protocol (JMAP)
for Mail* (RFC 8621). RFC Editor. https://doi.org/10.17487/RFC8621

Lodderstedt, T., Bradley, J., Labunets, A., & Fett, D. (2025). *Best current
practice for OAuth 2.0 security* (BCP 240; RFC 9700). RFC Editor.
https://doi.org/10.17487/RFC9700

Melnikov, A., & Leiba, B. (2021). *Internet Message Access Protocol (IMAP)
version 4rev2* (RFC 9051). RFC Editor. https://doi.org/10.17487/RFC9051

OpenSSF. (2025). *Supply-chain Levels for Software Artifacts specification,
version 1.2*. https://slsa.dev/spec/v1.2/

OpenTelemetry Authors. (2026). *OpenTelemetry specification, version 1.60.0*.
https://opentelemetry.io/docs/specs/otel/

WHATWG. (2026). *Fetch standard: HTTP-redirect fetch*.
https://fetch.spec.whatwg.org/#http-redirect-fetch

Elkady, H. (2026). *Anti-Slop UI: A Deterministic State-Machine Architecture
for Eliminating Design Hallucinations in LLM-Generated Interfaces*. Local Over.
https://local-over.github.io/Anti-Slop-UI/research_paper.pdf

NextLevelBuilder. (2026). *UI/UX Pro Max skill* (Version 2.5.0) [Computer
software]. GitHub. https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

Storybook. (n.d.). *Accessibility testing*. Retrieved August 21, 2026, from
https://storybook.js.org/docs/writing-tests/accessibility-testing

Storybook. (n.d.). *Interaction tests*. Retrieved August 21, 2026, from
https://storybook.js.org/docs/writing-tests/interaction-testing

SPDX Workgroup. (2024). *SPDX specification, version 3.0.1*.
https://spdx.github.io/spdx-spec/

World Wide Web Consortium. (2024). *Web Content Accessibility Guidelines
(WCAG) 2.2*. https://www.w3.org/TR/WCAG22/

National Institute of Standards and Technology. (2020). *Security guidelines
for storage infrastructure* (NIST Special Publication 800-209).
https://doi.org/10.6028/NIST.SP.800-209

OpenLineage. (n.d.). *OpenLineage documentation: Object model, run cycle, and
facets*. Retrieved August 25, 2026, from https://openlineage.io/docs/

World Wide Web Consortium. (2013). *PROV-O: The PROV ontology*.
https://www.w3.org/TR/prov-o/

World Wide Web Consortium. (2024). *Data Catalog Vocabulary (DCAT) — Version
3*. https://www.w3.org/TR/vocab-dcat-3/

---

## 13. Live open-PR identity inventory

This table was generated from a live GitHub pull-request collection whose
response was captured at `2026-08-25T00:26:45Z`. It records every currently open Naruon
PR's immutable head,
base, draft state, authority cluster, stack parent reference, and provisional
disposition. Review decisions, unresolved threads, mergeability, and Checks are
volatile and must be fetched again for the exact head immediately before any
merge; GraphQL rate-limit failures are not treated as approval or success.

The 102-row inventory is a fresh refresh later than baseline v0.2's 93-row
snapshot captured at `2026-08-21T19:25:43Z`: PR #1337 merged into protected
`develop` at `2026-08-25T00:10:39Z` and PRs #1449–#1463 opened since that
observation. The v0.2 93-row snapshot, the earlier 92-row snapshot taken
after PR #1442 merged, and their exact-head observations remain historical
and are retained in baseline v0.2 and in git history for audit
traceability. The self-row reflects the head observed at scan time and may
trail this document's own commit; all review decisions, Checks, and
mergeability still require a live exact-head fetch before merge.
Base-SHA columns record the protected-branch tip each row was scanned
against (`develop@81c10564...` for rows captured before PR #1337
merged; `develop@e5e99b4e...` for rows captured after). A few older rows
retain `develop@dd8d1519...` from an earlier scan window; that value is also
historical scan provenance, not a second claim about the current protected
branch. These values are therefore not one shared base declaration.

| PR | Title | Exact head SHA | Base ref and SHA | Draft | Authority cluster | Stack parent ref | Disposition | Next action |
|---:|---|---|---|:---:|---|---|---|---|
| 1463 | 🎨 Palette: 비동기 작업 버튼의 로딩 상태 시각적 피드백 개선 | d0f51274dc86271e365aa1384e1362daf93f1d7d | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1462 | feat: 신규 유틸리티 도구 3종 추가 (URL 인코더, URL 디코더, 해시 생성기) | dba144b01be8a7e332c9fc7b390e1d9b105536c4 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1461 | chore(deps): bump the ci-python group across 1 directory with 86 updates | f012853e6123017c290a7782cc7cf8e4801e4bb7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1460 | chore(deps): bump the backend-python group across 1 directory with 64 updates | dec4329986b261607204c0711d62f3bcd782d181 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1459 | chore(deps): bump the frontend-npm group across 1 directory with 14 updates | 3edb8320b0288f2bba54ce7e28083164e0d51966 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1458 | chore(deps): bump the github-actions group across 1 directory with 3 updates | f7099f951574a01f1333cb72a5e48ac91e7f4ea5 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1457 | chore(deps): bump the docker-base-images group across 1 directory with 2 updates | 245c8f1d2177e451e9812525ef6bbd7db9be3e6e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1456 | 🎨 Palette: 이메일 상세 화면 UX 밀도 개선 | 20b1c7f4798343d6949ab57ee9ab015d928b04bf | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1455 | 🛡️ Sentinel: [HIGH] 첨부 파일 파서의 경로 탐색 취약점 수정 | 40c5b7087a92a23eba787682fe32604861a9474b | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1454 | ⚡ Bolt: Optimize NetworkGraph edge description lookups to strictly O(1) | 9cb7883cd0a41b9634f4f74e77f3595d754ab7e7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1453 | 🎨 Palette: SettingsLayout 비활성화 버튼 접근성 툴팁 개선 | eef7e8d2eb25199afeb13c6b8a24f0f73bbd0fe5 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1452 | 🎨 Palette: 비활성화 버튼 접근성(Tooltip) 개선 추가 | ad32c8d35c11a76f52e189d7a5e83fb74fb603df | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1451 | feat: 텍스트 유틸리티 도구 추가 및 테스트 보완 | a2a20e3eb14bb65fab8ee2f2f9199dd76dd71bce | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1450 | chore: remove stray scratch/debug files committed to develop | 7d1f57a83a34312bea265ae3095bc67ff4e0493e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1449 | 🎨 Palette: 데이터 저장소 버튼 액션 로딩 UX 및 접근성 개선 | 63318d97c9feddba57fa962182ad3ca79da5a9da | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | frontend/a11y | — | repaired-root | latest comment-triggered acknowledgement is tree-identical and was fast-forwarded; 443 frontend tests, TypeScript, and diff checks pass; await exact-head review/Checks, then protected-merge |
| 1448 | test(governance): exercise multiline CodeRabbit pending notice | 874c098548e6794217393e0338074ba2f292d080 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1443 | fix: ignore CodeRabbit approval pending notices | 41e48413cffefa8a5393d6af1d5ad16be3c5de7c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1441 | 🎨 Palette: [UX 개선] 메일 상세 고밀도 컴포넌트 추가 | ce6ff8f26e4cfdc76be7d667c7b159c57f8e0ac5 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1439 | ⚡ Bolt: 프론트엔드 O(N) Array.find() 룩업을 O(1) Map 룩업으로 성능 개선 | 68106d13175d7ff67978de66e31d385237ca53b1 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1438 | fix(governance): supersede stale review decisions safely | 899493fae44a50648faa0ecaa6e7095b94037833 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | security/governance | — | repaired-root | non-force restack preserves the six-file governance delta; shell contract and diff checks pass; await fresh exact-head review/Checks, then protected-merge |
| 1436 | feat(frontend): add Storybook UI inventory | becc4e9e56bb30e511e812e8c66b19d094b28de0 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1434 | fix: accept DiskSage cloud-readiness schema 7 | 85e3eb43f9a7c3e87848df1307549d4efd3d29de | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1433 | fix(security): reject ambiguous Message-ID whitespace | 9c89a35e37f46a977d879dbec94fb3673870c0ce | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | security/governance | — | normal-or-stacked-root | non-force restacked; 136 passed, 1 skipped plus Ruff/diff checks; fresh exact-head checks/review pending |
| 1432 | fix(compose): harden optional pg-llm-batch database | e3dbed9a0d4e08348f94d26de09a2fabbdcfa96b | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | llm/orchestration | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1431 | test(core): cover operator env path resolution | e058f8c6e50256194d19be617f8df54f60bd1c27 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1430 | 🎨 Palette: 키보드 내비게이션을 위한 focus-visible 스타일 추가 | 49fc3eabd8e94a95dee2af3c1254c4d46a294399 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1429 | docs: establish Naruon product completion gap baseline | 5a72475506e8ec76692abfa233f3205c645568eb | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | docs/product | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1427 | fix(data): align PDF DOM upload budget with sidecar | ecf023ce3ad4efd804dd373834883a1e9632c391 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | yes | ingest/storage | newsdom-api#682 | owner-first/draft | pinned NewsDOM SHA still enforces 20 MiB; ADR lowered to Proposed/BLOCKED-UPSTREAM; 42 passed, 2 skipped plus Ruff/diff checks; merge owner release, then exact-pin and revalidate |
| 1426 | fix(governance): wait on stale aggregate review state | 5cc148e1f2f84d1afcd2d3cf3dabaade616c01d0 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1424 | ⚡ Bolt: [성능 개선] 네트워크 그래프에서 O(N) 노드 라벨 조회를 O(1) Map 조회로 대체 | 32c7edc11fd6faf8ae6918dae8b00de7c5c0b773 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1421 | 🎨 [UX] 설정 화면 장식용 아이콘에 aria-hidden 추가 | 719c1b347aae52e77ae7e40b0eb60769fd7178cb | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1420 | feat: URL 코덱 및 엄격한 JSON 포매터 추가 | bf7b741ea0b73a146ce9bcd323ca621c1562cb4e | develop@dd8d15191338b841f9e6f3a06507c6a5643b95d0 | yes | other | — | experimental/draft | validate parent and promote only after scope proof |
| 1419 | feat(attachments): index common image metadata | a0f5e03107e6ec3e85eea029bb11c8c8e784b907 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1418 | feat(tools): add auditable URL and contact hygiene | 19adb3e74c66837c5fb2d0a11a7ac030bbbfe3c4 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1417 | fix(email): enforce shared send throttling | 5a22a26ea370c15f8255f1e13c387a92bdcab68a | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | yes | mail/calendar | — | normal-or-stacked-root | reduced to five-file rolling-window slice; removed unused bucket schema and unrelated ancestry; 85 passed, 2 skipped plus Ruff/diff checks and real PostgreSQL advisory-lock smoke; exact-head checks/review pending |
| 1416 | fix(calendar): allow provider-backed create writeback | e4bf31e5725841e72946661ed11f11244c715787 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | mail/calendar | — | normal-or-stacked-root | non-force restacked; create executes without If-Match while update still requires ETag/If-Match; 49 passed, 1 skipped plus Ruff/diff checks; fresh exact-head checks/review pending |
| 1415 | fix(auth): select OIDC signing key by kid | e0a1f166221790e7ba4f0df37b328ac3cb896092 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1414 | fix(governance): refresh gate after OpenCode review | 8fa5cf95c93b152450311a23e172cdbe13b68a94 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | security/governance | local gate PASS; 36 governance tests passed; actionlint clean; hosted checks queued | normal-or-stacked-root | await exact-head checks and current-head review, then protected-merge |
| 1412 | ⚡ Bolt: [성능 개선] tools 배열 탐색을 Map 기반 O(1)로 변경 | b5032d7fb428189da86c10221d58d093d3abcc6e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1411 | 🎨 Palette: 검색어 지우기 ARIA 라벨 통일 | 9b52c7dac0d594210d28e1b7d732e454dbb68d9e | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | frontend/a11y | — | repaired-root | non-force restack preserves the eight-file localized clear-button label delta; 437 frontend tests, TypeScript, ESLint, and diff checks pass; await fresh exact-head review/Checks, then protected-merge |
| 1410 | 🎨 [OIDC 로그인/로그아웃 버튼 로딩 상태 및 접근성 개선] | fac7a5377bd7c5bc7bde89a6f0f05b3fd2c47632 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1408 | fix(a11y): expose keyboard focus on AI Hub tabs | cda57c26e75788eaa350d0faeb898349818da074 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1407 | feat(mail): fail-closed Inkspan edit handoff for recognized HWPX | 730ac3798d7dac8990db1b4daf15f3ab0b3dd2d5 | cursor/mail-hwpx-attachment-preview-7b5e@1ff9fc7a1d590652aa5308262518b8b60e0cebd1 | no | ingest/storage | cursor/mail-hwpx-attachment-preview-7b5e | repaired-stack | 16-file handoff delta inherits the source-backed mail preview and TestClient foundation; 18 backend tests pass with one environment skip, 453 frontend tests, TypeScript, ESLint, Ruff, and diff checks pass; await fresh exact-head review/Checks |
| 1406 | feat(mail): open recognized HWPX text from email attachments | 1ff9fc7a1d590652aa5308262518b8b60e0cebd1 | cursor/hwpx-recognized-text-preview-b246@1a1e4b3d622ab96a0866b6380d309708b30c1c51 | no | ingest/storage | cursor/hwpx-recognized-text-preview-b246 | repaired-stack | 11-file mail-preview delta inherits the source-backed preview and TestClient foundation; 14 backend tests pass with two environment skips, 448 frontend tests, TypeScript, ESLint, Ruff, and diff checks pass; await fresh exact-head review/Checks |
| 1404 | feat(data): show recognized HWPX paragraph text in attachment preview | 1a1e4b3d622ab96a0866b6380d309708b30c1c51 | feat/hwpx-section-text-recognition@1c3943a9e11b6dd1d5a202765cfa52fa1e4f4ea7 | no | security/governance | feat/hwpx-section-text-recognition | repaired-stack | 13-file preview delta inherits the canonical TestClient dependency; 84 backend tests pass with one environment skip, 442 frontend tests, TypeScript, ESLint, Ruff, and diff checks pass; await fresh exact-head review/Checks |
| 1403 | fix(oidc): fail closed on malformed token-endpoint escapes | 9cc3272fe8f3d97d20ace9ac72e8774a1dd9ffd0 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | security/governance | — | normal-or-stacked-root | stale-base reversals removed; 13 focused tests, TypeScript and ESLint pass; await fresh exact-head checks/review |
| 1402 | feat(email-writing): add independent criterion Judge | 3d6b3341c5dd15512d5d60cd5f8d95a1bbc6d846 | feat/llm-email-writing-candidate-task6@fa844bd035ab1f188a28c58e0ed2dc45fa31d0f3 | yes | mail/calendar | feat/llm-email-writing-candidate-task6 | experimental/draft | validate parent and promote only after scope proof |
| 1401 | ⚡ Bolt: ProjectsLayout 인라인 배열 맵핑 렌더링 최적화 | 1221fc848a086db721ef1dde0a26eb6af77fe035 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | performance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1400 | feat(email): Slice 3 buyer-visible withheld-media next actions | db7ca961de800a514cf9bee34d324f1c5cf233bb | cursor/email-media-quarantine-persist-0ad6@ff1dc18cd9de5e06649ac516b163af2db4bbde83 | yes | ingest/storage | cursor/email-media-quarantine-persist-0ad6 | experimental/draft | validate parent and promote only after scope proof |
| 1399 | feat(email): Slice 3 persist quarantined inline media | ff1dc18cd9de5e06649ac516b163af2db4bbde83 | cursor/email-media-admission-wiring-cd1a@1af546dbb01964e9a620ed341ae0dd3dab9439fd | yes | ingest/storage | cursor/email-media-admission-wiring-cd1a | experimental/draft | validate parent and promote only after scope proof |
| 1398 | feat(email): Slice 3 wire admission so only document_image continues | 1af546dbb01964e9a620ed341ae0dd3dab9439fd | cursor/email-media-admission-slice3-c9de@5a80583bcabc22609e8677864ae86f867d85fd45 | yes | ingest/storage | cursor/email-media-admission-slice3-c9de | experimental/draft | validate parent and promote only after scope proof |
| 1397 | feat(email): Slice 3 inline-media admission and tracking-pixel classification | 5a80583bcabc22609e8677864ae86f867d85fd45 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1392 | docs: make README customer and operator focused | c0ac8c01d58473680b89a225107366fec4fae986 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | docs/product | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1387 | fix(a11y): keep unavailable calendar actions discoverable | 37917799e8d27c07e29eeed87a52d5be41528330 | develop@dd8d15191338b841f9e6f3a06507c6a5643b95d0 | yes | frontend/a11y | — | experimental/draft | validate parent and promote only after scope proof |
| 1384 | feat(noema): route LLM through contextual-orchestrator | 0fd330137cdd19068fa8903dc70e1dc88f42cdc9 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | llm/orchestration | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1380 | fix(dav): land capability honesty with tomllib CI import | 658f69accc627b99e379835593c2b9e49b514d00 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1376 | fix(email): expose header-derived media pixel dimensions | aae34d0a9e7d607070bc98e7b0d03e17f607dd6c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1375 | feat(email-writing): parse contextual review candidates | fa844bd035ab1f188a28c58e0ed2dc45fa31d0f3 | feat/llm-email-writing-orchestrator-task5@9cd9b953a2dd236aebe1fcdc25e59ba3e9388505 | yes | security/governance | feat/llm-email-writing-orchestrator-task5 | experimental/draft | validate parent and promote only after scope proof |
| 1373 | feat(hwpx): recognize ordered section text with provenance | 1c3943a9e11b6dd1d5a202765cfa52fa1e4f4ea7 | feat/hwp-hwpx-attachment-recognition@3ab3f6e48bc30c22376a366a763fd20d84cd65ba | no | ingest/storage | feat/hwp-hwpx-attachment-recognition | repaired-stack | parent-relative integration keeps strict OPF spine order, HWP conversion pending, HWPX-specific outcomes, provenance, and the canonical TestClient dependency; 107 related tests plus focused 37-test dependency rerun, Ruff, and diff checks pass; await fresh exact-head review/Checks |
| 1370 | feat(supply-chain): verify locked hashes against PyPI releases | a1f89ebbf82acc83089c821f67c81258665c3e9b | feat/dependency-lock-provenance-receipt@f6eeb69f561e94cd50ae38fb1f43faa6cd2c52d7 | no | security/governance | feat/dependency-lock-provenance-receipt | stacked-child-merged-into-parent | merge commit cd7241798e347ee4b14a2b9812dd69eb719a1b58 is an ancestor of #1369 current head; verify through parent landing |
| 1369 | feat(supply-chain): attest Python lock provenance before install | 40a2845fcf2799c873a94c9a9320cbc4e38e8c14 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | yes | security/governance | — | combined-owner-root | non-force restacked; 51 tests, Ruff, actionlint, diff check, and both five-lock live receipts pass with zero violations; exact-head Checks/review queued |
| 1368 | ⚡ Bolt: [성능 개선] EmailDetail 개별 메시지 컴포넌트 메모이제이션 | 5c2f048c0e9fc97545e1d6f09d1379b3ae8f8b68 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1366 | fix(threading): honor RFC 5256 References ancestry | be0237714e373052b57d73e1168087da3adfda34 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1365 | fix(containers): publish explicit split runtime targets | 43666bed6214ce724d4dc50810d9f65f3d77d3f3 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1364 | feat(storage): add scoped S3 document object backend | 3a3baa6b8dc9ea224f46395cb78c91a45be2090c | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1363 | fix(governance): audit orphaned Actions workflow identities | 48593a1cab22cca86e2dbfb7e6d5cb89cf298f3c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1361 | feat(tools): add bounded content checksum generator | 5859a8f3f5e9dddf20a43313b53d7aa6453f8cd7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1356 | feat(email-writing): add hardened contextual-orchestrator boundary | 9cd9b953a2dd236aebe1fcdc25e59ba3e9388505 | feat/llm-email-writing-context-task4@4570747ccebd57ccaab30ffc68239f0c9d2f1ca0 | yes | mail/calendar | feat/llm-email-writing-context-task4 | experimental/draft | validate parent and promote only after scope proof |
| 1355 | fix(email): preserve deterministic descending thread order | 4b508b843d0d7efa02e71b4d2f069ffa8d556877 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | mail/calendar | — | normal-or-stacked-root | current protected base merged normally; 38 reply-order/tracking/SLA tests and Ruff pass; await fresh exact-head Checks and independent review |
| 1354 | feat(ui): add Storybook design-token contract | 84edbbf152d257cd05777bf0b007fcfec2ac1d18 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1353 | feat(attachments): recognize HWP and HWPX parser boundaries | 3ab3f6e48bc30c22376a366a763fd20d84cd65ba | codex/starlette-testclient-dependency@52dfc863d1a5d6e4e80b6366f719dd09f2aa6172 | no | ingest/storage | codex/starlette-testclient-dependency | repaired-stack | non-force restack preserves HWP/HWPX bounds, filename traversal defense, the 64 MiB import contract, and canonical `httpx2`; 64 parser/dependency tests, Ruff, and diff checks pass; await parent merge and fresh exact-head review/Checks |
| 1352 | fix(a11y): expose async button busy states | 8b7731da7063c39651aa9e3debfaa2052c476c35 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1349 | docs(product): define evidence-based workspace task contract | 559d091a9a75d8e79ab9608c04931c5a1e82e173 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | docs/product | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1347 | fix(governance): reject rate-limited review status as semantic evidence | cd973fc364efb8d150786f4c2bceec54187eb806 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1345 | fix(dav): reject ambiguous nested authorization encodings | 8146c56587acea5c4aa859ba9366eef0f39540d7 | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | security/governance | 82 focused tests + Ruff pass; information-only threads resolved; prior Strix provider failure is not clean evidence | normal-or-stacked-root | await fresh exact-head Checks and review, then protected-merge |
| 1339 | fix(host-policy): normalize dotted bracketed IPv6 safely | 7fbfbc81e8fd09e1ab54c85318b54b7e71e35e5e | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | security/governance | — | normal-or-stacked-root | non-force restacked; fixed `::ffff:7f00` mapped-loopback misclassification; 58 related tests plus TypeScript/ESLint/diff checks pass; fresh exact-head checks/review pending |
| 1333 | feat: persist DiskSage file lineage ontology | 017cdef392385571acfc5abc177882724d6026b9 | develop@e5e99b4e3bb081b92c602358878856536030e2ca | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1332 | feat(email): surface calendar writeback If-Match conflicts | d53598dc7e45b470907fd97dffb9d64e954f2731 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1329 | feat(email-writing): build authorized thread context | 4570747ccebd57ccaab30ffc68239f0c9d2f1ca0 | feat/llm-email-writing-review-evidence-task3@51fb5e8543247b1e5c790f3fdf98424c8fbed669 | yes | security/governance | feat/llm-email-writing-review-evidence-task3 | experimental/draft | validate parent and promote only after scope proof |
| 1328 | feat(email-writing): persist privacy-minimized review evidence | 51fb5e8543247b1e5c790f3fdf98424c8fbed669 | feat/llm-email-writing-contracts-task2@fb7c406ee1328a6ac42dbaf54bb6852c199d8b0a | yes | security/governance | feat/llm-email-writing-contracts-task2 | experimental/draft | validate parent and promote only after scope proof |
| 1327 | feat(email-writing): define strict review contracts | fb7c406ee1328a6ac42dbaf54bb6852c199d8b0a | feat/inkspan-email-writing-guide@bfc2df112136bb9fe358778d701e78bf9e78b685 | yes | security/governance | feat/inkspan-email-writing-guide | experimental/draft | validate parent and promote only after scope proof |
| 1322 | docs(adr): design Inkspan-based LLM email writing guidance | d943203afc0afae0c9a6190681675f4d30dcf257 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1321 | fix(auth): require issued-at in Keyverse OIDC sessions | d06eff3875543b1afa28570f9269571a63a81983 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1320 | fix(calendar): expose proposal context to screen readers | 1a9afa0cf845a49db4c2eb2372f9f36eaf4c8c4e | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1317 | feat: harden live macOS runtime and governance | 25d80197ee0eb8cb2aafc7d205ac7b98ccccba0c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1302 | fix(tools): remove canned source-derived tools | a39ba78d05d71f4d45bd7fe029b59f686e8cc2e3 | fix/remove-unsafe-phishing-detector@050ee1588090952c2c9058c4cb596851ee35cad7 | yes | other | fix/remove-unsafe-phishing-detector | validated stack | preserve four-file delta; await #1565 -> #1300 -> #1301 protected merge before fresh review |
| 1301 | fix(tools): remove unsafe phishing detector | 050ee1588090952c2c9058c4cb596851ee35cad7 | fix/fail-closed-tool-mutations@e3485b4dfed763cdcd846c7894dc5c5f69e445e0 | yes | other | fix/fail-closed-tool-mutations | validated stack | preserve four-file delta; await #1565 and #1300 protected merge before fresh review |
| 1300 | fix(tools): fail closed on unsafe global tool mutations | e3485b4dfed763cdcd846c7894dc5c5f69e445e0 | codex/starlette-testclient-dependency@52dfc863d1a5d6e4e80b6366f719dd09f2aa6172 | no | other | codex/starlette-testclient-dependency | validated stack | await fresh exact-head checks/review, then protected-merge after #1565 |
| 1288 | test(email): consolidate thread identity and folder visibility coverage | b7db9a316162a70bf8e594faf4f2e73766d9dc6c | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1287 | 🧪 테스트: runtime_secrets.py의 build_encryption_keyring 누락된 테스트 추가 | 4de4f5d5850baf1abc05203f204c489650ba9624 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1284 | test(pdf): cover pending document decode success | 68da2a53084751361f6332ca4f3fe82c34443964 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | ingest/storage | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1280 | test(search): cover configured fusion settings | 89742939fe8b9a9a33a9018d6863050f5c7a7fc7 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1279 | test(tools): consolidate webhook validation and execution coverage | c6a50e97b7742a7172d80de01159516796d4d1a0 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1277 | test(core): cover connector scope statement | aa04c9392c86c29fd39cae80149fbbd02681cff8 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | other | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1267 | perf(mail): memoize email list element mapping | 8fccadb727ac54a81422642022ccc2b31723bab9 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | mail/calendar | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1264 | integration: route LLM egress through EgressWeave | 124ea7bc7fa4632786f6a22c26196653b04d8c7f | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | no | llm/orchestration | docstring prefix regression repaired; 4 focused tests pass and review thread resolved | normal-or-stacked-root | await fresh exact-head checks and review, then protected-merge |
| 1257 | chore(deps): update connector websockets to 17.0.1 | 4613ff5a1a85e4882af1a3a4abd0e56b3b574187 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | dependency | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1245 | fix(email-detail): make responsive evidence actions functional | 796b34c5a1322f09c6f00b8cf24591ae04b89b6b | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | yes | frontend/a11y | — | experimental/draft | validate parent and promote only after scope proof |
| 1244 | chore(deps): update hash-locked aiohttp to 3.14.3 | c1d4c7fd2b98e464d3ff7e92f26d92a6c0f1e6e8 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1241 | fix(a11y): show keyboard focus on OIDC actions | fb7e63dee1d72365db595edb1bc49e097202e707 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | security/governance | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |
| 1206 | fix(security,api): opaque prompt IDs and CardDAV single-decode | aba2a03f3ca87914fcf1ca1c751b173097852bca | develop@042b0c70531b229af3acbd0421a2f23098d848b3 | yes | security/governance | 61 focused tests + Ruff pass; exact-head approval; unique delta excludes #1345 owner scope | normal-or-stacked-root | after #1345 protected merge, non-force restack and revalidate before Ready |
| 1195 | feat(email): deterministic dedupe provenance — gate strong fingerprints on genuine Date (naruon#1086) | c7aedc6a6a09bc91156e9c62e44f18cf8b4d3846 | develop@81c105645ca6e680f5f8c15ba9c33b67eb63c48b | no | frontend/a11y | — | normal-or-stacked-root | re-fetch exact review/check state, then fix or protected-merge |

The inventory is intentionally identity-first:

It represents the 2026-08-25 102-row refresh described above, which supersedes
the v0.2 post-#1442 93-row snapshot as current evidence while that snapshot
remains historical context: no review body, credential,
customer data, or copied provider payload is stored in this document. A parent
merge or head movement invalidates the affected row and requires regeneration.

### Exact-head check observations

The following failures were also read from the live Checks API during this
snapshot and are retained as RCA pointers, not as reusable merge evidence:

| PR | Exact head | Check/run evidence | Observed cause or disposition |
|---:|---|---|---|
| #1347 | `3f6932026fbef281a373d792518058e4aaf5178f` | Strix run `32440010004`, job `96648648553` | provider/model infrastructure returned NVIDIA NIM 404 and no complete Strix report; rerun after the central fail-closed workflow repair, without weakening the gate |
| #1442 | `94e10a6188a1b96ac162fa659ae4025bc00895bd` | metadata gate `96719432050`; merged `2026-08-21T09:18:28Z` | historical pre-merge observation only; the post-merge 93-row inventory excludes this PR |
| #1443 | `62a0d645b619bcd2eac8f0db87460c5c1990d128` | new parent-head Checks queued; predecessor Strix job `97705801302` | child #1448 merged normally into this stack branch, invalidating all predecessor-head evidence. The prior provider failure was NVIDIA NIM HTTP 429 with unavailable fallback/direct OpenAI 404; current head requires fresh Checks and qualifying approval |
| #1448 | `068aefdfa48122bc73cb85a1dc23614bb09ebc04` → merge `62a0d645b619bcd2eac8f0db87460c5c1990d128` | merge-result Checks queued; Devin passed on PR head | normal stack merge at `2026-08-25T15:31:39Z`; local governance and parent synchronization tests passed. Delayed merge-result Checks are being tracked and are not represented as successful hosted evidence |

Queued or pending Checks are not treated as source failures, and completed
predecessor-head evidence is never reused.

---

## 14. Claim boundary

This baseline is a product and technical decision record, not a certification,
security attestation, market valuation, or claim that Naruon is already GA.

The existence of 100% coverage gates, many PRs, or detailed documentation does
not itself demonstrate commercial completeness. GA is demonstrated only by the
end-to-end buyer journey, current exact-head protected integration, released
artifacts, provider interoperability, recovery/customer-exit evidence, and
operational support contract defined here.
