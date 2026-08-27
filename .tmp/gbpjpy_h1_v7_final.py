import importlib.util, json
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('b','/tmp/gbpjpy_h1_v5_opt.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
spec2=importlib.util.spec_from_file_location('v6','/tmp/gbpjpy_h1_v6_regime.py')
v6=importlib.util.module_from_spec(spec2); spec2.loader.exec_module(v6)
spec3=importlib.util.spec_from_file_location('v7','/tmp/gbpjpy_h1_v7_exit.py')
v7=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(v7)
OUT=Path('results'); OUT.mkdir(exist_ok=True)

V6P=v7.V6P
V6_EXIT={'target_r':2.25,'max_hold':24,'stop_buffer_atr':0.0,'be_trigger_r':None,'be_offset_r':0.0,'range_after':None,'range_lookback':4,'range_width_atr':1.0,'range_progress_max_r':0.5,'range_mfe_max_r':1.0}
# Final V7 is chosen from the development plateau: use the lower/central target 2.5R rather than 2.75/3.0 to reduce tail sensitivity.
V7_EXIT={'target_r':2.5,'max_hold':30,'stop_buffer_atr':0.10,'be_trigger_r':None,'be_offset_r':0.0,'range_after':16,'range_lookback':4,'range_width_atr':1.0,'range_progress_max_r':0.25,'range_mfe_max_r':1.0}
V7_NO_RANGE=dict(V7_EXIT); V7_NO_RANGE['range_after']=None

def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)
def fm(m): return b.fmt(m)
def reasons(ts):
    d={}
    for t in ts: d[t['exit_reason']]=d.get(t['exit_reason'],0)+1
    return d

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    ev=v6.detect2(bid,e20,e50,a14,a50,rv,V6P)
    base=v7.exit_sim(bid,ask,ev,a14,V6_EXIT)
    norange=v7.exit_sim(bid,ask,ev,a14,V7_NO_RANGE)
    final=v7.exit_sim(bid,ask,ev,a14,V7_EXIT)

    periods={
      'external_new_2020_21':('2020-08-27','2021-08-27'),
      'external_old_2021_22':('2021-08-27','2022-08-27'),
      'dev_2022_25':('2022-08-27','2025-08-27'),
      'recent_2025_26':('2025-08-27','2026-08-27'),
      'latest_2y':('2024-08-27','2026-08-27'),
      'full_2021_26':('2021-08-27','2026-08-27'),
      'full_2020_26':('2020-08-27','2026-08-27'),
    }
    def pack(ts): return {k:fm(b.metrics(sub(ts,a,z,bid))) for k,(a,z) in periods.items()}
    baseline_pack=pack(base); norange_pack=pack(norange); final_pack=pack(final)
    dev_years=[]
    for a,z in [('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]: dev_years.append(fm(b.metrics(sub(final,a,z,bid))))
    summary={
      'data_source':'Dukascopy JForex BID+ASK M15 aggregated H1, 2020-08-27～2026-08-26',
      'selection_policy':'V6 entries frozen. Exit family optimized on 2022-08-27～2025-08-26. Final target set to 2.5R from a broad 2.5～3.0R development plateau (conservative lower target). 2020-08-27～2021-08-26 was not used in V1～V7 development and is new external validation.',
      'v6_entry_params':V6P,
      'v6_exit':V6_EXIT,
      'v7_exit':V7_EXIT,
      'v7_range_definition':'After 16 held H1 bars, if the last 4 completed H1 bars have total high-low width <= 1.0×ATR14, current close progress <= +0.25R, and MFE since entry <= +1.0R, classify as stagnant/range and exit at next H1 BID open.',
      'v6_metrics':baseline_pack,
      'v7_no_range_ablation':norange_pack,
      'v7_metrics':final_pack,
      'v7_dev_years':dev_years,
      'v7_exit_reasons_dev':reasons(sub(final,'2022-08-27','2025-08-27',bid)),
      'v7_exit_reasons_recent':reasons(sub(final,'2025-08-27','2026-08-27',bid)),
      'v7_exit_reasons_external_new':reasons(sub(final,'2020-08-27','2021-08-27',bid)),
      'notes':['Break-even was tested in the V7 search but not selected; it tended to cut winners too early.','Initial SL is 0.10×ATR below the Flush low, giving the stop a small noise buffer.','Swap/rollover financing is not included because it is broker-specific; final MT5 broker retest should add it for positions crossing rollover.']
    }
    print('=== V7 FINAL SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))

    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]
    latest2=sub(final,'2024-08-27','2026-08-27',bid); cid='gbpjpy_h1_flush_recovery_v7_final'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'ATR14','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14[si:ei]]}]},{'label':'Volume','series':[{'kind':'histogram','label':'H1 Volume','values':[round(x.volume,4) for x in cb]}]},{'label':'RVOL20','levels':[V6P['rvol_min'],1.0],'series':[{'kind':'line','label':'RVOL20','values':[None if x is None else round(x,6) for x in rv[si:ei]]}]},{'label':'ATR14/ATR50','levels':[V6P['vol_ratio_min'],V6P['vol_ratio_max']],'series':[{'kind':'line','label':'Vol Ratio','values':[round(a14[i]/a50[i],6) if a50[i]>0 else None for i in range(si,ei)]}]}]}
    vt=[]
    for no,t in enumerate(latest2,1):
        e=t['event']; nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V7 Final','note':f"exit={t['exit_reason']}, RVOL={e['flush_rvol']:.2f}, ATR比={e['vol_ratio']:.2f}, BOvol={e['breakout_rvol']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V7 Final','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V7_FINAL','name':'V6 Entry + V7 Exit / Range Escape','hypothesis':'V6のエントリー優位性を維持し、SLに小さなATRバッファを持たせ、30時間まで伸ばしつつ、16時間経過後に停滞レンジを検出して撤退する。','entry_logic':['V6 entry rules frozen',json.dumps(V6P,ensure_ascii=False),'全条件はEntry前に確定','BUYはASK始値'],'exit_logic':['初期SL=Flush安値 - 0.10×Flush ATR','TP=+2.50R','最大保有=30時間','16時間経過後、直近4本の総値幅<=1.0×ATR14 かつ 現在進捗<=+0.25R かつ MFE<=+1.0R ならレンジ停滞と判定し、次のH1 BID始値で撤退','建値移動なし','同一H1足でSL/TP両方ならSL先着'],'future_tests':['MT5 broker tick volume再検証','broker-specific swap/rollover costを追加','完全未使用の将来期間でウォークフォワード']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V7_Final_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V7_Final_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
