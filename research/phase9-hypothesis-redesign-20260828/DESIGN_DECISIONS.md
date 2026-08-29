# Phase 9 Design Decisions

更新日: 2026-08-29  
判断時点でPhase 9の市場return、MFE、MAE、edge、勝率は未閲覧。

## 確定した判断

1. PS-201はLV-202へ統合し、20-bar boundaryとvolatility squeezeを1候補にする。
2. PS-201の8-bar balance幅は診断値のみで、Entry・昇格・救済に使わない。
3. LV-204は旧VV-104との独立性を十分に説明できないためpretest削除。
4. RR-205は再現可能なpoint-in-time carry data未確保のためpretest除外。同じPhaseで差し替えない。
5. LV-205はPS-205と同じ方向signalであるため、独立alphaから外しRISK-P9-RO-201へ移動。
6. Formal alphaは11件、risk overlayは1件。BH-FDR familyは12 confirmatory questions全体、q=0.10。
7. 旧draftは保存し、新しいfrozenファイルだけを実行正本とする。

## 凍結した防止策

- count-only Gateより前にreturnを計算しない。
- Underpoweredはp=1としてFDR familyから外さず、条件を緩めない。
- Phase 8期間2019-08-28〜2022-08-28は永久にPhase 9昇格根拠へ使わない。
- 2013-01-01以上2019-08-28未満だけを取得可能範囲とする。
- Development、OOS、Final Holdoutはavailability照会・一括download・cacheも禁止。
- subgroup、sensitivity、特定銘柄、特定時間足で失敗候補を救済しない。
- RR-203/RR-204は2脚を独立銘柄数として水増しせず、1つのcomposite spreadとして評価する。
- OANDA MT5 EAは全研究Gate通過後のみ。
