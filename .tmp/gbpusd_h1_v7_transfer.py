import importlib.util, json
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('m','/tmp/gbpjpy_h1_v8_macro.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b=m.b
OUT=Path('results'); OUT.mkdir(exist_ok=True)

# Exact transfer test: no GBPUSD-specific optimization.
P=dict(m.V6P)
X=dict(m.V7X)

def fm(ts): return b.fmt(b.metrics(ts))
def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)

def main():
    bid=b.h1(b.load('data/GBPUSD_M15_bid.csv'))
    ask=b.h1(b.load('data/GBPUSD_M15_ask.csv'))
    c=[x.close for x in bid]
    e20=b.ema(c,20); e50=b.ema(c,50)
    a14=b.atr(bid,14); a50=b.atr(bid,50)
    rv=b.rvol_series(bid,20)

    events=m.detect2(bid,e20,e50,a14,a50,rv,P)
    ts=m.simulate_v7(bid,ask,events,a14,X)

    periods={
      '2019_20':('2019-08-27','2020-08-27'),
      '2020_21':('2020-08-27','2021-08-27'),
      '2021_22':('2021-08-27','2022-08-27'),
      '2022_23':('2022-08-27','2023-08-27'),
      '2023_24':('2023-08-27','2024-08-27'),
      '2024_25':('2024-08-27','2025-08-27'),
      '2025_26':('2025-08-27','2026-08-27'),
      'latest_2y':('2024-08-27','2026-08-27'),
      'full_7y':('2019-08-27','2026-08-27')
    }
    pm={k:fm(sub(ts,a,z,bid)) for k,(a,z) in periods.items()}

    reasons={}
    for t in ts: reasons[t['exit_reason']]=reasons.get(t['exit_reason'],0)+1

    # latest-2y viewer JSON
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27))
    ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid))
    cb=bid[si:ei]
    cid='gbpusd_h1_v7_transfer'
    def cj(x):
        return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    chart={'id':cid,'symbol':'GBPUSD','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],
           'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],
           'panes':[{'label':'ATR14','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14[si:ei]]}]},
                    {'label':'RVOL20','series':[{'kind':'line','label':'RVOL20','values':[None if x is None else round(x,6) for x in rv[si:ei]]}]}]}

    latest=sub(ts,'2024-08-27','2026-08-27',bid)
    vt=[]
    for no,t in enumerate(latest,1):
        e=t['event']
        nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,
            'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),
            'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'V7 exact transfer to GBPUSD H1',
            'note':f"exit={t['exit_reason']}, flush_rvol={e['flush_rvol']:.2f}, vol_ratio={e['vol_ratio']:.2f}, breakout_rvol={e['breakout_rvol']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)

    summary={
      'test_type':'Exact out-of-pair transfer test. GBPJPY V7 rules copied to GBPUSD H1 with zero parameter optimization.',
      'data_source':'Dukascopy JForex/Jetta M15 BID+ASK aggregated to H1',
      'period':'2019-08-27 through 2026-08-26',
      'entry_params':P,'exit_params':X,
      'period_metrics':pm,'exit_reasons':reasons,
      'interpretation_rule':'Because no GBPUSD tuning was done, this test is primarily evidence about cross-pair portability. A weak result should not be rescued by reading it as optimized GBPUSD performance.'
    }
    viewer={'meta':{'report_title':'GBPUSD H1 V7 Exact Transfer Test','status':'検証済み'},
            'strategy':{'strategy_id':'GBPUSD_H1_V7_EXACT_TRANSFER','name':'GBPJPY V7 exact rules transferred to GBPUSD','hypothesis':'Same stop-sweep/recovery structure may generalize across GBP pairs.','entry_logic':['Exact V6/V7 entry parameters copied with no optimization'],'exit_logic':['Exact V7 exit parameters copied with no optimization'],'future_tests':['Only if transfer is promising: perform GBPUSD-specific development/holdout optimization separately.']},
            'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}

    (OUT/'GBPUSD_H1_V7_ExactTransfer_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPUSD_H1_V7_ExactTransfer_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
