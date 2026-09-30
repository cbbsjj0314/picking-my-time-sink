<!--
Canonical PR completion interface. Codex-created PRs open as Draft; humans decide Ready and merge.
PR title은 변경 결과를 짧게 요약한다. 본문은 간결한 한국어로 쓰고 technical identifier를 보존한다.
Ordinary PR은 Summary / Changes / Validation으로 충분하다. Ticket이나 governance field를 채우기 위해 만들지 않는다.
필요한 deferred scope, concrete uncertainty, caveat만 해당 section에 덧붙인다.
Required review / Human Gate / completion semantics는 docs/runbook/agent-workflow.md를 따른다.
-->

## Summary

- 변경 이유와 결과

## Changes

- 구현한 범위

## Validation

<!--
`command: exact result` 형식으로 적고, CI가 실행되면 결과를 기록한다.
Code change는 final code state의 ./scripts/check.sh 결과를 포함한다.
Docs-only PR은 수행한 static check 결과와 `Runtime checks: Not run (docs-only change)`를 적는다.
Documentation impact는 갱신한 durable docs 또는 기존 문서가 여전히 정확한 이유를 짧게 적는다.
-->

- `command`: result
- Documentation impact: Updated — durable docs / None — reason

<!--
아래는 accepted contract가 요구할 때만 본문에 추가하는 conditional evidence 예시다.
Ordinary PR에는 빈 governance section이나 N/A field를 만들 필요가 없다.
Ticket 내용을 장문으로 복제하지 않는다. 실제로 요구되는 field만 사용한다.

## Ticket / Spec

- Reference: 링크 또는 ID
- Acceptance evidence:
  - AC-1 → test, command, review 또는 document evidence

## Risk / Review / Human Gate

- Risk Level: Low / Medium / High
- Review Level: Standard / Fresh-context
- Independent Review Status: Not required / Pending / Findings open / Passed
- Independent Review Evidence: N/A / Pending — review not completed / human-authored GitHub comment or review
- Human Gate Required: Yes / No
- Risk / Assumptions: concrete risk or assumption

Required Fresh-context review가 미완료이면 Pending이다. Blocking finding 또는 required evidence 누락이 남으면 Findings open이다.
Passed는 Fresh-context reviewer가 해결을 최종 확인한 경우에만 사용한다.
Implementation agent의 자체 검증/수정/완료 보고와 원본 ChatGPT conversation은 independent review evidence가 아니다.
Public review evidence는 reviewed contract/ticket, findings, missing evidence, uncertainty, final status를 포함한 human-authored GitHub PR comment 또는 review다.

Human Gate Required: Yes이면 다음을 포함한다.

- Human Decision Status: Pending / Approved / Approved with conditions / Rejected
- Confirmed decision: Pending — requires a human-authored GitHub PR comment or review
- Remaining risk: concrete remaining risk
- Rollback / Mitigation: bounded mitigation

Approval evidence는 exact gated scope를 승인하는 human-authored GitHub PR comment 또는 review여야 한다.
PR body의 상태값, agent의 완료 보고, ChatGPT conversation 또는 모호한 decision reference는 approval evidence가 아니다.
Human-authored approval evidence가 없으면 Pending으로 유지한다.
Gate scope와 pre-gate allowed work/merge가 정해져 있으면 해당 contract와 evidence를 기록한다.
PR merge 자체를 Human Gate approval로 취급하지 않는다.
-->
