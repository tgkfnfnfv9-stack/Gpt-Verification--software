import csv, hashlib, json, math, random, statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

START=datetime(2019,8,28); EVAL_END=datetime(2025,8,28)
SPLITS={"DISCOVERY":(datetime(2019,8,28),datetime(2022,8,28)),"DEVELOPMENT":(datetime(2022,8,28),datetime(2024,8,28)),"OOS":(datetime(2024,8,28),datetime(2025,8,28))}
OUT=Path("results"); OUT.mkdir(exist_ok=True)

@dataclass
class QBar:
    dt: datetime; bo: float; bh: float; bl: float; bc: float
    ao: float; ah: float; al: float; ac: float; volume: float
    @property
    def o(self): return (self.bo+self.ao)/2
    @property
    def h(self): return (self.bh+self.ah)/2
    @property
    def l(self): return (self.bl+self.al)/2
    @property
    def c(self): return (self.bc+self.ac)/2

def norm(s): return ''.join(ch.lower() for ch in s if ch.isalnum())
def pick(fields,cands):
    m={norm(k):k for k in fields}
    for c in cands:
        if norm(c) in m:return m[norm(c)]
    for nk,k in m.items():
        for c in cands:
            if nk.endswith(norm(c)):return k
def pdt(x):
    s=str(x).strip().strip('"').replace('Z','+00:00')
    try:
        v=float(s)
        if v>1e12:return datetime.fromtimestamp(v/1000,tz=timezone.utc).replace(tzinfo=None)
        if v>1e9:return datetime.fromtimestamp(v,tz=timezone.utc).replace(tzinfo=None)
    except:pass
    d=datetime.fromisoformat(s)
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d

def load_side(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f); fs=r.fieldnames
        tk=pick(fs,['timestamp','time','date','datetime']); ok=pick(fs,['open']); hk=pick(fs,['high']); lk=pick(fs,['low']); ck=pick(fs,['close']); vk=pick(fs,['volume','tick_volume'])
        z={}
        for row in r:
            try:
                dt=pdt(row[tk]); o,h,l,c=map(float,(row[ok],row[hk],row[lk],row[ck])); v=float(row[vk]) if vk and row.get(vk) else 0
                if o>0 and h>=max(o,c) and l<=min(o,c):z[dt]=(o,h,l,c,v)
            except:pass
        return z

def load_pair(symbol):
    b=load_side(f'data/{symbol}_M15_bid.csv'); a=load_side(f'data/{symbol}_M15_ask.csv'); out=[]
    for dt in sorted(set(b)&set(a)):
        x,y=b[dt],a[dt]
        if y[0]>=x[0]:out.append(QBar(dt,*x[:4],*y[:4],x[4]))
    return out

def aggregate(src,minutes):
    if minutes==15:return src
    g={}; expected=minutes//15
    for x in src:
        minute=(x.hour*60+x.minute)//minutes*minutes
        key=x.dt.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(minutes=minute)
        g.setdefault(key,[]).append(x)
    out=[]
    for key,z in sorted(g.items()):
        z=sorted(z,key=lambda x:x.dt)
        if len(z)!=expected or any(z[i].dt!=key+timedelta(minutes=15*i) for i in range(expected)):continue
        out.append(QBar(key,z[0].bo,max(x.bh for x in z),min(x.bl for x in z),z[-1].bc,z[0].ao,max(x.ah for x in z),min(x.al for x in z),z[-1].ac,sum(x.volume for x in z)))
    return out

def decile(v,prev):
    if v is None or len(prev)<240:return None
    q=statistics.quantiles(prev,n=10,method='inclusive')
    return sum(v>=x for x in q)

def features(bars):
    n=len(bars); tr=[]
    for i,x in enumerate(bars):
        pc=bars[i-1].c if i else x.c; tr.append(max(x.h-x.l,abs(x.h-pc),abs(x.l-pc)))
    f=[None]*n; hist_atr=[]; hist_trend=[]; hist_spread=[]
    for i in range(n):
        if i<41:
            hist_atr.append(None);hist_trend.append(None);hist_spread.append(None);continue
        atr=sum(tr[i-14:i])/14; m40=statistics.median(tr[i-40:i]); net=bars[i-1].c-bars[i-8].c; path=sum(abs(bars[j].c-bars[j-1].c) for j in range(i-7,i)); eff=abs(net)/path if path else 0
        oldh=max(x.h for x in bars[i-20:i]); oldl=min(x.l for x in bars[i-20:i]); rng=bars[i].h-bars[i].l; d=1 if net>0 else (-1 if net<0 else 0)
        loc=((bars[i].c-bars[i].l)/rng if d==1 else (bars[i].h-bars[i].c)/rng) if rng>0 and d else 9
        ext=(bars[i].h>=oldh+.15*m40) if d==1 else ((bars[i].l<=oldl-.15*m40) if d==-1 else False)
        rec=(bars[i].c<=oldh-.05*m40) if d==1 else ((bars[i].c>=oldl+.05*m40) if d==-1 else False)
        sig=eff>=.65 and abs(net)>=1.5*m40 and ext and rng>=1.2*m40 and loc<=.25 and rec
        trend=abs(bars[i-1].c-bars[i-9].c)/atr if atr else None; spread=(bars[i-1].ao-bars[i-1].bo)/atr if atr else None
        va=[x for x in hist_atr[-240:] if x is not None]; vt=[x for x in hist_trend[-240:] if x is not None]; vs=[x for x in hist_spread[-240:] if x is not None]
        f[i]={"atr":atr,"m40":m40,"side":"SELL" if d==1 else "BUY","sig":sig,"da":decile(atr,va),"dt":decile(trend,vt),"ds":decile(spread,vs)}
        hist_atr.append(atr);hist_trend.append(trend);hist_spread.append(spread)
    return f

def outcome(bars,i,side,scale,h=3):
    en=i+1; ex=en+h
    if ex>=len(bars) or scale<=0:return None
    if side=='BUY':p=bars[ex].bo-bars[en].ao; mfe=max(x.bh for x in bars[en:ex])-bars[en].ao; mae=min(x.bl for x in bars[en:ex])-bars[en].ao
    else:p=bars[en].bo-bars[ex].ao; mfe=bars[en].bo-min(x.al for x in bars[en:ex]); mae=bars[en].bo-max(x.ah for x in bars[en:ex])
    return p/scale,mfe/scale,mae/scale,en,ex

def bootstrap(vals,n=2000):
    if not vals:return [None,None]
    rng=random.Random(20260828); ms=[]
    for _ in range(n):ms.append(sum(rng.choice(vals) for _ in vals)/len(vals))
    ms.sort();return [ms[int(.025*n)],ms[int(.975*n)]]

def cell(symbol,tf,bars):
    ft=features(bars); reuse={}; pairs=[]; signals=[]
    candidates=[i for i,x in enumerate(ft) if x and not x['sig'] and None not in (x['da'],x['dt'],x['ds']) and bars[i].dt<EVAL_END]
    for i,x in enumerate(ft):
        if not x or not x['sig'] or bars[i].dt>=EVAL_END or None in (x['da'],x['dt'],x['ds']):continue
        so=outcome(bars,i,x['side'],x['atr']);
        if not so:continue
        eligible=[]
        for j in candidates:
            if bars[j].dt.year!=bars[i].dt.year or bars[j].dt.hour//4!=bars[i].dt.hour//4 or abs((bars[j].dt-bars[i].dt).days)>60:continue
            if not (j+4<i-41 or j-41>i+4) or reuse.get(j,0)>=3:continue
            y=ft[j]; dist=abs(y['da']-x['da'])+abs(y['dt']-x['dt'])+abs(y['ds']-x['ds']); tie=hashlib.sha256(f'{symbol}|{tf}|{i}|{j}|20260828'.encode()).hexdigest();eligible.append((dist,tie,j))
        chosen=sorted(eligible)[:5]
        if len(chosen)<3:continue
        co=[]
        for _,__,j in chosen:
            z=outcome(bars,j,x['side'],ft[j]['atr'])
            if z:co.append(z[0]);reuse[j]=reuse.get(j,0)+1
        if len(co)<3:continue
        edge=so[0]-sum(co)/len(co);pairs.append((bars[i].dt,so[0],sum(co)/len(co),edge));signals.append((i,x,so))
    def summ(rows):
        if not rows:return {"status":"NON_ESTIMABLE","signals":0}
        e=[x[3] for x in rows];s=[x[1] for x in rows];c=[x[2] for x in rows]
        return {"status":"ESTIMABLE","signals":len(rows),"signal_mean_atr":sum(s)/len(s),"control_mean_atr":sum(c)/len(c),"mean_edge_atr":sum(e)/len(e),"median_edge_atr":statistics.median(e),"positive_edge_rate":sum(x>0 for x in e)/len(e),"bootstrap_95ci":bootstrap(e)}
    split={k:summ([x for x in pairs if a<=x[0]<b]) for k,(a,b) in SPLITS.items()}
    full=summ(pairs);full['splits']=split;full['instrument']=symbol;full['timeframe']=tf;full['data_rows']=len(bars);full['period']=[bars[0].dt.isoformat(),bars[-1].dt.isoformat()] if bars else []
    return full

def main():
    files=sorted(Path('data').glob('*_M15_bid.csv')); symbols=[p.name.split('_M15_')[0] for p in files if Path(str(p).replace('_bid.csv','_ask.csv')).exists()]
    results=[]; errors=[]
    for sym in symbols:
        try:
            base=load_pair(sym)
            for tf,m in [('M15',15),('H1',60),('H4',240)]:results.append(cell(sym,tf,aggregate(base,m)))
        except Exception as exc:errors.append({'instrument':sym,'error':type(exc).__name__+': '+str(exc)})
    ranked=sorted([x for x in results if x.get('status')=='ESTIMABLE'],key=lambda x:x.get('mean_edge_atr',-999),reverse=True)
    report={'strategy_id':'STRAT-PA-002','spec':'frozen-no-retuning','data_source':'Dukascopy JForex M15 BID+ASK via pinned dukascopy-go v0.2.0 on GitHub Actions','source_period':['2019-08-28','2026-08-28'],'evaluated_until_exclusive':'2025-08-28','final_holdout_2025_08_28_to_2026_08_28':'MASKED_NOT_EVALUATED','timeframes':['M15','H1','H4'],'matched_controls':'same instrument/timeframe/year/UTC4h; nearest prior-only ATR/trend/spread deciles; ±60 days; 5 requested/3 minimum; reuse cap 3','results':results,'ranked':ranked,'errors':errors}
    (OUT/'PA002_cross_market_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    viewer={'meta':{'report_title':'PA-002 FX・商品 横断Entry Edge検証','status':'検証済み（Entry研究・Final Holdout未開封）'},'strategy':{'strategy_id':'STRAT-PA-002','name':'Efficient Move Extreme Rejection','hypothesis':'効率的な先行方向への新高値・新安値更新が同一足で強く拒否された後、逆方向の3本先Returnに偏りがあるか。','entry_logic':['凍結済みPA-002 v1.0.0','Signal後の次足ASK/BIDでEntry','同条件Matched Controlと比較'],'exit_logic':['Entry研究のため3本後のBID/ASK Openで評価','1 ATRを尺度とした標準化Return'],'future_tests':['OANDA MT5履歴で再検証','Final Holdoutは前段Gate合格後のみ開封']},'charts':[],'trades':[],'notes':[json.dumps({'top_cells':ranked[:15],'errors':errors},ensure_ascii=False)]}
    (OUT/'PA002_cross_market_viewer.json').write_text(json.dumps(viewer,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'symbols':symbols,'cells':len(results),'estimable':len(ranked),'top':ranked[:5],'errors':errors},ensure_ascii=False,indent=2))
    if not ranked:raise RuntimeError('No estimable cells')

if __name__=='__main__':main()
