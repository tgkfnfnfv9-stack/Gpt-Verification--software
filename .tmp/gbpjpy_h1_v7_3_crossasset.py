import csv, importlib.util, json, math, random, statistics, subprocess
from datetime import datetime
from pathlib import Path

spec=importlib.util.spec_from_file_location('m','/tmp/gbpjpy_h1_v8_macro.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
b=m.b
OUT=Path('results'); OUT.mkdir(exist_ok=True)
REPORT_START=datetime(2019,8,27); REPORT_END=datetime(2026,8,27)
SYMBOLS={'XAUUSD':'Gold','LIGHTCMDUSD':'WTI'}


def ensure_data(sym, side):
    p=Path(f'data/{sym}_M15_{side}.csv')
    if p.exists() and p.stat().st_size>1000: return p
    cmd=['dukascopy-go','download','--symbol',sym,'--timeframe','m15','--side',side,
         '--from','2018-08-27','--to','2026-08-27','--output',str(p),'--engine','jetta']
    subprocess.run(cmd,check=True)
    return p


def agg_hours(rows,hours):
    g={}
    for x in rows:
        h=(x.dt.hour//hours)*hours
        k=x.dt.replace(hour=h,minute=0,second=0,microsecond=0)
        g.setdefault(k,[]).append(x)
    out=[]
    for k in sorted(g):
        z=sorted(g[k],key=lambda q:q.dt)
        out.append(b.Bar(k,z[0].open,max(q.high for q in z),min(q.low for q in z),z[-1].close,sum(q.volume for q in z)))
    return out


def series_pack(bars):
    c=[x.close for x in bars]
    e20=b.ema(c,20); e50=b.ema(c,50)
    a14=b.atr(bars,14); a50=b.atr(bars,50)
    rv=b.rvol_series(bars,20)
    return e20,e50,a14,a50,rv


def valid_control_candidates(bars,e20,e50,a14,a50,events,tfh):
    blocked=set()
    radius=max(10,int(math.ceil(48/tfh)))
    for e in events:
        ii=e['entry_i']
        for j in range(max(0,ii-radius),min(len(bars),ii+radius+1)): blocked.add(j)
    out=[]
    p=m.V6P
    for ii in range(90,len(bars)-max(30,int(math.ceil(96/tfh)))):
        j=ii-1
        if ii in blocked: continue
        if not (REPORT_START<=bars[ii].dt<REPORT_END): continue
        if not (e20[j]>e50[j] and bars[j].close>e20[j]): continue
        aa=a14[j]
        if aa<=0 or a50[j]<=0: continue
        slope=(e50[j]-e50[max(0,j-p['slope_lb'])])/aa
        if slope<p['slope_strength_min']: continue
        vr=a14[j]/a50[j]
        if not (p['vol_ratio_min']<=vr<=p['vol_ratio_max']): continue
        if not b.session_ok(bars[j].dt.hour,p['session']): continue
        out.append(ii)
    return out


def matched_controls(bars,cands,events):
    unused=set(cands); chosen=[]
    byyear={}
    for i in cands: byyear.setdefault(bars[i].dt.year,[]).append(i)
    for e in events:
        ii=e['entry_i']; y=bars[ii].dt.year
        pool=[j for j in byyear.get(y,[]) if j in unused]
        if not pool:
            pool=[j for j in cands if j in unused]
        if not pool: break
        # nearest in calendar time, then closest hour-of-day
        j=min(pool,key=lambda q:(abs((bars[q].dt-bars[ii].dt).total_seconds()),abs(bars[q].dt.hour-bars[ii].dt.hour)))
        unused.remove(j); chosen.append(j)
    return chosen


def event_metrics(bid,ask,a14,events,tfh):
    am={x.dt:x for x in ask}; fs=b.medspread(bid,ask)
    horizons=[6,12,24,48] if tfh==1 else [12,24,48,96]
    vals={h:[] for h in horizons}; pos={h:0 for h in horizons}
    mfe48=[]; mae48=[]; reach={1.0:0,2.0:0,2.5:0}; valid=0
    rows=[]
    for e in events:
        ii=e['entry_i']
        if not (REPORT_START<=bid[ii].dt<REPORT_END): continue
        if ii<=0: continue
        ab=am.get(bid[ii].dt); entry=ab.open if ab else bid[ii].open+fs
        atr=max(a14[ii-1],1e-12)
        stop=e['flush_low']-0.10*e['atr0']; risk=entry-stop
        if risk<=0: continue
        valid+=1
        rec={'entry_time':bid[ii].dt.isoformat(),'entry':entry,'atr':atr,'risk':risk}
        for h in horizons:
            nb=int(math.ceil(h/tfh)); z=min(len(bid)-1,ii+nb-1)
            r=(bid[z].close-entry)/atr
            vals[h].append(r); pos[h]+=1 if r>0 else 0
            rec[f'ret_{h}h_atr']=r
        nb48=int(math.ceil(48/tfh)); end=min(len(bid)-1,ii+nb48-1)
        hi=max(bid[z].high for z in range(ii,end+1)); lo=min(bid[z].low for z in range(ii,end+1))
        mfe48.append((hi-entry)/atr); mae48.append((entry-lo)/atr)
        hit_stop=False; hit={1.0:False,2.0:False,2.5:False}
        for z in range(ii,end+1):
            if bid[z].low<=stop: hit_stop=True; break
            for rr in hit:
                if not hit[rr] and bid[z].high>=entry+rr*risk: hit[rr]=True
        for rr in hit: reach[rr]+=1 if hit[rr] else 0
        rec['mfe48_atr']=(hi-entry)/atr; rec['mae48_atr']=(entry-lo)/atr
        rows.append(rec)
    out={'n':valid}
    for h in horizons:
        out[f'avg_ret_{h}h_ATR']=round(statistics.mean(vals[h]),3) if vals[h] else None
        out[f'positive_{h}h_pct']=round(100*pos[h]/len(vals[h]),1) if vals[h] else None
    out['MFE48_ATR']=round(statistics.mean(mfe48),3) if mfe48 else None
    out['MAE48_ATR']=round(statistics.mean(mae48),3) if mae48 else None
    for rr in reach: out[f'{rr:g}R_before_stop_48h_pct']=round(100*reach[rr]/valid,1) if valid else None
    return out,rows


def control_metrics(bid,ask,a14,indices,tfh):
    am={x.dt:x for x in ask}; fs=b.medspread(bid,ask)
    horizons=[6,12,24,48] if tfh==1 else [12,24,48,96]
    vals={h:[] for h in horizons}; pos={h:0 for h in horizons}; mfe48=[]; mae48=[]
    for ii in indices:
        if ii<=0 or ii>=len(bid): continue
        ab=am.get(bid[ii].dt); entry=ab.open if ab else bid[ii].open+fs
        atr=max(a14[ii-1],1e-12)
        for h in horizons:
            nb=int(math.ceil(h/tfh)); z=min(len(bid)-1,ii+nb-1)
            r=(bid[z].close-entry)/atr; vals[h].append(r); pos[h]+=1 if r>0 else 0
        nb48=int(math.ceil(48/tfh)); end=min(len(bid)-1,ii+nb48-1)
        hi=max(bid[z].high for z in range(ii,end+1)); lo=min(bid[z].low for z in range(ii,end+1))
        mfe48.append((hi-entry)/atr); mae48.append((entry-lo)/atr)
    out={'n':len(indices)}
    for h in horizons:
        out[f'avg_ret_{h}h_ATR']=round(statistics.mean(vals[h]),3) if vals[h] else None
        out[f'positive_{h}h_pct']=round(100*pos[h]/len(vals[h]),1) if vals[h] else None
    out['MFE48_ATR']=round(statistics.mean(mfe48),3) if mfe48 else None
    out['MAE48_ATR']=round(statistics.mean(mae48),3) if mae48 else None
    return out


def yearly24(bid,ask,a14,events,tfh):
    am={x.dt:x for x in ask}; fs=b.medspread(bid,ask); d={}
    nb=int(math.ceil(24/tfh))
    for e in events:
        ii=e['entry_i']
        if not (REPORT_START<=bid[ii].dt<REPORT_END) or ii<=0: continue
        ab=am.get(bid[ii].dt); entry=ab.open if ab else bid[ii].open+fs
        z=min(len(bid)-1,ii+nb-1); atr=max(a14[ii-1],1e-12)
        d.setdefault(bid[ii].dt.year,[]).append((bid[z].close-entry)/atr)
    return [{'year':y,'n':len(v),'avg_ret24_ATR':round(statistics.mean(v),3),'positive24_pct':round(100*sum(x>0 for x in v)/len(v),1)} for y,v in sorted(d.items())]


def test_one(sym,label,tfh):
    print('TEST',sym,'H'+str(tfh))
    bp=ensure_data(sym,'bid'); ap=ensure_data(sym,'ask')
    rawb=b.load(bp); rawa=b.load(ap)
    bid=agg_hours(rawb,tfh); ask=agg_hours(rawa,tfh)
    e20,e50,a14,a50,rv=series_pack(bid)
    events=m.detect2(bid,e20,e50,a14,a50,rv,m.V6P)
    events=[e for e in events if REPORT_START<=bid[e['entry_i']].dt<REPORT_END]
    sig,sigrows=event_metrics(bid,ask,a14,events,tfh)
    cands=valid_control_candidates(bid,e20,e50,a14,a50,events,tfh)
    ctrls=matched_controls(bid,cands,events)
    ctl=control_metrics(bid,ask,a14,ctrls,tfh)
    edge24=None
    if sig.get('avg_ret_24h_ATR') is not None and ctl.get('avg_ret_24h_ATR') is not None:
        edge24=round(sig['avg_ret_24h_ATR']-ctl['avg_ret_24h_ATR'],3)
    edge48=None
    if sig.get('avg_ret_48h_ATR') is not None and ctl.get('avg_ret_48h_ATR') is not None:
        edge48=round(sig['avg_ret_48h_ATR']-ctl['avg_ret_48h_ATR'],3)
    mfe_edge=round(sig['MFE48_ATR']-ctl['MFE48_ATR'],3) if sig.get('MFE48_ATR') is not None and ctl.get('MFE48_ATR') is not None else None
    support='NO_SUPPORT'
    if edge24 is not None and edge24>=0.30 and sig.get('positive_24h_pct',0)>=55 and mfe_edge is not None and mfe_edge>0:
        support='STRONG_SUPPORT'
    elif edge24 is not None and edge24>=0.10:
        support='PARTIAL_SUPPORT'
    out={'symbol':sym,'market':label,'timeframe':'H'+str(tfh),'period':'2019-08-27 to 2026-08-26',
         'entry_logic':'GBPJPY V7 technical entry transferred unchanged: trend + sweep + flush + recovery + breakout + retest; next bar ASK open',
         'signal':sig,'matched_control':ctl,'edge24_ATR':edge24,'edge48_ATR':edge48,'MFE48_edge_ATR':mfe_edge,
         'yearly_signal_24h':yearly24(bid,ask,a14,events,tfh),'hypothesis_support':support}
    for r in sigrows:
        r.update({'symbol':sym,'market':label,'timeframe':'H'+str(tfh)})
    return out,sigrows


def main():
    allres=[]; allrows=[]
    for sym,label in SYMBOLS.items():
        for tfh in (1,4):
            res,rows=test_one(sym,label,tfh); allres.append(res); allrows.extend(rows)
    summary={
      'data_source':'Dukascopy JForex/Jetta via dukascopy-go v0.2.0; M15 BID+ASK+volume aggregated to H1/H4',
      'purpose':'Test the V7 entry hypothesis only on commodity CFDs, not V7 exit profitability.',
      'hypothesis':'In an uptrend, a liquidity sweep/flush followed by fast recovery, breakout and retest should show stronger subsequent upside than comparable trend-regime entries if the pattern captures genuine absorption/reaccumulation.',
      'control':'One-to-one calendar-near matched entries from the same year satisfying V7 trend/ATR/session regime but outside the V7 setup neighborhood.',
      'important_limit':'OHLC+broker volume cannot prove large-player intent. This tests the conditional price behavior implied by the hypothesis.',
      'results':allres
    }
    (OUT/'Commodity_XAU_WTI_V7_entry_H1_H4_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['symbol','market','timeframe','entry_time','entry','atr','risk','ret_6h_atr','ret_12h_atr','ret_24h_atr','ret_48h_atr','ret_96h_atr','mfe48_atr','mae48_atr']
    with open(OUT/'Commodity_XAU_WTI_V7_entry_H1_H4_signals.csv','w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader()
        for r in allrows: w.writerow(r)
    compact=[]
    for x in allres:
        compact.append({'market':x['market'],'tf':x['timeframe'],'n':x['signal']['n'],
          'sig24':x['signal'].get('avg_ret_24h_ATR'),'ctl24':x['matched_control'].get('avg_ret_24h_ATR'),'edge24':x['edge24_ATR'],
          'sig_pos24':x['signal'].get('positive_24h_pct'),'ctl_pos24':x['matched_control'].get('positive_24h_pct'),
          'sig48':x['signal'].get('avg_ret_48h_ATR'),'ctl48':x['matched_control'].get('avg_ret_48h_ATR'),'edge48':x['edge48_ATR'],
          'mfe48_edge':x['MFE48_edge_ATR'],'reach1R':x['signal'].get('1R_before_stop_48h_pct'),
          'reach2R':x['signal'].get('2R_before_stop_48h_pct'),'reach2.5R':x['signal'].get('2.5R_before_stop_48h_pct'),
          'support':x['hypothesis_support']})
    print('=== COMMODITY XAU/WTI V7 ENTRY-ONLY H1/H4 ===')
    print(json.dumps(compact,ensure_ascii=False,indent=2))
    print('=== YEARLY ===')
    for x in allres: print(x['market'],x['timeframe'],json.dumps(x['yearly_signal_24h'],ensure_ascii=False))

if __name__=='__main__': main()
