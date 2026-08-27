import importlib.util, json, math, random, statistics
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('b','/tmp/gbpjpy_h1_v5_opt.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
OUT=Path('results'); OUT.mkdir(exist_ok=True)

def detect2(bars,e20,e50,a14,a50,rv,p):
    ev=[]; i=80; n=len(bars)
    while i<n-60:
        hw=p['h0_window']; h0i=max(range(i-hw,i),key=lambda z:bars[z].high); h0=bars[h0i].high
        if not 1<=i-h0i<=hw: i+=1; continue
        if not (e20[h0i]>e50[h0i] and bars[h0i].close>e20[h0i]): i+=1; continue
        a0=a14[h0i]
        if a0<=0: i+=1; continue
        trend_strength=(e20[h0i]-e50[h0i])/a0
        slope_strength=(e50[h0i]-e50[max(0,h0i-p['slope_lb'])])/a0
        if trend_strength<p['trend_strength_min'] or slope_strength<p['slope_strength_min']: i+=1; continue
        prior_low=min(bars[z].low for z in range(max(0,h0i-p['sweep_lookback']),h0i))
        fl=bars[i].low; drop=h0-fl; sweep_depth=(prior_low-fl)/a0
        if drop<p['atr_mult']*a0 or fl>=prior_low or sweep_depth<p['sweep_depth']: i+=1; continue
        if rv[i] is None or rv[i]<p['rvol_min']: i+=1; continue
        vr=a14[i]/a50[i] if a50[i]>0 else 0
        if vr<p['vol_ratio_min'] or vr>p['vol_ratio_max']: i+=1; continue
        rng=max(1e-12,bars[i].high-bars[i].low); reject=(bars[i].close-bars[i].low)/rng
        if reject<p['flush_rejection_min']: i+=1; continue
        rec=None; rr=0
        for j in range(i+1,min(n,i+p['recovery_bars']+1)):
            ratio=(bars[j].close-fl)/drop if drop>0 else 0
            if bars[j].close>prior_low and ratio>=p['recovery_pct']:
                rec=j; rr=ratio; break
        if rec is None: i+=1; continue
        if p['recovery_rvol_min']>0 and (rv[rec] is None or rv[rec]<p['recovery_rvol_min']): i+=1; continue
        bo=None
        for k in range(rec,min(n-1,rec+p['breakout_bars']+1)):
            if bars[k].close>h0+p['breakout_buffer']*a0:
                bo=k; break
        if bo is None: i+=1; continue
        bo_strength=(bars[bo].close-h0)/a0
        if bo_strength<p['breakout_strength_min']: i=bo+1; continue
        if p['breakout_rvol_min']>0 and (rv[bo] is None or rv[bo]<p['breakout_rvol_min']): i=bo+1; continue
        ret=None; abo=a14[bo]
        for q in range(bo+1,min(n-1,bo+p['retest_bars']+1)):
            near=bars[q].low<=h0+p['retest_touch']*abo
            hold=bars[q].close>=h0-p['retest_hold']*abo
            if near and hold and b.session_ok(bars[q].dt.hour,p['session']): ret=q; break
        if ret is not None and ret+1<n:
            ev.append({'entry_i':ret+1,'flush_i':i,'recovery_i':rec,'breakout_i':bo,'retest_i':ret,'h0':h0,'flush_low':fl,'atr0':a0,'drop_atr':drop/a0,'sweep_depth_atr':sweep_depth,'flush_rvol':rv[i],'vol_ratio':vr,'recovery_ratio':rr,'trend_strength':trend_strength,'slope_strength':slope_strength,'flush_rejection':reject,'recovery_rvol':rv[rec],'breakout_rvol':rv[bo],'breakout_strength':bo_strength})
        i=bo+1
    return ev

def rp(r):
    return {'slope_lb':r.choice([5,8]),'h0_window':r.choice([5,7]),'atr_mult':r.choice([0.9,1.0,1.15,1.3]),'sweep_lookback':r.choice([10,12,16]),'sweep_depth':r.choice([0.03,0.06,0.10]),'recovery_bars':r.choice([4,6]),'recovery_pct':r.choice([0.55,0.65]),'breakout_bars':r.choice([8,10,14]),'breakout_buffer':r.choice([0.0,0.02]),'retest_bars':r.choice([6,10,14]),'retest_touch':r.choice([0.50,0.65]),'retest_hold':r.choice([0.15,0.20,0.30]),'session':r.choice(['london','london_ny']),'rvol_min':r.choice([0.65,0.75,0.85]),'vol_ratio_min':r.choice([0.75,0.85]),'vol_ratio_max':r.choice([1.30,1.50,2.00]),'recovery_rvol_min':r.choice([0.0,0.65,0.80]),'breakout_rvol_min':r.choice([0.65,0.80]),'trend_strength_min':r.choice([0.0,0.10,0.20,0.30]),'slope_strength_min':r.choice([0.0,0.03,0.06,0.10]),'flush_rejection_min':r.choice([0.0,0.15,0.30]),'breakout_strength_min':r.choice([0.0,0.05,0.10])}

def sub(ts,a,z,bars): return b.subset(ts,a,z,bars)
def fm(m): return b.fmt(m)

def main():
    bid=b.h1(b.load('data/GBPJPY_M15_bid.csv')); ask=b.h1(b.load('data/GBPJPY_M15_ask.csv'))
    c=[x.close for x in bid]; e20=b.ema(c,20); e50=b.ema(c,50); a14=b.atr(bid,14); a50=b.atr(bid,50); rv=b.rvol_series(bid,20)
    years=[('2022-08-27','2023-08-27'),('2023-08-27','2024-08-27'),('2024-08-27','2025-08-27')]
    rng=random.Random(2026082702); seen=set(); C=[]
    for _ in range(1800):
        p=rp(rng); k=json.dumps(p,sort_keys=True)
        if k in seen: continue
        seen.add(k)
        ts=b.simulate(bid,ask,detect2(bid,e20,e50,a14,a50,rv,p),2.25,24,0.0)
        ym=[b.metrics(sub(ts,a,z,bid)) for a,z in years]; dev=b.metrics(sub(ts,'2022-08-27','2025-08-27',bid))
        if min(x['trades'] for x in ym)<8 or dev['trades']<30: continue
        if min(x['expectancy_r'] for x in ym)<0.03 or dev['expectancy_r']<0.22 or dev['pf']<1.5: continue
        mn=min(x['expectancy_r'] for x in ym); sd=statistics.pstdev([x['expectancy_r'] for x in ym])
        score=dev['expectancy_r']+0.007*min(dev['trades'],55)+0.16*mn-0.08*sd+0.03*math.log(max(dev['pf'],1))-0.015*dev['max_dd_r']
        C.append((score,p,ym,dev))
    C.sort(reverse=True,key=lambda x:x[0])
    if not C: raise RuntimeError('no stable V6 candidates')
    chosen=next((x for x in C[:100] if x[3]['trades']>=36),C[0])
    score,p,ym,dev=chosen
    ev=detect2(bid,e20,e50,a14,a50,rv,p); ts=b.simulate(bid,ask,ev,2.25,24,0.0)
    external=sub(ts,'2021-08-27','2022-08-27',bid)
    recent=sub(ts,'2025-08-27','2026-08-27',bid)
    latest2=sub(ts,'2024-08-27','2026-08-27',bid)
    full4=sub(ts,'2022-08-27','2026-08-27',bid)
    summary={'data_source':'Dukascopy JForex BID+ASK M15 aggregated H1','selection_policy':'V6 parameters selected on 2022-08-27～2025-08-26 only. 2021-08-27～2022-08-26 is new external prior validation. 2025-08-27～2026-08-26 is recent revalidation but is no longer untouched due to prior V5 inspection.','selected_params':p,'target_r':2.25,'max_hold_hours':24,'dev_years':[fm(x) for x in ym],'development_3y':fm(dev),'external_2021_22':fm(b.metrics(external)),'recent_2025_26':fm(b.metrics(recent)),'latest_2y':fm(b.metrics(latest2)),'full_2022_26':fm(b.metrics(full4)),'top_candidates':[{'score':round(x[0],4),'params':x[1],'years':[fm(y) for y in x[2]],'dev':fm(x[3])} for x in C[:10]]}
    print('=== V6 SUMMARY ==='); print(json.dumps(summary,ensure_ascii=False,indent=2))
    # Latest 2y viewer
    si=next(i for i,x in enumerate(bid) if x.dt>=datetime(2024,8,27)); ei=next((i for i,x in enumerate(bid) if x.dt>=datetime(2026,8,27)),len(bid)); cb=bid[si:ei]
    cid='gbpjpy_h1_flush_recovery_v6_regime'
    def cj(x): return {'time':x.dt.isoformat(timespec='seconds')+'+00:00','open':round(x.open,6),'high':round(x.high,6),'low':round(x.low,6),'close':round(x.close,6),'volume':round(x.volume,4)}
    chart={'id':cid,'symbol':'GBPJPY','timeframe':'H1','period':'2024-08-27 ～ 2026-08-26','candles':[cj(x) for x in cb],'overlays':[{'kind':'line','label':'EMA20','values':[round(x,6) for x in e20[si:ei]]},{'kind':'line','label':'EMA50','values':[round(x,6) for x in e50[si:ei]]}],'panes':[{'label':'ATR14','series':[{'kind':'line','label':'ATR14','values':[round(x,6) for x in a14[si:ei]]}]},{'label':'Volume','series':[{'kind':'histogram','label':'H1 Volume','values':[round(x.volume,4) for x in cb]}]},{'label':'RVOL20','levels':[p['rvol_min'],1.0],'series':[{'kind':'line','label':'RVOL20','values':[None if x is None else round(x,6) for x in rv[si:ei]]}]},{'label':'ATR14/ATR50','levels':[p['vol_ratio_min'],p['vol_ratio_max']],'series':[{'kind':'line','label':'Vol Ratio','values':[round(a14[i]/a50[i],6) if a50[i]>0 else None for i in range(si,ei)]}]}]}
    vt=[]
    for no,t in enumerate(latest2,1):
        e=t['event']; nt={'no':no,'chart_id':cid,'side':'BUY','entry_i':t['entry_i']-si,'exit_i':t['exit_i']-si,'entry_price':round(t['entry_price'],6),'exit_price':round(t['exit_price'],6),'stop':round(t['stop'],6),'target':round(t['target'],6),'r':round(t['r'],6),'result':t['result'],'confidence':None,'setup':'Flush Recovery V6 Regime','note':f"RVOL={e['flush_rvol']:.2f}, ATR比={e['vol_ratio']:.2f}, Trend={e['trend_strength']:.2f}, Slope={e['slope_strength']:.2f}, Reject={e['flush_rejection']:.2f}, BOvol={e['breakout_rvol']:.2f}"}
        if 0<=nt['entry_i']<=nt['exit_i']<len(cb): vt.append(nt)
    viewer={'meta':{'report_title':'GBPJPY H1 Flush Recovery V6 Regime','status':'検証済み'},'strategy':{'strategy_id':'GBPJPY_H1_FLUSH_RECOVERY_V6_REGIME','name':'Flush Recovery V6 Regime + Volume + Volatility','hypothesis':'Sweep/Flush後の再上昇は、相対出来高・適度なボラティリティ・トレンド強度・回復/ブレイク時の参加継続が揃うほど安定しやすい。','entry_logic':[json.dumps(p,ensure_ascii=False),'全条件はEntry前に確定','BUYはASK始値'],'exit_logic':['SL=Flush安値','TP=2.25R','最大24時間','同一H1足でSL/TP両方ならSL先着'],'future_tests':['MT5 broker tick volume再検証','将来期間の継続ウォークフォワード']},'charts':[chart],'trades':vt,'notes':[json.dumps(summary,ensure_ascii=False)]}
    (OUT/'GBPJPY_H1_FlushRecovery_V6_Regime_2y.json').write_text(json.dumps(viewer,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (OUT/'GBPJPY_H1_FlushRecovery_V6_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
