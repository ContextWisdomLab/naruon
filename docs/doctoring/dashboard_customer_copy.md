# Dashboard customer-facing status copy

## Evidence and scope

The scoped visual inspection of Naruon #1570 at
`c298e4d93dfa5dcdefeac3a9312f92804b234584` found two implementation terms
on the Today dashboard: `source-linked` and `충돌 토큰 있음`.
See [the independent visual receipt](https://github.com/ContextualWisdomLab/naruon/pull/1570#issuecomment-5560458888)
and Gap baseline 1.52. This follow-up changes existing copy, not the parent
response guards, request lifecycle, API fields, or translation infrastructure.

The pending-task card counts tasks whose status is not done. Its caption is
therefore `미완료`, without implying that the user must understand source linkage.
An ETag provides a comparison baseline, not proof of freshness, write permission,
or absence of a conflict. The existing truthy branch becomes `원본 변경 비교 가능`;
the absent branch becomes `변경 전 원본 확인 필요`. Do not say changes were checked
or writes completed merely because an ETag is present. The calendar action
remains available and provider enforcement is unchanged.

The existing dashboard source-evidence test covers both ETag states, unchanged
counts, source scope and request headers. Its first new expectation failed on
the parent text before the copy repair. Existing browser recovery cases also
assert the customer-facing labels and absence of the two internal terms.
Record fresh browser screenshots before claiming visual acceptance. This is
not delivery of all eight locales or a versioned database translation owner;
those remain separate product requirements. No static catalog or new dependency
is introduced.
