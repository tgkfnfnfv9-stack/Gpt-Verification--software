# Policy Incident 2026-08-29

incident_id: `PHASE9-INC-20260829-001`  
status: `REMEDIATED_TRIGGER_DISABLED_OUTCOME_EXPOSURE_NOT_REVIEWED`

## 発生内容

Phase 9事前登録commit `e94cd52a0ec5a990f32c3740ba83736beb95d709` をmainへ反映した際、旧一時workflow 2本がpath制限なしの`on: push`で自動起動しました。

- Run [33231270189](https://github.com/tgkfnfnfv9-stack/Gpt-Verification--software/actions/runs/33231270189)
- Run [33231270148](https://github.com/tgkfnfnfv9-stack/Gpt-Verification--software/actions/runs/33231270148)

## GitHub APIで確認した事実

| 項目 | 状態 |
|---|---|
| 禁止期間を含むDownload step | success |
| 旧research script step | failure |
| Artifact upload step | skipped |
| Run artifact数 | 両runとも0 |
| Phase 9 candidate code | 実行なし |
| Phase 9 outcome閲覧 | なし |
| Job logの結果内容確認 | 実施していない |

取得対象にはGBPJPY M15 BID/ASK、USDJPY・GBPUSD、VIXの2018/2019〜2026年が含まれました。runner一時領域でありArtifactは残っていませんが、「2022〜2026年が一度も取得されていない」という表現は撤回します。

## 科学的な扱い

- Phase 9の11 alpha＋1 overlayは実行されていません。
- Phase 9固有のreturn、MFE、MAE、edge、勝率は閲覧していません。
- 一方、旧戦略workflowによる将来期間アクセス履歴があるため、2022〜2026年を厳格な未接触splitと呼べるかは後続protocol前に再監査します。
- Frozen Phase 9 Discovery期間2014〜2019はこのincidentの取得対象外です。

## 原因

`.github/workflows/tmp-gbpjpy-h1-v8.yml`と`tmp-gbpjpy-h1-v8b.yml`が、mainへの全pushで起動する設定のまま残っていました。

## 是正

commit `b61e160faf353346c3d9f527e1fe551de5d765bf`で、両workflowを次の二重防御へ変更済みです。

1. triggerを手動`workflow_dispatch`だけにする
2. jobに`if: ${{ false }}`を設定して常にskipする

今後はpush後にActions runを確認し、意図しないworkflowが起動していないことを完了条件にします。
