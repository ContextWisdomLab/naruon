# Async button busy-state accessibility

## Decision

Naruon exposes `aria-busy=true` only while an action control is actively processing its asynchronous operation. The existing `disabled` behavior remains responsible for preventing duplicate activation; `aria-busy` communicates the processing state to the accessibility API rather than replacing the disabled-state contract.

The bounded change applies to the project evidence-review action, repository document actions, and duplicate-thread intent action. It does not claim whole-product accessibility conformance or imply that every statically disabled control is busy.

## Evidence boundary

WAI-ARIA defines `aria-busy` as a state indicating that an element is being modified and that assistive technologies can defer exposing intermediate changes until the operation is complete. The attribute is defined for all elements in the base markup and defaults to `false`. This supports binding `aria-busy` to the same boolean state that represents the in-flight asynchronous action, while leaving ordinary unavailable controls unmarked as busy.

## Verification

Merge readiness is determined only from the unchanged current PR head after repository CI, security, coverage, review, and protected-branch requirements pass. The accessibility attribute itself is not a substitute for rendered assistive-technology testing across supported environments.

## Reference — APA 7th

World Wide Web Consortium. (2026, June 4). *Accessible Rich Internet Applications (WAI-ARIA) 1.3* (Working Draft). https://www.w3.org/TR/2026/WD-wai-aria-1.3-20260604/

## Action identity

A shared loading lock may disable sibling document actions to prevent conflicting writes, but it must not announce every sibling as the operation that is currently processing. Naruon therefore records the initiating document action separately from the shared lock. Only the initiating upload, reparse, embedding-regeneration, HWP-conversion, or WebDAV-materialization button exposes `aria-busy=true`; disabled siblings remain `aria-busy=false`.

The focused server-rendered regression exercises the real button group and fails if a shared boolean again marks every document action busy. Stable `data-document-action` identifiers exist only to bind rendered accessibility evidence to the initiating operation; they do not authorize or execute an action.

## Project review prerequisite versus submission (2026-09-07)

The residual review finding on #1352 at `eb8af38ed00be32bc4e8ec8a2a210faab80d08ea`
was still present in `ProjectsLayout`: `evidenceLoading` describes fetching the
selected evidence, whereas `correctionSubmitting` describes saving its review.
The save button must remain disabled during either operation, but only the
submission changes its busy state and label. The repair changes that one ARIA
binding; it does not change request payloads, authorization, or the shared lock.

`ProjectsLayout.accessibility.test.tsx` now renders the actual component with
independently deferred evidence GET and correction POST responses. It checks
disabled/non-busy before evidence arrives, no premature POST, enabled/non-busy
after evidence arrives, disabled/busy during submission, exactly one POST despite
a repeated click, and enabled/non-busy after success or rejection, including the
failure alert. The existing confirmation and document-action tests remain.

The initial regression failed both new cases at expected `false` versus actual
`true` while fetching evidence. After the one-line repair, an initial combined
run hit the default five-second timeout and a subsequent state assertion failed;
an isolated run also timed out. These failures are retained, and host load is an
observation, not a proven cause. A diagnostic-only 30-second invocation passed
three tests; the repository timeout was not changed. The identical default
invocation then passed all four tests across the two related files (46.67 s).
Focused ESLint with `--max-warnings=0` and `git diff --check` passed.

Run from `frontend`: `corepack pnpm exec vitest run
src/components/ProjectsLayout.accessibility.test.tsx
src/components/data-layout/DocumentRepositoryTab.busy-state.test.tsx`.
This is mocked API/DOM evidence, not browser, screen-reader, full-suite, build,
hosted, or protected-merge acceptance. Those results must be attached to the
final immutable candidate separately before delivery is claimed.

## Unsaved project memo safety repair (2026-09-07)

The separate generic memo editor called `saveProjectEvidence`, which only set
a success message. Its page test and full-product smoke script mistook that
message for persistence. This is distinct from the semantic object's review
correction POST and must not be credited as a working save feature.

The inspected contracts are `backend/api/webdav.py` (folder reads and separately
scoped materialization intents), `backend/api/projects.py` (semantic object
corrections), and `project_registration.apply_project_correction` (candidate
group/object membership). They do not establish a generic folder/backlog memo
and source-selection persistence contract. Reinterpreting the memo as an
arbitrary graph object's summary or replacing its attributes would change the
domain meaning and ownership boundary, so that workaround is not used.

The immediate repair removes the false-success handler, disables the unsupported
save, labels the local preview unsaved, and explains that a refresh loses the
draft. The existing page regression first failed on the enabled save button;
it now checks unavailable saving, no POST and no success message. Smoke evidence
labels distinguish unavailable saving from persistence and no longer claim a
saved memo. This safety repair does not complete the product requirement.

The remaining product Gap requires a Naruon-owned versioned memo/source contract,
stable project identity including non-graph projects, tenant/workspace and source
authorization, audited writes, conflict handling, and reload/readback persistence
with real PostgreSQL and actual-browser evidence. Failed-source readiness and
zero-value metric rendering are separate unresolved findings. Parent `1b465`'s
build and error-screen inspection do not validate this new runtime delta; new-head
full/build/visual evidence remains required before delivery.

## Project source readiness safety repair

Four source requests (folders, tasks, semantic candidates and session) feed the
same project screen. Previously, a rejected request cleared arrays and the
render path converted them into a waiting queue and zero-valued milestones.
The first regression failed for each request: three displayed the fallback as
empty data, while the failed session did not show an error at all.

The screen now renders loading/error states before exposing derived project
metrics, rejects an unavailable session, and retries the same source batch from
an explicit action. A normal empty response still renders the empty workspace.
Tests distinguish pending sources, each failed request followed by recovery,
successful empty data, real component bindings and existing review submission.
The initial API client returns JSON without member validation. The project
ingress now checks folder/task/candidate members, nullable fields, task enums,
finite scores and integer counts before storing the batch. These checks match
`ProjectFolderResponse`, `TicketTaskResponse` and `ProjectCandidateResponse`,
including nullable citation paths and candidate timestamps. This is not a
whole-product schema audit or a server authorization change.
Independent degraded source panels and durable memo persistence remain product
work; no current-head full/build/hosted acceptance is inferred from focused tests.

The first malformed-response regression produced eight failures (invalid top
levels, null members and a non-text candidate title), with the no-claims
anonymous response correctly rejected. The next two-file invocation never ran
test bodies: two fork workers failed to start after 124.84 seconds. That remains
failed evidence, not a product pass or a proven host root cause. The fixed-lock
environment is pnpm 11.5.3 / Vitest 4.1.10; one later diagnostic keeps the same
default timeout and `--maxWorkers=1` without changing repository configuration.
That diagnostic terminated with exit 1 after 111.46 seconds: 18 of 21 tests
passed, two existing positive flows exceeded the default 5000 ms timeout, and
the contradictory session-response regression failed because no error state
was shown. All three existing busy-state tests passed. No worker-start error
occurred in this diagnostic. These results neither prove the cause of the two
timeouts nor complete the required positive-flow evidence; no further blind
rerun or timeout increase was performed. Focused ESLint exited 0 separately.

A contradictory `authenticated: false` response carrying a non-null user claim
is also a required regression. `ApiClient.getServerSessionClaims` ignored that
flag until local commit `e11a8e9754f826f2bcac6da9b820a9d54ea10e37` added an
explicit-true guard at the shared client. The actual `/auth/session` serializer returns anonymous claims
when unauthenticated, so this is malformed-response rejection work, not evidence
of a server issuing an authenticated identity to an anonymous caller. The shared
client repair was coordinated with its owner and kept in a separate two-file
commit. Eight flag regressions first failed. After repair, the API-client suite
passed all 25 tests (including true/network/malformed cases); the combined
working-tree run with pending project-readiness changes passed 46 tests across
three files in 20.37 seconds. Both earlier positive-flow timeout cases passed
in that run, without proving their earlier cause or repairing full-suite failures.
Focused API ESLint and diff checks passed. This is local evidence, not protected
integration, complete system verification, or a backend authorization change.

### Durable memo implementation prerequisites (proposed, not implemented)

`ProjectFolder` in `backend/db/models.py` has an opaque folder UID and user/org
ownership, but no workspace field; its read service filters only user/org.
Graph objects already carry workspace identity, while the fallback task queue
is a UI-derived object. A single unscoped memo key or graph correction cannot
represent all three safely.

First establish authoritative workspace ownership for existing folder records
and a stable, server-resolved project reference. Do not assign historical rows
to the caller's current workspace or infer ownership from a display title.
`_candidate_groups` currently uses a persisted explicit candidate UID when one
exists, otherwise `_synthetic_project_uid` derives an automatic UID from scope
and source identity. Adding an explicit candidate can therefore change the
project UID. A memo contract must preserve identity/alias continuity across that
transition rather than silently creating a different project or orphaning notes.
Then add the product-owned memo resource with a unique scoped project reference,
version number, note and authorized source reference; use a conditional write
against the expected version and record the audit event in the same transaction.
Reads must enforce the same owner/org/workspace boundary. The UI's source-kind
dropdown is not an authorized source identity and needs an actual source selector.
Reopening and refreshing must recover committed content; conflicting writes must
preserve the local draft and expose a reload/resolve action. Real PostgreSQL
scope/conflict/rollback tests and actual-browser save/readback complete the proof.
The disabled-save safety repair is only an intermediate step toward this feature.

## Progress provenance repair after 6abe0743

The next local delta starts at `6abe0743bd4f4747c0def1c76c4d01335fb9640d`.
It remains unpublished until writer coordination and independent diff review.
CodeGraph and direct caller inspection found two invalid denominators:
`semanticProgress` converted candidate ranking score into percent in the sidebar,
overview and relationship panel; `buildProjects` copied the completion ratio and
status of every returned task onto every WebDAV folder. An empty response also
produced a fabricated zero percent. `_candidate_score` in
`backend/services/project_graph/project_registration.py` combines fixed object
weights, confidence and source counts; it does not measure completed work.

The reproducible RED command was
`corepack pnpm exec vitest run --maxWorkers=1 src/app/projects/page.test.tsx`
in the frontend directory with an isolated environment. Session 5415 exited 1:
3 failures and 15 passes in 31.81 seconds. Its rendered output contained folder
50%, candidate 87%, and empty-folder 0%, rather than unavailable progress.
These are unit fixtures only, not customer data or browser evidence.

The repair removes score-derived percentages and represents unsupported folder
and candidate progress as null. Folder status is also unavailable rather than
inherited from unrelated tasks. Only the returned task queue can retain a
completion ratio when its denominator is nonzero; native progress elements
carry the label, value and maximum. Empty, zero-complete, half-complete and
all-complete cases are separate regression cases. Unknown progress is not zero.

The list request is `apiClient.get('/api/tasks')`, not a project-scoped query.
At the baseline, `backend/api/tasks.py:170-198` filters owner and organization,
has no limit/offset, and serializes `result.all()`. It does not filter workspace;
`TicketTask` also lacks a workspace field. Therefore the display must say
**retrieved tasks**, expose completed/returned counts, and never promise all
project or workspace work. Renaming UI copy does not repair this missing data
contract. A canonical, server-authorized project/task relationship and scoped
aggregate with explicit denominator remain necessary. Historical records must
not be assigned to the current workspace without ownership evidence.

The backend ranking heuristic, real project completion contract and persistent
memo identity/readback remain unfinished. Removing misleading metrics is an
intermediate safety repair, not completion of those product requirements.
The previous 6abe desktop/mobile error/retry inspection does not verify the new
normal progress surfaces. No approved working backend/account is available for
that inspection; do not inject browser fixtures or bypass authentication to
manufacture evidence. Local unit success, hosted checks, normal-state visual
inspection, protected merge and deployed behavior remain separate claims.

Final focused GREEN used `corepack pnpm exec vitest run --maxWorkers=1
src/app/projects/page.test.tsx src/components/ProjectsLayout.accessibility.test.tsx`
in the isolated frontend environment. Session 33954 exited 0 with 2 files and
25 tests passing in 20.07 seconds. This includes the revised retrieved-count
wording and denominator assertions; the earlier 21-pass/65.26-second and
25-pass/53.10-second runs predate that final wording. No raw log file was
created; the command session's stdout and exit code are the original evidence.
The full browser smoke script's region locator was updated but that synthetic
legacy script was not executed as real-product visual evidence.
Session 65374 also exited 0 for focused ESLint with `--max-warnings=0`,
`node --check scripts/full-product-ui-smoke.mjs`, and `git diff --check`.

## 517e560a 이후 문서 쓰기·목록 갱신 수리

정상 merge `517e560a073ebfde087f4477ba0ea8125b7c25ff`는 부모
`0b28f8e289d50a0aff35565399395d00907fc107`과
`67fed84c000c86fb1da12560decea2edd13b47b2`의 유효 변경을 보존한다.
여기에는 보호 브랜치의 첨부파일 경로 우회 방지 수정도 포함된다.
이 HEAD의 7489 실행은 실패했다. API 25개·busy 3개는 통과했으나 Projects 22개는
fork worker 응답 timeout으로 실행되지 않았다. 첨부파일 검증 84038은 21개 통과,
44.88초, 종료코드 0이었다. 집중 lint·구문 검사도 통과했다.
승인된 동일 HEAD의 Projects 단독 진단 21052는 기본 timeout과 worker 1개를 유지한 채
22개를 55.63초에 통과했다. 단독 통과로 원래 통합 실행이나 worker 오류의 RCA를
완료 처리하지 않는다. 원시 진단 파일은
`/private/tmp/naruon-1352-merge-evidence.ju75sI/`에 있다.
원래 통합 출력은 도구 stdout 전사이며 전체 원시 로그를 재구성한 자료가 아니다.

### 문제·재현·소유권

원격 `67fed84c`의 미해결 CodeRabbit 리뷰는 두 문서 처리 함수가
`loadDataQualitySurface()` 종료 전에 성공을 표시하고, finally에서 활성 작업을
조건 없이 지운다고 지적했다. 호출부를 더 확인하니 `handleDocumentFileChange`도
업로드 도중 같은 상태를 초기화했다. 동기 요청 잠금이 없어 한 React 이벤트 배치에서
두 번 호출하면 disabled 상태가 DOM에 반영되기 전에 POST 두 건이 전송된다.

열린 PR 파일 목록은 네 페이지를 모두 조회했으며 잘린 파일 목록은 없었다.
#1352 외에 #1404(`a1a3d461`, 미리보기), #1449(`e25a3995`, pending 식별·오류 표시),
#1472(`d396ac49`, 작업별 문구)가 DataLayout을 변경한다.
파일 중첩은 현재 활동 중인 writer의 존재·부재를 증명하지 않는다.
#1449의 provider-write-false·409 충돌·422 입력 오류 처리는 유효 delta로 보존한다.
이번 로컬 수리가 그 기능까지 구현하거나 완전히 승계한 것은 아니다.
[승계 조정 댓글](https://github.com/ContextualWisdomLab/naruon/pull/1449#issuecomment-5563458717)은
정상 승계를 요청하며 자동 close·retarget·소스 복사를 허용하지 않는다.

생산 소스를 바꾸기 전 4174 실행에서 5개 단언이 모두 실패했다(31.07초).
업로드와 재분석은 갱신 중 잠금이 풀렸고, 동기 연속 호출은 POST를 두 번 보냈다.
파일 선택 변경도 진행 중인 업로드를 풀었으며, 쓰기 성공 뒤 갱신 실패를 구분하는
안내와 조회 전용 재시도 경로가 없었다. 테스트는 실제 DataLayout·DocumentRepositoryTab을
렌더링하되 네트워크 자료는 단위 테스트에만 사용한다. 고객 데이터 저장이나
실제 브라우저 Visual Inspection의 증거로 삼지 않는다.

### 선택한 수리와 보존할 계약

컴포넌트 내부 요청 식별자를 POST와 후속 갱신이 끝날 때까지 유지한다.
이벤트 처리 함수가 동기적으로 잠금을 얻고, 해당 요청만 종료 상태를 기록하거나
잠금을 해제한다. 네이티브 파일 입력 disabled와 처리 함수의 guard를 함께 둬
진행 중 파일 선택 변경을 막았다. 별도 조회 revision은 늦은 초기 응답이나
이미 떠난 화면의 응답이 목록·스냅샷 상태를 덮어쓰지 못하게 한다.
이미 전송한 POST의 효과가 취소되거나 rollback된다고 가정하지 않는다.

스냅샷 실패는 부분 성공으로 남아야 한다.
`frontend/src/app/data/page.test.tsx`의
`keeps quality checks usable when evidence snapshot fetch fails`가
스냅샷은 null이어도 품질 목록은 사용할 수 있어야 한다는 기존 계약이다.
첫 초안은 스냅샷 실패가 두 자료를 모두 무효화하도록 잘못 바꿨다.
기존 단위 테스트를 확인해 이를 수정했다. 스냅샷의 좁은 오류 진단은 유지하되
상태 반영은 동일한 최신 조회 revision으로 검사한다.

새 문구는 “요청 결과를 받았지만 목록을 새로 불러오지 못했습니다.”로,
외부 시스템 쓰기가 완료됐다고 주장하지 않는다. 조회만 재시도하고 이전 POST 결과는
보존한다. 응답 종류별 intent·provider 오류 문구는 #1449/#1472의 계약과 이어야 하며,
문구를 맞추려고 같은 POST를 다시 보내서는 안 된다.

### 검증 결과와 실패 기록

첫 수리 실행 22515는 static busy 1개 통과·생명주기 5개 실패였다(38.38초).
첫 사례가 기본 5초 timeout에 걸렸고 뒤이어 겹친 act 경고와 DOM 부재가 나타났다.
경고 필터나 timeout 상향은 적용하지 않았다.
초기 0초 effect 타이머만 명시적으로 진행하고, 실패 뒤 재시도에는 새 응답을 공급하도록
테스트를 수정했다. 예상된 503 진단의 내용·횟수를 정확히 검사하며 React 경고 같은
예상 밖 출력을 정상 증거로 받아들이지 않는다.

3713 실행도 4개 통과·3개 실패, 160.44초였다.
첫 timeout·후속 act 겹침·최신 화면 반영 전 단언이 남았으므로 타이머 제어만으로
문제가 해결됐다고 볼 수 없다. `data_lifecycle_scheduled_timers.log`에 원시 출력을 보존했다.
그 뒤 저장소 기존 페이지 테스트의 Promise-resolved JSON stub을 재사용했다.
단위 테스트가 의도치 않게 Node Response stream의 스케줄링까지 시험하지 않도록 한 조치다.
비활성 수집·임베딩·품질 탭만 mock하며 실제 DataLayout·DocumentRepositoryTab·ApiClient는
그대로 실행한다. 전체 탭 통합이나 HTTP decoder를 검증했다고 주장하지 않는다.

12304는 7개 통과, 48.54초, 종료코드 0, React 경고 없음이었다.
`data_lifecycle_project_fixture.log`와 종료코드 파일을 보존했다.
늦은 초기 응답 무시와 조회 재시도 성공 후 목록 복원·오류 제거·busy 해제를 포함하지만,
이 실행은 뒤에 추가한 unmount 회귀보다 앞선다. 52048의 focused ESLint도 종료코드 0이다.
73925는 기존 스냅샷 부분 성공 사례 1개를 17.07초에 통과했다. 다른 11개는 선택 대상 밖이었다.

26080은 Data 관련 3파일 20개를 34.96초에 통과했지만, 기존 테스트 두 개에서
스냅샷 응답 mock 누락으로 오류 진단이 남았다. 이를 깨끗한 GREEN으로 기록하지 않는다.
두 fixture에 기존 스냅샷 응답을 추가하고 예상 밖 console.error가 없다는 단언을 보강했다.
앞선 실패를 지우지 않으며 전체 프런트엔드 검사·배포·정상 상태 실제 VI는 여전히 별도 증거가 필요하다.

fixture 보강 후 97315는 동일한 Data 관련 3파일 20개를 37.32초에 통과했다.
종료코드는 0이며 예상 밖 stderr·React 경고는 없었다.
원시 파일은 `data_lifecycle_complete_fixture.log`, 종료코드 파일은
`data_lifecycle_complete_fixture_exit.txt`이다. 실행 명령은 frontend에서
`corepack pnpm exec vitest run --maxWorkers=1 src/components/DataLayout.document-lifecycle.test.tsx src/components/data-layout/DocumentRepositoryTab.busy-state.test.tsx src/app/data/page.test.tsx`이며
`env -i PATH="$PATH"`로 실행했다. 기본 timeout을 유지했고 제외한 Data 테스트는 없다.

### 공식 문서 근거

React의 ref 계약은 렌더링 상태를 동기 잠금처럼 쓰지 않고 이벤트 처리 함수에서
가변 요청 식별자를 유지하는 방법을 설명한다. effect 문서는 오래된 비동기 결과를
무시하는 것과 외부 작업 자체를 취소하는 것을 구별한다.
Context7은 quota 제한으로 사용할 수 없어 아래 공식 문서를 직접 확인했다.
이는 구현 방법의 근거이며 모든 예외 상황이나 이 구현의 검증 완료를 뜻하지 않는다.

React. (n.d.). *useRef*. Retrieved September 7, 2026, from
https://react.dev/reference/react/useRef

React. (n.d.). *useEffect*. Retrieved September 7, 2026, from
https://react.dev/reference/react/useEffect
