<!--
빠르게 훑어볼 수 있게 짧게 쓴다.
긴 문단보다 짧은 bullet을 선호한다.
구체적이고 명확하게 쓴다.
쓸데없이 길게 쓰지 않는다.
추상적인 표현은 피한다.
효과를 과장하는 표현보다 구현 사실을 먼저 적는다.
PR 범위는 분명히 적는다.
인접하지만 이번 PR에 넣지 않은 내용만 별도로 적는다.
의도적으로 제외한 범위를 적을 필요가 없으면 해당 section은 지운다.
PR 본문은 한국어로 작성한다.
설명 문장은 간결한 한국어로 쓰고, 객체명 / endpoint / route / loader / table / view / CLI 명령은 번역하지 않고 실제 코드 표기를 유지한다.
docs-only PR이면 Validation section은 남기고 `- Not run (docs-only change)`라고 적는다.
Ticket / Spec reference, Human Gate Required, Risk / Assumptions, Required Checks / CI result는 짧게 적는다.
Ticket 내용을 PR 본문에 장문으로 반복하지 않는다.
해당하지 않으면 `- N/A`로 두거나 section을 지운다.

PR title guidance:
PR 전체를 한 줄로 요약하는 짧고 읽기 쉬운 제목으로 쓴다.
개별 commit 메시지보다 한 단계 위에서 작업 결과나 범위를 설명한다.

Good examples:
- Clarify app catalog resume behavior
- Add 90-day CCU daily reader service
- Prepare tracked universe scheduled pipeline

Avoid:
- docs(source-inventory): document app catalog resume precedence
- fix: update tests and docs
-->

## Summary

<!--
가능하면 입력과 출력이 함께 보이게 쓴다.
첫 bullet에서 이 PR이 왜 필요한지 한 줄로 설명하면 좋다.
내부 개발 용어만으로 설명하지 않는다.
-->

- 변경 사항
- 변경 이유
- 필요하면 범위 경계
- Ticket / Spec: 링크 또는 ID

---

## Changes

<!--
무엇을 읽어 어디에 적재/노출하는지 보이게 쓴다.
view, table, endpoint, file path 같은 실제 객체명을 우선 쓴다.
-->

- 변경 1
- 변경 2
- 변경 3

---

<!--
리뷰어가 같이 기대할 만한 인접 작업을 이번 PR에서 의도적으로 제외했을 때만 남긴다.
범위가 이미 자명하면 이 section은 통째로 지운다.
특히 입력 범위와 노출 범위가 다를 때는 남기는 편이 좋다.
-->

## Out of scope / Deferred

- 의도적으로 제외한 인접 작업
- 별도 PR로 남긴 후속 작업

---

## Risk / Review / Human Gate

<!--
Independent Review Status는 다음 의미로 사용한다.
- Not required: Review Level은 Standard이고 Independent Review Evidence는 N/A다.
- Pending: Fresh-context review가 필요하지만 아직 완료되지 않았으며, Independent Review Evidence에는 아직 evidence가 없음을 표시한다.
- Findings open: Blocking finding 또는 required evidence 누락이 남아 있으며, Independent Review Evidence는 finding이 기록된 GitHub PR comment 또는 GitHub review를 가리킨다.
- Passed: Fresh-context reviewer가 blocking findings와 required evidence 해결을 최종 재확인했으며, Independent Review Evidence는 최종 재확인 결과가 기록된 GitHub PR comment 또는 GitHub review를 가리킨다.

Implementation agent가 수정한 사실만으로 Passed를 사용할 수 없다.
Fresh-context reviewer의 재확인 없이 Findings open을 Passed로 바꾸지 않는다.
Implementation agent 자신의 완료 보고나 자체 수정 결과는 independent review evidence가 아니다.
Fresh-context review의 원본 ChatGPT conversation은 public independent review evidence가 아니다.
Fresh-context review 결과는 reviewed contract and ticket, blocking findings, missing evidence, remaining uncertainty, final status를 포함한 짧은 human-authored GitHub PR comment 또는 GitHub review로 기록한다.

Human Gate Required는 Yes / No로 적는다. Yes일 때만 Human Decision Status, Confirmed decision, Remaining risk, Rollback / Mitigation field를 남긴다.
Human Gate Required가 Yes일 때 실제 approval evidence는 human-authored GitHub PR comment 또는 human-authored GitHub review로 제한한다.
Confirmed decision은 human-authored GitHub PR comment 또는 GitHub review를 가리켜야 한다.
PR 본문에 기입된 상태값이나 implementation agent의 자기 보고만으로는 Human Gate approval을 증명할 수 없다.
ChatGPT conversation, 이를 가리키는 모호한 reference, implementation agent의 완료 보고는 Human Gate approval evidence가 아니다.
Human-authored approval evidence가 아직 없으면 Human Decision Status는 Pending, Confirmed decision은 `Pending — requires a human-authored GitHub PR comment or review`로 유지한다.

위험한 가정, runtime/schema/API/scheduler/DB/deploy 관련 caveat가 있으면 한 줄로 적는다.
없으면 `- Human Gate Required: No`와 `- Risk / Assumptions: N/A` 정도로 짧게 둔다. Human Gate Required가 No이면 Human Decision field를 지운다.
-->

- Risk Level: Low / Medium / High
- Review Level: Standard / Fresh-context
- Independent Review Status: Not required / Pending / Findings open / Passed
- Independent Review Evidence: N/A / Pending — review not completed / GitHub comment or review reference
- Human Gate Required: Yes / No
- Risk / Assumptions: N/A
- Human Decision Status: Pending / Approved / Approved with conditions / Rejected
- Confirmed decision: Pending — requires a human-authored GitHub PR comment or review
- Remaining risk: N/A
- Rollback / Mitigation: N/A

---

## Validation

<!--
기본은 `command: result` 한 줄 형식으로 쓴다.
명령 목록과 결과를 따로 반복하지 않는다.
`pytest`는 가능하면 passed count / time까지 적는다.
CI가 돌았다면 Required Checks / CI result도 짧게 적는다.
추가 caveat나 skip 이유가 있으면 같은 bullet에 짧게 적고,
더 긴 설명이 필요할 때만 Notes로 보낸다.
-->

- `command 1`: result
- `command 2`: result
- Required Checks / CI: result
- Acceptance evidence:
  - AC-1 → test, command, smoke, review 또는 document evidence
  - AC-2 → ...

---

<!--
Summary, Changes, Out of scope / Deferred, Validation에 이미 적은 내용을 반복하지 않는다.
리뷰어가 알아야 할 추가 맥락, caveat, assumption이 있을 때만 남긴다.
추가로 적을 내용이 없으면 이 section은 통째로 지운다.
-->

## Notes

- 리뷰어가 알아야 할 맥락
- caveat, rollout note, assumption
