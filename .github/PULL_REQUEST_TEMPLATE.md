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
한국어 설명은 간결하게 쓰고, 객체명 / endpoint / route / loader / table / view / CLI 명령은 실제 코드 표기를 유지한다.
docs-only PR이면 Validation section은 남기고 `- Not run (docs-only change)`라고 적는다.

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

- What changed
- Why this change exists
- Scope boundary if relevant

---

## Changes

<!--
무엇을 읽어 어디에 적재/노출하는지 보이게 쓴다.
view, table, endpoint, file path 같은 실제 객체명을 우선 쓴다.
-->

- Change 1
- Change 2
- Change 3

---

<!--
리뷰어가 같이 기대할 만한 인접 작업을 이번 PR에서 의도적으로 제외했을 때만 남긴다.
범위가 이미 자명하면 이 section은 통째로 지운다.
특히 입력 범위와 노출 범위가 다를 때는 남기는 편이 좋다.
-->

## Out of scope / Deferred

- Intentionally excluded adjacent item
- Follow-up item kept for a separate PR

---

## Validation

<!--
기본은 `command: result` 한 줄 형식으로 쓴다.
명령 목록과 결과를 따로 반복하지 않는다.
`pytest`는 가능하면 passed count / time까지 적는다.
추가 caveat나 skip 이유가 있으면 같은 bullet에 짧게 적고,
더 긴 설명이 필요할 때만 Notes로 보낸다.
-->

- `command 1`: result
- `command 2`: result

---

<!--
Summary, Changes, Out of scope / Deferred, Validation에 이미 적은 내용을 반복하지 않는다.
리뷰어가 알아야 할 추가 맥락, caveat, assumption이 있을 때만 남긴다.
추가로 적을 내용이 없으면 이 section은 통째로 지운다.
-->

## Notes

- Reviewer context
- Caveats, rollout notes, or assumptions
