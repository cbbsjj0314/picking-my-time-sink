<!--
빠르게 훑어볼 수 있게 짧게 쓴다.
긴 문단보다 짧은 bullet을 선호한다.
구체적이고 명확하게 쓴다.
쓸데없이 길게 쓰지 않는다.
추상적인 표현은 피한다.
PR 범위는 분명히 적는다.
인접하지만 이번 PR에 넣지 않은 내용만 별도로 적는다.
의도적으로 제외한 범위를 적을 필요가 없으면 해당 section은 지운다.
한국어 설명을 넣을 때는 반말 톤으로 간결하게 쓴다.
docs-only PR이면 Validation에 `Not run (docs-only change)`라고 적는다.

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

- What changed
- Why this change exists
- Scope boundary if relevant

---

## Changes

- Change 1
- Change 2
- Change 3

---

<!--
리뷰어가 같이 기대할 만한 인접 작업을 이번 PR에서 의도적으로 제외했을 때만 남긴다.
범위가 이미 자명하면 이 section은 통째로 지운다.
-->

## Out of scope / Deferred

- Intentionally excluded adjacent item
- Follow-up item kept for a separate PR

---

## Validation

- `command 1`
- `command 2`

Results:
- Result 1
- Result 2

---

<!--
Summary, Changes, Out of scope / Deferred, Validation에 이미 적은 내용을 반복하지 않는다.
리뷰어가 알아야 할 추가 맥락, caveat, assumption이 있을 때만 남긴다.
추가로 적을 내용이 없으면 이 section은 통째로 지운다.
-->

## Notes

- Reviewer context
- Caveats, rollout notes, or assumptions
