# 次セッションへ送る文章

```text
GitHub Repository tgkfnfnfv9-stack/Gpt-Verification--software のPhase 9自動売買研究を引き継いでください。

最初に research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md を完全に読み、
同ファイルの「セッション開始時に読む順番」に従ってください。

Formal alphaは11件、risk overlayは1件、全件UNTESTED_PREREGISTEREDです。
旧tmp workflowのpolicy incidentがあるため POLICY_INCIDENT_20260829.md も必ず読んでください。
公開endpoint廃止とJForexへの切替え理由は PROVIDER_ACQUISITION_BLOCKER.md と JFOREX_SOURCE_CHANNEL_AMENDMENT.md を必ず読んでください。
正本はfrozen JSONとpreregistered policyです。draftを使わないでください。

公開endpointとdukascopy-go経路は廃止済みです。公式認証JForex Tester API、同一の12銘柄、M15/H1×BID/ASKの4runは結果未閲覧で凍結済みです。
次はphase9-acquisition-onlyをmanual dispatchし、認証・price request前に停止するBuild preflightで全Maven依存SHAと再珫uild JAR SHAを取得・凍結します。同一run full-QCまたは承認済み非公開raw保管の固定前に実取得しないでください。実取得時はM15が2019-08-28未満、H1が2019-08-01未満のみで、Count-only前にreturn/MFE/MAE/edgeを計算しません。
サブエージェントは8論理役割を、実際の並列上限に合わせて2波で使い、主担当だけがcommitしてください。
```
