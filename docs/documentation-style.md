# Documentation style and translation guide

이 문서는 `picking-my-time-sink` repo에서 public documentation, runbook, decision record, evidence summary를 작성하거나 번역할 때 적용하는 문체·번역·formatting 기준을 정의한다.

목표는 문서를 한국어 중심으로 읽기 쉽게 유지하면서도, code와 연결되는 identifier, command, API route, schema/table/view name, metric name, status literal의 정확성을 보존하는 것이다.

## 관련 문서와 책임 경계

이 문서는 기존 project 운영 규칙을 대체하지 않는다.

- `AGENTS.md`는 agent 작업 방식, scope control, validation, Git convention의 상위 기준이다.
- `docs/data-governance.md`는 data meaning, public/local boundary, sanitized fixture, durable data contract의 기준이다.
- 이 문서는 README와 tracked public docs를 작성·번역할 때 적용하는 문체, literal 보존, formatting, docs-code consistency 기준을 다룬다.

동일한 주제를 다룰 때는 다음 기준을 따른다.

- agent workflow와 Git/validation 절차는 `AGENTS.md`를 우선한다.
- data governance와 public/private evidence boundary는 `docs/data-governance.md`를 우선한다.
- 문서 문체, 번역 방식, hard wrapping, PR body wording은 이 문서를 우선 참고한다.

## 적용 범위

이 문서는 다음 문서 작업에 적용한다.

- `README.md`
- `docs/**/*.md` 중 tracked public docs
- public-facing decision docs
- runbook
- evidence summary
- ticket/template 문서
- 문서-only PR body에서 문서 작업을 설명할 때 참고하는 wording 원칙

단, `docs/local/**`는 local/private documentation 영역으로 별도 취급한다.

다음 항목은 이 문서의 기본 번역 대상이 아니다.

- `web/**`의 UI copy
- API/client-visible message
- operator CLI/help output
- source comment/docstring
- test fixture와 snapshot
- generated file
- vendored file
- lockfile
- private/local-only evidence

위 항목을 수정해야 한다면 별도 scope, 별도 validation, 별도 PR로 분리한다.

## 기본 문체

문서는 Korean-first로 작성한다.

기본 문체는 해라체를 사용한다.

예:

```text
한다
유지한다
제외한다
남긴다
검증한다
```

해라체 문서에서는 다음 표현을 기본 문체로 쓰지 않는다.

```text
했습니다
됩니다
해주세요
할 수 있습니다
```

단, 사용자-facing UI 문구나 외부 독자를 대상으로 하는 별도 문서에서 다른 문체가 명시되어 있으면 그 문서의 목적을 우선한다.

## 번역 원칙

human-facing English prose는 한국어 중심으로 번역한다.

다만 다음 항목은 원문 spelling을 보존한다.

- identifier
- object name
- endpoint
- route
- table name
- view name
- model name
- schema name
- API name
- command
- module
- class
- function
- config key
- filename
- package name
- library name
- framework name
- metric name
- status literal
- enum value
- environment variable
- SQL fragment
- code symbol
- proper noun

예:

```text
GET /combined/games/overview
srv_chzzk_category_game_mapping
fact_chzzk_category_30m
CCU
KST
KR
Prometheus
Grafana
DuckDB
Dagster
ClickHouse
```

## Technical term 처리

software engineering term은 한국어로 옮겼을 때 의미가 흐려지거나 어색하면 English로 유지한다.

예:

```text
read-only
runtime
scheduler
contract
surface
mapping
guardrail
fallback
snapshot
artifact
metric
dashboard
query
schema
API
route
CLI
operator
probe
smoke
validation
lineage
materialization
freshness
partition
KPI
score
recommendation
localization
```

필요하면 짧은 한국어 설명을 덧붙인다.

다음은 설명을 덧붙이는 편이 좋은 technical term의 예시다.

```text
serving view
read model
bounded sample caveat
```

설명을 덧붙일 때는 다음처럼 짧게 쓴다.

```text
serving view: API가 읽기 쉽게 정리한 DB view
read model: 조회/API 응답에 맞춘 읽기 전용 데이터 모델
bounded sample caveat: 제한된 샘플 기반 관측값이라는 주의 문구
```

단순히 모든 English term을 한국어로 바꾸는 것을 목표로 하지 않는다.

## Code block과 literal

다음은 번역하지 않는다.

- code block
- inline code
- shell command
- command output
- JSON/YAML key
- SQL
- route literal
- path
- URL
- package name
- fixture literal
- metric literal
- status literal

예:

```md
`GET /games/explore/overview`
`git diff --check`
`docs/local/**`
`ready-to-open-pr`
```

위와 같은 literal은 그대로 유지한다.

## Caveat와 boundary 보존

문서의 caveat, warning, deferred boundary, operating boundary는 의미를 약화하거나 강화하지 않는다.

특히 다음 표현은 정확히 유지한다.

- read-only boundary
- no-write boundary
- Human Gate
- deferred scope
- private/local boundary
- bounded sample caveat
- raw/private evidence exclusion
- current implemented behavior
- future work
- historical checkpoint
- planning-only contract

문서가 “구현됨”과 “후속 작업”을 구분하고 있다면, 번역 중 이 경계를 바꾸지 않는다.

예:

```text
minimal Combined overview API는 구현되어 있다.
Chzzk metric merge, ranking/KPI/score/recommendation은 후속 작업이다.
```

위 두 상태를 섞지 않는다.

## Public/private boundary

public docs에는 raw/private/local-only evidence를 노출하지 않는다.

다음 항목은 public docs에 넣지 않는다.

- provider raw payload
- credentials
- token
- secret
- private runtime detail
- host/path 세부 정보
- scheduler XML/log
- row-level UGC
- raw API response
- private DB row
- real private category/game/channel name
- ignored local data content
- `docs/local/**`의 private/local-only 내용

public docs에는 durable contract, sanitized aggregate, public-safe summary만 남긴다.

## `docs/local/**` 처리

`docs/local/**`는 local/private documentation 영역으로 취급한다.

tracked public docs에서 `docs/local/**`를 참조할 수는 있지만, 그 내용을 public docs로 복사하지 않는다.

`docs/local/**`가 Git에서 ignored이거나 untracked라면, public PR에 포함하지 않는다.

## Formatting 규칙

문서 수정 시 불필요한 formatting churn을 만들지 않는다.

특히 normal prose paragraph에 line-length 기반 hard wrapping을 새로 추가하지 않는다.

원칙:

- 기존 Markdown paragraph style을 유지한다.
- 문장 중간을 글자 수 기준으로 강제 개행하지 않는다.
- heading, list, table, code block, blockquote 구조를 보존한다.
- code fence를 reflow하지 않는다.
- command example을 reflow하지 않는다.
- table 구조를 깨지 않는다.
- 의미 변경 없는 broad rewrite를 피한다.

## 문서-코드 일치성

문서가 current-state claim을 포함한다면 code와 충돌하지 않는지 확인한다.

확인 대상:

- path
- command
- script
- API route
- endpoint
- table/view/schema name
- metric name
- dashboard name
- config key
- status literal
- implemented/unimplemented claim
- future work claim

예:

```text
README가 “현재 구현된 endpoint만 포함한다”고 말하면, 실제 router에 등록된 endpoint와 일치해야 한다.
```

historical checkpoint나 planning doc은 과거 상태를 말할 수 있다. 단, current-state 문서처럼 읽히지 않도록 historical/planning context를 명확히 남긴다.

## 문서 분류

문서 작업 전에는 대상 파일을 먼저 분류한다.

### Primary reader

문서 번역 여부는 파일 확장자나 위치만으로 결정하지 않고, primary reader를 기준으로 판단한다.

권장 reader 분류:

- `operator_facing`: 사람이 직접 실행·점검·운영 판단에 사용하는 문서다. 예: manual runbook, smoke 절차, scheduler 점검, local operation note, troubleshooting guide.
- `agent_facing`: Codex나 coding agent가 작업 방식, scope, validation, repo convention을 이해하기 위해 읽는 문서다. 예: `AGENTS.md`, agent workflow, implementation prompt, task execution rule.
- `public_facing`: repo 방문자나 reviewer가 project purpose, current behavior, API/data contract, setup 방법을 이해하기 위해 읽는 tracked public 문서다. 예: `README.md`, public architecture docs, public decision docs.
- `developer_facing`: repo contributor가 code, test, build, architecture를 이해하기 위해 읽는 문서다. 예: development setup, architecture note, testing guide.
- `mixed_reader`: operator, agent, developer, reviewer가 함께 읽는 문서다. 이 경우 section 단위로 독자를 나누고, 전체 번역 여부를 임의로 결정하지 않는다.

### Translation decision

Primary reader를 분류한 뒤 translation decision을 따로 정한다.

권장 decision 분류:

- `translate_korean_first`: human-facing prose를 한국어 중심으로 번역한다.
- `keep_english`: 문서의 primary reader, 외부 독자, ecosystem convention 때문에 English를 유지한다.
- `preserve_literals_only`: 설명 문장은 한국어화할 수 있지만 command, identifier, route, config, status literal은 그대로 유지한다.
- `split_by_section`: mixed-reader 문서에서 section별로 번역 여부를 다르게 판단한다.
- `defer_to_separate_scope`: UI copy, API/client-visible message, operator CLI/help output, source comment/docstring처럼 별도 PR로 분리한다.

기본 판단:

- Korean-speaking human operator가 직접 읽는 문서는 `translate_korean_first` 우선순위가 높다.
- `agent_facing` 문서는 무조건 번역하지 않는다. agent가 정확히 따라야 하는 command, constraint, validation rule, repo convention은 English technical literal을 보존하고, 필요할 때만 Korean-first 설명을 추가한다.
- `public_facing` 문서는 repo의 예상 독자에 따라 결정한다. 현재 repo가 한국어 사용자/운영자 중심이면 `translate_korean_first`가 적절하고, 외부 English reader를 우선하면 `keep_english`가 적절할 수 있다.
- `mixed_reader` 문서는 `split_by_section`을 기본값으로 둔다.

### Inventory classification

Repo-wide audit에서는 primary reader와 translation decision을 정한 뒤, 대상 파일을 작업 단위로 다시 분류한다.

권장 inventory 분류:

- `public_docs_candidate`
- `ui_localization_candidate`
- `api_or_client_message_candidate`
- `operator_facing_candidate`
- `comment_or_docstring_review_only`
- `test_or_fixture_coupled`
- `already_sufficiently_korean`
- `keep_english`
- `generated_or_excluded`
- `manual_review_needed`

문서 번역 PR에서는 기본적으로 `public_docs_candidate` 중 `translate_korean_first`로 판단된 항목만 mutation 대상으로 삼는다.

`ui_localization_candidate`, `api_or_client_message_candidate`, `operator_facing_candidate`, `comment_or_docstring_review_only`는 별도 작업으로 분리한다.

## Preferred wording

다음 표현은 repo에서 선호하는 해석을 따른다.

### `emit` / `emitted field`

`emit`은 실행 결과에 포함되어 출력·노출된다는 의미로 해석한다.

권장 표현:

```text
현재 실행 결과에 포함되어 노출되는 `execution-meta` field
```

### `Ratio`

`Ratio`가 문서화된 formula이고 emitted field가 아니라면 다음처럼 표현한다.

```text
`Ratio`는 문서에 설명된 계산식/formula일 뿐이고, 실제 실행 결과에 포함되어 출력·노출되는 field는 아니다.
```

### `per-run execution meta`

권장 표현:

```text
각 job/run 실행마다 생기는 일반 실행 메타데이터(`execution-meta`)
```

### `Raw representative capture`

원본 대표 캡처를 의미한다.

필요하면 다음처럼 쓴다.

```text
Raw representative capture
```

또는:

```text
원본 대표 캡처(`raw representative capture`)
```

### `ingest regression input`

Parser 또는 ingest 동작이 regression되지 않았는지 검증하는 입력을 의미한다.

필요하면 다음처럼 쓴다.

```text
Parser 또는 ingest regression input
```

또는:

```text
Parser 또는 ingest regression 검증에 쓰는 입력
```

### `durable contract`

오래 유지되는 안정적인 contract를 의미한다.

필요하면 다음처럼 쓴다.

```text
durable contract
```

또는:

```text
장기적으로 유지되는 contract
```

## 경로 규칙

경로와 evidence 성격은 다음 기준으로 나눈다.

```md
경로 규칙:

- 각 job/run 실행마다 생기는 일반 실행 메타데이터(`execution-meta`)는 local/private에 유지한다.
- Raw representative capture는 ignored local data path 아래에 유지한다.
- Parser 또는 ingest regression input은 `tests/fixtures/...` 아래의 최소 sanitized fixture여야 한다.
- Public docs에는 durable contract만 유지한다.
```

## Validation

문서-only 변경에서는 `AGENTS.md`의 validation 원칙을 우선하되, 이 문서 관점에서는 최소한 다음을 확인한다.

```bash
git diff --check
git status --short
git diff --name-only
```

PR 전에는 다음도 확인한다.

```bash
git diff --name-only main...HEAD
git diff --stat main...HEAD
```

문서가 path, command, route, metric, table/view/schema를 언급하면 static check를 수행한다.

예:

```bash
test -e "<path>"
git grep -n "<identifier-or-route>"
```

문서-only PR에서는 tests/builds를 실행하지 않을 수 있다. 이 경우 PR body에 실행하지 않은 validation을 적지 않는다.

## PR body 규칙

PR body는 repo의 기존 PR 관례와 PR template이 있으면 그 template을 우선 따른다.

이 문서는 PR body의 전체 구조를 새로 정의하지 않는다. 다만 문서-only PR에서 한국어 문서 작업을 설명할 때는 다음 원칙을 따른다.

- PR body도 Korean-first로 작성한다.
- section heading, command, route, validation token, status literal은 English를 유지할 수 있다.
- 실행하지 않은 tests/builds/validation을 적지 않는다.
- Web UI, API/client-visible message, operator CLI/help output, source comment/docstring처럼 제외한 범위는 명확히 deferred로 남긴다.
- raw/private/local-only evidence를 PR body에 노출하지 않는다.

PR body 구성이 애매하면 `AGENTS.md`의 planning/reporting, validation, Git convention을 우선 참고한다.

## Commit message 규칙

Commit message와 squash merge title은 `AGENTS.md`의 Git convention을 따른다.

이 repo의 기본 형식은 다음이다.

```text
type(scope): summary
```

문서-only 변경은 보통 `docs` type을 사용한다.

예:

```text
docs: add documentation style guide
docs(readme): align Combined overview API status
```

이 문서는 commit convention의 source of truth가 아니다. 자세한 Git convention은 `AGENTS.md`를 우선한다.

이미 merge된 `main` history를 commit message만 고치기 위해 rewrite하지 않는다. 다음 PR부터 관례를 지킨다.

## Agent checklist

Codex나 coding agent가 문서 작업을 수행할 때는 다음 순서를 따른다.

1. repo root와 branch를 확인한다.
2. 변경 대상 파일을 명확히 제한한다.
3. 바로 번역하지 말고 필요한 경우 read-only inventory audit을 먼저 수행한다.
4. 문서 분류와 excluded scope를 먼저 보고한다.
5. human-facing prose만 번역한다.
6. identifier와 technical literal을 보존한다.
7. caveat와 deferred boundary를 보존한다.
8. hard wrapping을 추가하지 않는다.
9. public/private boundary를 확인한다.
10. 문서가 code 상태와 충돌하지 않는지 static check한다.
11. `git diff --check`를 실행한다.
12. PR body와 squash title이 `AGENTS.md`와 repo 관례에 충돌하지 않는지 확인한다.

## Completion criteria

문서 작업은 다음 조건을 만족해야 완료로 본다.

- 변경 파일이 target scope 안에 있다.
- non-target implementation file이 섞이지 않았다.
- raw/private/local-only evidence가 노출되지 않았다.
- identifier, command, route, schema/table/view name, metric name이 변형되지 않았다.
- current-state 문서가 code 상태와 충돌하지 않는다.
- hard wrapping이나 Markdown 구조 문제가 없다.
- `git diff --check`가 통과한다.
- PR body가 실제 수행한 validation만 말한다.
- PR body와 squash merge title이 `AGENTS.md`와 repo 관례에 충돌하지 않는다.
