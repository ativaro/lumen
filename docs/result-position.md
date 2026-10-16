# Interactive results stay in conversation order

A completed `lumen_present_view` used to occupy a global footer below all chat
messages. Later text and replies appeared above the old table or controls.

The shared result reader now retains the originating message and part position.
Display-only segments place the existing interactive view between the preceding
and following text. Native Studio moves its existing widget to that row; Search
loads the same ResultView in the matching row. This also covers supported file
results in standalone Search. Stored messages, tool payloads and permissions do
not change. Copy/save still use the complete original answer.

Filters and selections remain in the existing RichController during streaming.
The existing contract is unchanged: a newly presented interactive view replaces
the preceding one. This is not an archive of every previous interactive view.

Verification: a synthetic real Qt/QML test reproduces the old incorrect order,
then checks table -> trailing text in the same message -> follow-up -> new answer,
continued streaming, filter preservation and session switch/return. 36 focused
answer, rich-result, Studio, clipboard and privacy tests pass; the Search UI
keyboard/theme/voice test and the position test also pass after adding explicit
fallback row flags. Installed position/clipboard tests run with disposable
profiles and no provider request.

The broader Search suite retains two previously recorded scroll-test failures
(answer-start and latest-message button expectations). They are unrelated to
result placement and are not claimed as passing. A Studio test still expected
removed product rooms; its expected destination now matches projects.
