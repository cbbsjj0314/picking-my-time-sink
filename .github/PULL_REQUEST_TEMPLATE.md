<!--
빠르게 훑어볼 수 있게 짧게 쓴다.
긴 문단보다 짧은 bullet을 선호한다.
PR 범위와 의도적으로 제외한 범위를 분명히 적는다.
필요 없는 section은 지운다.
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

## Not included

- Intentionally excluded item 1
- Follow-up item 2

---

## Validation

- `command 1`
- `command 2`

Results:
- Result 1
- Result 2

---

## Notes

- Reviewer context
- Caveats, rollout notes, or assumptions
