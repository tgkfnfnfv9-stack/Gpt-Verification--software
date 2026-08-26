'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const sample=fs.readFileSync(path.join(root,'samples/GPT出力データ_サンプル.json'),'utf8');

// Minimal async IndexedDB boundary double. Real IDB is also checked on the published page.
function fakeStorage(initial){
  const copy=value=>value===undefined?undefined:JSON.parse(JSON.stringify(value));
  const state={record:copy(initial),failRead:false,failWrite:false,holdRead:false,holdWrite:false,writes:0};
  let queue=Promise.resolve();
  const db={objectStoreNames:{contains:()=>true},createObjectStore(){},close(){},transaction(name,mode){
    const ops=[];let staged,aborted=false;
    const tx={abort(){aborted=true},objectStore(){return {
      get(){const request={};ops.push(()=>{request.result=copy(state.record);request.onsuccess?.()});return request},
      put(value){staged=copy(value);return {}}
    }}};
    queue=queue.then(async()=>{
      if(mode==='readonly'&&state.holdRead)await new Promise(resolve=>state.releaseRead=resolve);
      if(mode==='readonly'&&state.failRead){tx.error=new Error('read unavailable');tx.onabort?.();return}
      while(ops.length)ops.shift()();
      if(mode==='readwrite'&&state.holdWrite)await new Promise(resolve=>state.releaseWrite=resolve);
      if(aborted){tx.onabort?.();return}
      if(mode==='readwrite'&&(++state.writes===state.failWriteNumber||state.failWrite)){tx.error=new Error('quota exceeded');tx.onabort?.();return}
      if(mode==='readwrite')state.record=staged;
      tx.oncomplete?.();
    });
    return tx;
  }};
  return {state,open(){const request={};queueMicrotask(()=>{request.result=db;request.onsuccess?.()});return request}};
}
const flushTasks=async()=>{for(let i=0;i<25;i++)await Promise.resolve()};
// Exercise the actual inline application and registered handlers, without browser dependencies.
// Canvas is a drawing stub: these tests do not certify real-browser gesture delivery or layout.
function setup(filename,storage){
  const elements=new Map(),windowListeners=new Map();
  const doc={activeElement:null};
  const win={scrollX:0,scrollY:420,scrollTo(x,y){this.scrollX=x;this.scrollY=y},addEventListener(name,fn){windowListeners.set(name,fn)}};
  const drawCalls=[],drawingStack=[];
  const drawing=new Proxy({}, {get:(obj,key)=>obj[key]??(key==='measureText'?text=>({width:Array.from(String(text)).length*7}):(...args)=>{
    drawCalls.push({method:key,args,stroke:obj.strokeStyle,fill:obj.fillStyle,font:obj.font});
    if(key==='save')drawingStack.push({...obj});
    if(key==='restore'){const saved=drawingStack.pop();if(saved){for(const property of Object.keys(obj))delete obj[property];Object.assign(obj,saved)}}
  }),set:(obj,key,value)=>(obj[key]=value,true)});
  function element(id){
    if(elements.has(id))return elements.get(id);
    const listeners=new Map(),captures=new Set(),classes=new Set();
    const e={innerHTML:'',textContent:'',style:{},dataset:{},disabled:false,value:'',className:'',
      classList:{add(x){classes.add(x)},remove(x){classes.delete(x)},contains:x=>classes.has(x),toggle(x,on){if(on)classes.add(x);else classes.delete(x)}},
      parentNode:null,
      appendChild(child){child.parentNode=this},after(child){child.parentNode=this.parentNode},
      focus(){doc.activeElement=this},click(){this.clickCount=(this.clickCount||0)+1},
      getAttribute(name){if(name==='style')return Object.keys(this.style).length?JSON.stringify(this.style):null;return null},
      setAttribute(name,value){if(name==='style'){for(const key of Object.keys(this.style))delete this.style[key];Object.assign(this.style,JSON.parse(value))}},
      removeAttribute(name){if(name==='style')for(const key of Object.keys(this.style))delete this.style[key]},
      open:false,showModal(){this.open=true},close(){this.open=false;for(const {fn} of listeners.get('close')||[])fn({})},
      addEventListener(name,fn,options){if(!listeners.has(name))listeners.set(name,[]);listeners.get(name).push({fn,options})},
      getBoundingClientRect:()=>({width:id==='equity'?300:400,height:id==='equity'?170:710,left:20,top:0}),
      getContext:()=>drawing,
      setPointerCapture:id=>captures.add(id),hasPointerCapture:id=>captures.has(id),releasePointerCapture:id=>captures.delete(id),
      listeners,captures};
    elements.set(id,e);return e;
  }
  Object.assign(doc,{body:element('body'),getElementById:element,querySelectorAll:()=>[]});
  doc.activeElement=element('openFullscreen');
  element('chartWrap').parentNode=element('chartPlaceholder').parentNode=element('chartCard');
  const context=vm.createContext({document:doc,window:win,devicePixelRatio:1,
    console:{warn(){}},confirm:()=>true,indexedDB:storage});
  const run=code=>vm.runInContext(code,context);
  const html=fs.readFileSync(process.env.VIEWER_HTML||path.join(root,filename),'utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  run(script);
  const chart=element('chart');
  function fire(type,id=1,x=190,y=100,extra={},target=chart){
    let prevented=false;
    const e={pointerId:id,pointerType:'touch',button:0,clientX:x,clientY:y,deltaY:100,preventDefault(){prevented=true},...extra};
    const handlers=target.listeners.get(type)||[];
    assert.ok(handlers.length,`${type} must have a registered handler`);
    for(const {fn} of handlers)fn(e);
    return {prevented};
  }
  const view=()=>JSON.parse(run('JSON.stringify(view)'));
  const span=()=>{const v=view();return v.end-v.start};
  async function load(){context.files=[{name:'sample.json',type:'application/json',text:async()=>sample}];await run('loadJsonFiles(files)');run('view={start:10,end:50};drawChart()')}
  return {run,context,element,chart,fire,drawCalls,touch:(type,points=[],extra={})=>fire(type,1,0,0,{cancelable:true,targetTouches:points.map(([identifier,clientX,clientY=100])=>({identifier,clientX,clientY})),...extra}),ready:run('storageReady'),axisFire:(type,id=7,x=390,y=100,extra={})=>fire(type,id,x,y,extra,element('priceAxis')),view,span,load,html,doc,win,windowEvent:name=>windowListeners.get(name)(),dialogEvent(name){let prevented=false;for(const {fn} of element('chartDialog').listeners.get(name)||[])fn({preventDefault(){prevented=true}});return prevented}};
}
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);

for(const filename of ['index.html','report.html']){
  test(`${filename}: single finger pans and clamps to both ends`,async()=>{
    const h=setup(filename);await h.load();
    h.fire('pointerdown');assert.equal(h.chart.captures.size,0);
    h.fire('pointermove',1,230);assert.ok(h.chart.captures.has(1));near(h.view().start,5);near(h.span(),40);
    h.fire('pointermove',1,10000);near(h.view().start,0);
    h.fire('pointermove',1,-10000);near(h.view().end,63);
    h.fire('pointerup');assert.equal(h.run('drag'),null);assert.equal(h.chart.captures.size,0);
    const ended=h.view();h.fire('pointermove',1,250);assert.deepEqual(h.view(),ended);
  });
  test(`${filename}: pinch zoom anchors the moving midpoint`,async()=>{
    const h=setup(filename);await h.load();h.run('openChartFullscreen()');
    const candleAt=x=>h.view().start+(x-30)/320*h.span();
    const anchor=candleAt(210);
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);
    h.fire('pointermove',1,90);h.fire('pointermove',2,330);
    near(h.span(),40*160/240);near(candleAt(210),anchor);
    h.fire('pointermove',1,106);h.fire('pointermove',2,346);
    near(candleAt(226),anchor);
    h.fire('pointermove',1,146);h.fire('pointermove',2,306);
    near(h.span(),40);near(candleAt(226),anchor);
  });
  test(`${filename}: vertical pinch and extreme distances stay finite`,async()=>{
    const h=setup(filename);await h.load();h.run('openChartFullscreen()');
    h.fire('pointerdown',1,190,100);h.fire('pointerdown',2,190,200);
    h.fire('pointermove',2,190,300);near(h.span(),20);
    h.fire('pointermove',2,190,100000);near(h.span(),5);
    h.fire('pointermove',2,190,100);near(h.span(),63);
    assert.ok(Number.isFinite(h.view().start)&&Number.isFinite(h.view().end));
  });
  test(`${filename}: two fingers to one rebases without a jump`,async()=>{
    const h=setup(filename);await h.load();h.run('openChartFullscreen()');
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);h.fire('pointermove',2,330);
    const before=h.view();h.fire('pointerup',2,330);assert.deepEqual(h.view(),before);
    h.fire('lostpointercapture',2,330);assert.deepEqual(h.view(),before);
    h.fire('pointermove',1,130);assert.deepEqual(h.view(),before);
    h.fire('pointermove',1,146);near(h.view().start,before.start-16/320*(before.end-before.start));
  });
  test(`${filename}: cancel, lost capture and blur cannot leave a stuck drag`,async()=>{
    const h=setup(filename);await h.load();
    for(const event of ['pointercancel','lostpointercapture']){
      h.fire('pointerdown');h.fire(event);assert.equal(h.run('drag'),null);assert.equal(h.run('chartPointers.size'),0);
      const v=h.view();h.fire('pointermove',1,250);assert.deepEqual(h.view(),v);
    }
    h.fire('pointerdown',1);h.fire('pointerdown',2);h.windowEvent('blur');
    assert.equal(h.run('chartPointers.size'),0);assert.equal(h.chart.captures.size,0);
  });
  test(`${filename}: chart changes, trade navigation, full view and resize reset gestures`,async()=>{
    const h=setup(filename);await h.load();
    for(const action of [()=>h.run('switchChart(1)'),()=>h.run('focusTrade(0)'),()=>h.element('allView').onclick(),()=>h.windowEvent('resize')]){
      h.fire('pointerdown');action();assert.equal(h.run('chartPointers.size'),0);assert.equal(h.run('drag'),null);
      const v=h.view();h.fire('pointermove',1,240);assert.deepEqual(h.view(),v);
    }
  });
  test(`${filename}: mouse drag, wheel and tooltip still work`,async()=>{
    const h=setup(filename);await h.load();
    h.fire('pointerdown',1,190,100,{pointerType:'mouse',button:2});assert.equal(h.run('drag'),null);
    h.fire('pointerdown',1,190,100,{pointerType:'mouse'});h.fire('pointermove',1,230,100,{pointerType:'mouse'});near(h.view().start,5);
    h.fire('pointerup',1,230,100,{pointerType:'mouse'});
    const old=h.span();assert.ok(h.fire('wheel',1,190,100,{deltaY:-100}).prevented);assert.ok(h.span()<old);
    h.fire('mousemove',1,190,100,{pointerType:'mouse'});assert.equal(h.element('tooltip').style.display,'block');
  });
  test(`${filename}: empty and one-candle datasets remain safe`,async()=>{
    const h=setup(filename);h.fire('pointerdown');h.fire('pointermove');assert.equal(h.run('drag'),null);
    assert.equal(h.fire('wheel').prevented,false);
    await h.load();h.run('DATA.charts[0].candles=DATA.charts[0].candles.slice(0,1);DATA.trades=[];switchChart(0)');
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);h.fire('pointermove',2,330);
    assert.deepEqual(h.view(),{start:0,end:0});
    h.run('clearAllDatasets()');assert.equal(h.run('DATA'),null);assert.equal(h.chart.captures.size,0);
  });
  test(`${filename}: vertical and diagonal swipes leave the chart alone`,async()=>{
    const h=setup(filename);await h.load();
    for(const [x,y] of [[195,140],[215,130],[210,125],[190,60]]){
      const before=h.view();h.fire('pointerdown',1,190,100);
      assert.equal(h.fire('pointermove',1,193,103).prevented,false);assert.deepEqual(h.view(),before);
      assert.equal(h.fire('pointermove',1,x,y).prevented,false);assert.deepEqual(h.view(),before);
      assert.equal(h.run('normalTouch.axis'),'y');assert.equal(h.chart.captures.size,0);
      h.fire('pointermove',1,300,y);assert.deepEqual(h.view(),before);
      h.fire('pointerup');
    }
  });
  test(`${filename}: normal pointer pinch zooms time and waits for all fingers to lift`,async()=>{
    const h=setup(filename);await h.load();const before=h.view();
    h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);
    h.fire('pointermove',1,90);h.fire('pointermove',2,330);assert.ok(h.span()<before.end-before.start);const zoomed=h.view();
    h.fire('pointerup',2);h.fire('pointermove',1,180);assert.deepEqual(h.view(),zoomed);
    h.fire('pointerup',1);h.run('setChartView(10,40)');h.fire('pointerdown',1,190);h.fire('pointermove',1,230);near(h.view().start,5);
  });
  test(`${filename}: fullscreen preserves view and restores scroll, styles and focus`,async()=>{
    const h=setup(filename);await h.load();
    h.doc.body.style.background='red';const before=h.view();
    h.element('openFullscreen').onclick();assert.equal(h.run('chartFullscreen'),true);
    assert.ok(h.element('chartDialog').open);assert.ok(h.doc.body.classList.contains('chart-modal-open'));
    assert.equal(h.element('chartWrap').parentNode,h.element('fullscreenHost'));assert.deepEqual(h.view(),before);
    assert.equal(h.doc.activeElement,h.element('closeFullscreen'));
    h.element('fullZoomIn').onclick();const zoomed=h.view();near(h.span(),30);
    h.fire('pointerdown');h.win.scrollY=0;h.element('closeFullscreen').onclick();
    assert.equal(h.run('chartFullscreen'),false);assert.equal(h.run('chartPointers.size'),0);
    assert.equal(h.element('chartDialog').open,false);assert.equal(h.win.scrollY,420);
    assert.equal(h.doc.body.style.background,'red');assert.equal(h.doc.body.style.top,undefined);
    assert.equal(h.doc.body.classList.contains('chart-modal-open'),false);
    assert.equal(h.element('chartWrap').parentNode,h.element('chartCard'));
    assert.equal(h.doc.activeElement,h.element('openFullscreen'));assert.deepEqual(h.view(),zoomed);
    h.element('openFullscreen').onclick();assert.deepEqual(h.view(),zoomed);
    assert.equal(h.dialogEvent('cancel'),true);assert.equal(h.run('chartFullscreen'),false);assert.equal(h.win.scrollY,420);
  });
  test(`${filename}: zoom buttons, empty state and clearing fullscreen`,async()=>{
    const h=setup(filename);h.element('openFullscreen').onclick();assert.equal(h.run('chartFullscreen'),false);
    assert.equal(h.element('zoomIn').disabled,true);await h.load();
    h.element('zoomIn').onclick();near(h.span(),30);h.element('zoomOut').onclick();near(h.span(),40);
    h.element('allView').onclick();near(h.span(),63);
    h.element('openFullscreen').onclick();h.element('fullZoomIn').onclick();assert.ok(h.span()<63);
    h.element('fullAllView').onclick();near(h.span(),63);
    h.run('clearAllDatasets()');assert.equal(h.run('DATA'),null);assert.equal(h.run('chartFullscreen'),false);
    assert.equal(h.doc.body.classList.contains('chart-modal-open'),false);assert.equal(h.win.scrollY,420);
  });
  test(`${filename}: resize preserves full-screen view and small canvas geometry`,async()=>{
    const h=setup(filename);await h.load();h.run('openChartFullscreen()');h.element('fullZoomIn').onclick();
    const before=h.view();h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);h.windowEvent('resize');
    assert.equal(h.run('chartPointers.size'),0);assert.deepEqual(h.view(),before);assert.equal(h.run('chartFullscreen'),true);
    h.chart.getBoundingClientRect=()=>({width:700,height:150,left:0,top:0});h.run('drawChart()');
    assert.ok(h.chart._geom.mainH<150);assert.ok(h.chart._geom.mainH>0);
  });
  test(`${filename}: first import does not automatically zoom to a trade`,async()=>{
    const h=setup(filename);h.context.files=[{name:'test.json',type:'application/json',text:async()=>sample}];
    await h.run('loadJsonFiles(files)');assert.deepEqual(h.view(),{start:0,end:63});
    const before=h.view();h.run('focusTrade(1)');assert.deepEqual(h.view(),before);
  });
  test(`${filename}: time zoom, panning, trade focus and full view never autoscale price`,async()=>{
    const h=setup(filename);await h.load();
    const price=()=>JSON.parse(h.run('JSON.stringify(chartState().price)'));
    const initial=price();h.run('zoomChart(.5)');assert.deepEqual(price(),initial);
    const span=h.span();h.run('focusTrade(1)');near(h.span(),span);assert.deepEqual(price(),initial);
    h.run('setChartView(35,20)');assert.deepEqual(price(),initial);
    h.run('openChartFullscreen()');h.fire('pointerdown',1,130);h.fire('pointerdown',2,290);h.fire('pointermove',2,330);
    assert.ok(h.span()<20);assert.deepEqual(price(),initial);h.run('closeChartFullscreen()');
    h.element('allView').onclick();assert.deepEqual(price(),initial);
  });
  test(`${filename}: dragging the price scale affects price only in both modes`,async()=>{
    const h=setup(filename);await h.load();const view=h.view();
    for(const full of [false,true]){
      if(full)h.run('openChartFullscreen()');
      const original=h.run('chartState().price.hi-chartState().price.lo');
      h.axisFire('pointerdown',7,390,200);assert.ok(h.element('priceAxis').captures.has(7));
      h.axisFire('pointermove',7,390,100);assert.ok(h.run('chartState().price.hi-chartState().price.lo')<original);
      assert.deepEqual(h.view(),view);
      h.axisFire('pointermove',7,390,300);assert.ok(h.run('chartState().price.hi-chartState().price.lo')>original);
      h.axisFire('pointerup');assert.equal(h.run('priceDrag'),null);assert.equal(h.element('priceAxis').captures.size,0);
      const stopped=h.run('chartState().price.hi');h.axisFire('pointermove',7,390,-500);near(h.run('chartState().price.hi'),stopped);
    }
  });
  test(`${filename}: price-scale cancel, extreme drag and keyboard are safe`,async()=>{
    const h=setup(filename);await h.load();
    h.axisFire('pointerdown',7,390,200);h.axisFire('pointerdown',8,390,150);
    h.fire('pointerdown',1);assert.equal(h.run('chartPointers.size'),0);
    for(const y of [-1e9,1e9]){h.axisFire('pointermove',7,390,y);assert.ok(h.run('Number.isFinite(chartState().price.lo)&&Number.isFinite(chartState().price.hi)&&chartState().price.hi>chartState().price.lo'))}
    h.axisFire('pointercancel');assert.equal(h.run('priceDrag'),null);
    h.axisFire('pointerdown');h.windowEvent('resize');assert.equal(h.run('priceDrag'),null);
    const before=h.view();assert.ok(h.axisFire('keydown',7,390,100,{key:'Home'}).prevented);
    const span=h.run('chartState().price.hi-chartState().price.lo');h.axisFire('keydown',7,390,100,{key:'ArrowUp'});
    assert.ok(h.run('chartState().price.hi-chartState().price.lo')<span);assert.deepEqual(h.view(),before);
  });
  test(`${filename}: price fit is explicit and only uses the visible candles`,async()=>{
    const h=setup(filename);await h.load();
    const hi=h.run('chartState().price.hi');h.run('currentChart().candles[45].high=10000;drawChart()');near(h.run('chartState().price.hi'),hi);
    const before=h.view();h.element('fitPrice').onclick();assert.ok(h.run('chartState().price.hi')>10000);assert.deepEqual(h.view(),before);
    h.run('setChartView(0,10)');assert.ok(h.run('chartState().price.hi')>10000);
    h.element('fitPrice').onclick();assert.ok(h.run('chartState().price.hi')<10000);
  });
  test(`${filename}: each chart and dataset retains its own time and price ranges`,async()=>{
    const h=setup(filename);await h.load();h.run('zoomChart(.5)');h.axisFire('pointerdown');h.axisFire('pointermove',7,390,30);h.axisFire('pointerup');
    const expected=h.run('JSON.stringify(chartState())');h.run('switchChart(1);switchChart(0)');assert.equal(h.run('JSON.stringify(chartState())'),expected);
    await h.run('loadJsonFiles(files)');assert.equal(h.run('DATASETS.length'),2);assert.notEqual(h.run('JSON.stringify(chartState())'),expected);
    h.run('activateDataset(0)');assert.equal(h.run('JSON.stringify(chartState())'),expected);
    h.run('openChartFullscreen();closeChartFullscreen()');h.windowEvent('resize');assert.equal(h.run('JSON.stringify(chartState())'),expected);
  });
  test(`${filename}: clearing cancels pending and queued imports without blocking fresh reads`,async()=>{
    const h=setup(filename);await h.ready;let finish;
    h.context.slow=[{name:'slow.json',text:()=>new Promise(resolve=>{finish=resolve})}];
    h.context.fast=[{name:'fresh.json',text:async()=>sample}];
    const old=h.run('loadJsonFiles(slow)');await Promise.resolve();await Promise.resolve();
    const queued=h.run('loadJsonFiles(fast)');assert.equal(h.element('clearAllDataBtn').disabled,false);
    h.run('clearAllDatasets()');assert.equal(h.run('DATASETS.length'),0);
    await h.run('loadJsonFiles(fast)');assert.equal(h.run('DATASETS.length'),1);
    const status=h.element('fileStatus').textContent;finish(sample);await Promise.all([old,queued]);
    assert.equal(h.run('DATASETS.length'),1);assert.equal(h.run('DATASETS[0].sourceName'),'fresh.json');
    assert.equal(h.element('fileStatus').textContent,status);assert.equal(h.run('importPending'),0);
  });
  test(`${filename}: simultaneous import batches retain selection order`,async()=>{
    const h=setup(filename);await h.ready;let finish;
    h.context.first=[{name:'first.json',text:()=>new Promise(resolve=>{finish=resolve})}];
    h.context.second=[{name:'second.json',text:async()=>sample}];
    const first=h.run('loadJsonFiles(first)'),second=h.run('loadJsonFiles(second)');await Promise.resolve();await Promise.resolve();
    assert.equal(h.run('DATASETS.length'),0);finish(sample);await Promise.all([first,second]);
    assert.equal(h.run('DATASETS.map(x=>x.sourceName).join(",")'),'first.json,second.json');
    assert.equal(h.run('activeDatasetIndex'),1);assert.equal(h.run('importPending'),0);
  });
  test(`${filename}: malformed records and nonfinite trade results are rejected before registration`,async()=>{
    const h=setup(filename);
    const mutations=[d=>d.strategy='oops',d=>d.meta=[],d=>d.trades[0].steps=[null],d=>d.trades[0]=null,
      d=>d.trades[0].r='1e309',d=>d.trades.forEach(t=>t.r=1e308)];
    h.context.files=mutations.map((mutate,i)=>{const d=JSON.parse(sample);mutate(d);return {name:`bad${i}.json`,text:async()=>JSON.stringify(d)}});
    h.context.files.push({name:'good.json',text:async()=>sample});await h.run('loadJsonFiles(files)');
    assert.equal(h.run('DATASETS.length'),1);assert.equal(h.run('DATASETS[0].sourceName'),'good.json');
    assert.match(h.element('fileStatus').textContent,/6件エラー/);h.run('focusTrade(0);drawChart();renderStrategy()');
  });
  test(`${filename}: missing or inconsistent OHLC is not silently converted to zero`,async()=>{
    const h=setup(filename);
    for(const value of [null,'','   ',true,{},'1e309']){
      const d=JSON.parse(sample);d.charts[0].candles[0].open=value;h.context.raw=d;
      assert.throws(()=>h.run('normalizeData(raw)'),/OHLC/);
    }
    for(const key of ['high','low']){
      const d=JSON.parse(sample);d.charts[0].candles[0][key]=key==='high'?-10000:10000;h.context.raw=d;
      assert.throws(()=>h.run('normalizeData(raw)'),/OHLC/);
    }
    const d=JSON.parse(sample);Object.assign(d.charts[0].candles[0],{open:0,high:1,low:-1,close:0});
    d.trades[0].entry_price=null;h.context.raw=d;h.run('normalizeData(raw)');
    assert.equal(h.context.raw.charts[0].candles[0].open,0);
    assert.equal(h.context.raw.trades[0].entry_price,h.context.raw.charts[0].candles[d.trades[0].entry_i].close);
  });
  test(`${filename}: single-sign histograms use zero and are clipped to their own pane`,async()=>{
    const h=setup(filename);await h.load();
    for(const value of [-100,100]){
      h.run(`currentChart().panes=[{label:'MACD',zero_line:true,series:[{kind:'histogram',values:Array(64).fill(${value})}]}]`);
      h.drawCalls.length=0;h.run('drawChart()');
      const zero=h.drawCalls.find(c=>c.method==='lineTo'&&c.stroke==='#39424f').args[1];
      const pane=h.drawCalls.filter(c=>c.method==='rect').at(-1).args;
      assert.ok(zero>=pane[1]&&zero<=pane[1]+pane[3]);
      const bar=h.drawCalls.find(c=>c.method==='fillRect'&&c.fill===(value<0?'rgba(255,93,93,.65)':'rgba(47,191,113,.65)'));
      if(value<0)near(bar.args[1],zero);else near(bar.args[1]+bar.args[3],zero);
      assert.equal(h.drawCalls.filter(c=>c.method==='clip').length,2);
      assert.equal(h.drawCalls.filter(c=>c.method==='save').length,h.drawCalls.filter(c=>c.method==='restore').length);
    }
  });
  test(`${filename}: short landscape canvases and many panes never invert price or indicators`,async()=>{
    const h=setup(filename);await h.load();
    for(const height of [150,100,30])for(const count of [2,8]){
      h.chart.getBoundingClientRect=()=>({width:400,height,left:20,top:0});
      h.run(`currentChart().panes=Array.from({length:${count}},()=>({label:'RSI',min:0,max:100,levels:[0,100],series:[]}))`);
      h.drawCalls.length=0;h.run('drawChart()');
      assert.ok(h.run('cv._geom.Y(cv._geom.hi)<cv._geom.Y(cv._geom.lo)'));
      const levels=h.drawCalls.filter(c=>c.method==='lineTo'&&c.stroke==='#333b47');
      assert.equal(levels.length,count*2);
      for(let i=0;i<levels.length;i+=2)assert.ok(levels[i].args[1]>levels[i+1].args[1]);
    }
  });
  test(`${filename}: normal TouchEvents pinch overrides page zoom without double zooming`,async()=>{
    const h=setup(filename);await h.load();const price=h.run('JSON.stringify(chartState().price)');
    h.fire('pointerdown',1,130);assert.equal(h.touch('touchstart',[[10,130]]).prevented,false);
    h.fire('pointerdown',2,290);assert.equal(h.touch('touchstart',[[10,130],[20,290]]).prevented,true);
    h.fire('pointermove',2,330);near(h.span(),40);
    assert.equal(h.touch('touchmove',[[10,90],[20,330]]).prevented,true);near(h.span(),40*160/240);
    assert.equal(h.run('JSON.stringify(chartState().price)'),price);assert.equal(h.win.scrollY,420);
    h.fire('pointercancel');assert.ok(h.run('normalPinch'));
    h.touch('touchend',[[10,90]]);const view=h.view();h.touch('touchmove',[[10,190]]);assert.deepEqual(h.view(),view);
    h.touch('touchend');assert.equal(h.run('normalPinch'),null);
    assert.equal(h.chart.listeners.get('touchmove')[0].options.passive,false);
    assert.match(h.html,/#chart\{touch-action:pan-y;/);
  });
  test(`${filename}: native vertical scroll and cancelled touches cannot become a stuck pinch`,async()=>{
    const h=setup(filename);await h.load();const before=h.view();
    h.fire('pointerdown',1,190,100);h.fire('pointermove',1,192,140);h.fire('pointerdown',2,280,140);
    assert.equal(h.touch('touchstart',[[10,190,140],[20,280,140]]).prevented,false);assert.equal(h.run('normalPinch'),null);
    h.fire('pointercancel');assert.equal(h.touch('touchstart',[[10,130],[20,290]],{cancelable:false}).prevented,false);
    h.touch('touchstart',[[10,130],[20,290]]);h.touch('touchmove',[[10,90],[20,330]],{cancelable:false});
    assert.equal(h.run('normalPinch'),null);assert.deepEqual(h.view(),before);
    h.touch('touchstart',[[10,130],[20,290]]);h.touch('touchcancel');assert.equal(h.run('normalPinch'),null);
    h.touch('touchstart',[[10,130],[20,290]]);h.run('openChartFullscreen()');assert.equal(h.run('normalPinch'),null);
    assert.equal(h.touch('touchstart',[[10,130],[20,290]]).prevented,false);
  });
  test(`${filename}: imported datasets survive a fresh page instance and both entry points share storage`,async()=>{
    const db=fakeStorage(),h=setup(filename,db);await h.load();await h.load();
    assert.equal(db.state.record.datasets.length,2);assert.equal(h.element('storageStatus').dataset.state,'saved');
    h.run('activateDataset(0)');await h.element('saveDataBtn').onclick();
    const next=setup(filename==='index.html'?'report.html':'index.html',db);await next.ready;
    assert.equal(next.run('DATASETS.length'),2);assert.equal(next.run('DATA.charts.length'),2);
    assert.equal(next.run('DATA.trades.length'),4);assert.equal(next.run('activeDatasetIndex'),0);
    assert.match(next.element('storageStatus').textContent,/2件を復元/);
  });
  test(`${filename}: save status waits for transaction commit and preserves memory on write failure`,async()=>{
    const db=fakeStorage(),h=setup(filename,db);await h.ready;db.state.holdWrite=true;
    const loading=h.load();await flushTasks();assert.equal(h.element('storageStatus').dataset.state,'saving');
    assert.equal(db.state.record,undefined);db.state.holdWrite=false;db.state.releaseWrite();await loading;
    assert.equal(h.element('storageStatus').dataset.state,'saved');db.state.failWrite=true;
    await h.load();assert.equal(h.run('DATASETS.length'),2);assert.equal(db.state.record.datasets.length,1);
    assert.equal(h.element('storageStatus').dataset.state,'error');assert.equal(h.element('saveDataBtn').disabled,false);
    db.state.failWrite=false;await h.element('saveDataBtn').onclick();assert.equal(db.state.record.datasets.length,2);
  });
  test(`${filename}: chart, file and all-data deletion update durable storage`,async()=>{
    const db=fakeStorage(),h=setup(filename,db);await h.load();await h.load();
    h.run('removeChartFromActive(1)');await h.run('saveQueue');assert.equal(db.state.record.datasets[1].data.charts.length,1);
    h.run('removeDataset(0)');await h.run('saveQueue');assert.equal(db.state.record.datasets.length,1);
    h.run('clearAllDatasets()');await h.run('saveQueue');assert.equal(db.state.record.datasets.length,0);
    const next=setup(filename,db);await next.ready;assert.equal(next.run('DATASETS.length'),0);assert.equal(next.run('DATA'),null);assert.equal(next.element('clearAllDataBtn').disabled,true);
  });
  test(`${filename}: imports wait for restoration and clear invalidates a pending restore`,async()=>{
    const db=fakeStorage(),seed=setup(filename,db);await seed.load();
    db.state.holdRead=true;const h=setup(filename,db);const loading=h.load();await flushTasks();
    assert.equal(h.run('DATASETS.length'),0);db.state.holdRead=false;db.state.releaseRead();await loading;
    assert.equal(h.run('DATASETS.length'),2);assert.equal(db.state.record.datasets.length,2);
    db.state.holdRead=true;const cleared=setup(filename,db);await flushTasks();cleared.run('clearAllDatasets()');
    db.state.holdRead=false;db.state.releaseRead();await cleared.ready;await cleared.run('saveQueue');
    assert.equal(cleared.run('DATASETS.length'),0);assert.equal(db.state.record.datasets.length,0);
  });
  test(`${filename}: failed clearing after an in-flight save can be retried from the empty screen`,async()=>{
    const db=fakeStorage(),h=setup(filename,db);await h.ready;db.state.holdWrite=true;db.state.failWriteNumber=2;
    const loading=h.load();await flushTasks();h.run('clearAllDatasets()');
    db.state.holdWrite=false;db.state.releaseWrite();await loading;await h.run('saveQueue');
    assert.equal(h.run('DATASETS.length'),0);assert.equal(db.state.record.datasets.length,1);
    assert.equal(h.element('storageStatus').dataset.state,'error');
    assert.equal(h.element('saveDataBtn').disabled,false);assert.equal(h.element('clearAllDataBtn').disabled,false);
    await h.element('saveDataBtn').onclick();assert.equal(db.state.record.datasets.length,0);
    assert.equal(h.element('saveDataBtn').disabled,true);

  });
  test(`${filename}: stale tabs cannot overwrite another tab's saved changes`,async()=>{
    const db=fakeStorage(),seed=setup(filename,db);await seed.load();
    const a=setup(filename,db),b=setup(filename,db);await Promise.all([a.ready,b.ready]);
    await a.load();const revision=db.state.record.revision;await b.load();
    assert.equal(db.state.record.revision,revision);assert.equal(b.element('storageStatus').dataset.state,'error');
    assert.match(b.element('storageStatus').textContent,/別のタブ/);assert.equal(b.run('DATASETS.length'),2);
    b.run('clearAllDatasets()');await b.run('saveQueue');assert.equal(db.state.record.datasets.length,2);
  });
  test(`${filename}: corrupt saved entries are isolated and unavailable storage does not block import`,async()=>{
    const db=fakeStorage({version:1,datasets:[{id:'good',data:JSON.parse(sample)},{id:'bad',data:{}}]});
    const h=setup(filename,db);await h.ready;assert.equal(h.run('DATASETS.length'),1);
    assert.equal(h.element('storageStatus').dataset.state,'error');assert.equal(db.state.record.datasets.length,2);
    const corrupt=setup(filename,fakeStorage({version:99,datasets:[]}));await corrupt.ready;
    assert.equal(corrupt.element('storageStatus').dataset.state,'error');assert.equal(corrupt.element('clearAllDataBtn').disabled,false);
    const unavailable=setup(filename);await unavailable.load();assert.equal(unavailable.run('DATASETS.length'),1);
    assert.equal(unavailable.element('storageStatus').dataset.state,'error');assert.equal(unavailable.element('saveDataBtn').disabled,false);
  });
  test(`${filename}: fullscreen touch and normal mouse drag move price without resizing either axis`,async()=>{
    for(const full of [false,true]){
      const h=setup(filename);await h.load();if(full)h.run('openChartFullscreen()');
      const before=h.run('JSON.stringify(chartState().price)'),price=JSON.parse(before),v=h.view();
      const height=h.run('cv._geom.mainH-cv._geom.pad.t-cv._geom.pad.b'),pointerType=full?'touch':'mouse';
      h.fire('pointerdown',1,190,150,{pointerType});h.fire('pointermove',1,230,210,{pointerType});
      const after=JSON.parse(h.run('JSON.stringify(chartState().price)'));
      near(after.hi-after.lo,price.hi-price.lo);near(after.lo-price.lo,60*(price.hi-price.lo)/height);
      near(h.span(),v.end-v.start);near(h.view().start,5);h.fire('pointerup');
      const stopped=h.run('JSON.stringify(chartState().price)');h.fire('pointermove',1,230,310,{pointerType});
      assert.equal(h.run('JSON.stringify(chartState().price)'),stopped);
    }
  });
  test(`${filename}: normal two-finger translation pans vertically while one finger keeps native scrolling`,async()=>{
    const h=setup(filename);await h.load();const price=h.run('JSON.stringify(chartState().price)'),time=h.span();
    h.fire('pointerdown',1,190,100);h.fire('pointermove',1,190,160);
    assert.equal(h.run('JSON.stringify(chartState().price)'),price);h.fire('pointercancel');
    h.touch('touchstart',[[10,130,100],[20,290,100]]);h.touch('touchmove',[[10,150,150],[20,310,150]]);
    assert.ok(h.run('chartState().price.lo')>JSON.parse(price).lo);near(h.run('chartState().price.hi-chartState().price.lo'),JSON.parse(price).hi-JSON.parse(price).lo);
    near(h.span(),time);near(h.view().start,7.5);assert.equal(h.win.scrollY,420);
    const shifted=h.run('JSON.stringify(chartState().price)');h.touch('touchmove',[[10,110,150],[20,350,150]]);
    assert.ok(h.span()<time);assert.equal(h.run('JSON.stringify(chartState().price)'),shifted);
    h.touch('touchend',[[10,110,150]]);h.touch('touchmove',[[10,110,250]]);assert.equal(h.run('JSON.stringify(chartState().price)'),shifted);
    h.touch('touchend');assert.equal(h.run('normalPinch'),null);
  });
  test(`${filename}: full-screen vertical pan rebases across fingers and survives chart switches`,async()=>{
    const h=setup(filename);await h.load();h.run('openChartFullscreen()');
    h.fire('pointerdown',1,130,100);h.fire('pointerdown',2,290,100);h.fire('pointermove',1,130,140);h.fire('pointermove',2,290,140);
    const before=h.run('JSON.stringify(chartState().price)');h.fire('pointerup',2,290,140);h.fire('pointermove',1,130,140);
    assert.equal(h.run('JSON.stringify(chartState().price)'),before);h.fire('pointermove',1,130,160);
    assert.ok(h.run('chartState().price.lo')>JSON.parse(before).lo);h.fire('pointercancel');
    const shifted=h.run('JSON.stringify(chartState().price)');h.run('switchChart(1);switchChart(0);closeChartFullscreen()');
    assert.equal(h.run('JSON.stringify(chartState().price)'),shifted);
  });
  test(`${filename}: extreme vertical shifts never expand price scale or generate infinite coordinates`,async()=>{
    const h=setup(filename);await h.load();h.run('openChartFullscreen()');const span=h.run('chartState().price.hi-chartState().price.lo');
    h.fire('pointerdown',1,190,100);
    for(const y of [1e6,-1e6,1e30,Infinity]){
      h.fire('pointermove',1,190,y);near(h.run('chartState().price.hi-chartState().price.lo'),span);
      assert.ok(h.run('Number.isFinite(chartState().price.hi)&&Number.isFinite(chartState().price.lo)'));
    }
  });
  test(`${filename}: step labels have white text, opaque backing and fit inside the plot`,async()=>{
    const h=setup(filename);await h.load();
    h.run("cv.getContext('2d').font='11px original';DATA.trades[0].steps=[{i:20,label:'条件が成立'}];focusTrade(0)");
    assert.ok(h.drawCalls.some(c=>c.method==='fillText'&&c.args[0]==='条件が成立'&&c.fill==='#f8fafc'&&c.font.includes('600 12px')));
    h.drawCalls.length=0;
    h.run("cv.getContext('2d').font='11px original';drawStepLabel(cv.getContext('2d'),'非常に長いラベル文字の確認',48,40,{left:10,top:20,width:50,height:80})");
    const background=h.drawCalls.find(c=>c.method==='fillRect'&&c.fill==='#07111c');
    assert.ok(background.args[0]>=10&&background.args[0]+background.args[2]<=60);
    assert.ok(background.args[1]>=20&&background.args[1]+background.args[3]<=100);
    assert.ok(h.drawCalls.find(c=>c.method==='fillText').args[0].endsWith('…'));
    assert.equal(h.run("cv.getContext('2d').font"),'11px original');
    h.drawCalls.length=0;h.run("drawStepLabel(cv.getContext('2d'),'offscreen',30,-100,{left:10,top:20,width:50,height:80})");
    assert.equal(h.drawCalls.length,0);
  });
  test(`${filename}: native JSON picker reuses its directory identity on each selection`,async()=>{
    const h=setup(filename);await h.ready;const calls=[];h.win.isSecureContext=true;
    h.win.showOpenFilePicker=async options=>{calls.push(options);return [{name:'chosen.json',getFile:async()=>({text:async()=>sample})}]};
    h.run('updatePickerHelp()');await h.element('openDataBtn').onclick();await h.element('openDataBtn').onclick();
    assert.equal(h.run('DATASETS.length'),2);assert.equal(h.run('activeDatasetIndex'),1);
    assert.equal(calls.length,2);assert.equal(calls[0].id,calls[1].id);assert.ok(calls[0].id);
    assert.equal(calls[0].multiple,true);assert.equal(h.element('fileInput').clickCount,undefined);
    assert.equal(h.element('standardPickerBtn').hidden,false);
  });
  test(`${filename}: native picker cancellation is quiet and failed pickers offer an explicit fallback`,async()=>{
    const h=setup(filename);await h.load();h.win.isSecureContext=true;const previous=h.element('fileStatus').textContent;
    h.win.showOpenFilePicker=async()=>{throw Object.assign(new Error('cancelled'),{name:'AbortError'})};
    await h.element('openDataBtn').onclick();assert.equal(h.element('fileStatus').textContent,previous);assert.equal(h.run('DATASETS.length'),1);
    h.win.showOpenFilePicker=async()=>{throw new Error('blocked')};await h.element('openDataBtn').onclick();
    assert.match(h.element('fileStatus').textContent,/通常の選択/);assert.equal(h.element('standardPickerBtn').hidden,false);
    h.element('standardPickerBtn').onclick();assert.equal(h.element('fileInput').clickCount,1);
  });
  test(`${filename}: unsupported pickers use the normal chooser and unreadable selections stay isolated`,async()=>{
    const h=setup(filename);await h.ready;await h.element('openDataBtn').onclick();assert.equal(h.element('fileInput').clickCount,1);
    assert.match(h.element('pickerHelp').textContent,/指定できません/);h.win.isSecureContext=true;
    h.win.showOpenFilePicker=async()=>[{name:'broken.json',getFile:async()=>{throw new Error('removed')}},{name:'good.json',getFile:async()=>({text:async()=>sample})}];
    await h.element('openDataBtn').onclick();assert.equal(h.run('DATASETS.length'),1);assert.match(h.element('fileStatus').textContent,/1件エラー/);
  });
  test(`${filename}: clearing data while a native picker is pending cancels its late import`,async()=>{
    const h=setup(filename);await h.load();h.win.isSecureContext=true;let finish;
    h.win.showOpenFilePicker=()=>new Promise(resolve=>finish=resolve);const pending=h.element('openDataBtn').onclick();
    h.run('clearAllDatasets()');finish([{name:'late.json',getFile:async()=>({text:async()=>sample})}]);await pending;
    assert.equal(h.run('DATASETS.length'),0);
  });
  test(`${filename}: imports, deletion, filters, escaping and statistics regressions`,async()=>{
    const h=setup(filename);await h.load();await h.load();assert.equal(h.run('DATASETS.length'),2);
    assert.equal(h.run('DATA.summary.buy.trades'),2);assert.equal(h.run('DATA.summary.sell.trades'),2);
    assert.deepEqual(JSON.parse(h.run('JSON.stringify(calcStats([{r:2},{r:-1},{r:1.5},{r:-1}]))')),
      {trades:4,win_rate:50,expectancy_r:.375,profit_factor:1.75,max_dd_r:1,total_r:1.5});
    h.run("filter='SELL';renderRows()");assert.equal((h.element('tradeRows').innerHTML.match(/<tr /g)||[]).length,2);
    h.run('removeChartFromActive(1)');assert.equal(h.run('DATA.charts.length'),1);assert.equal(h.run('DATA.trades.length'),2);
    h.run('removeDataset(0)');assert.equal(h.run('DATASETS.length'),1);
    h.context.files=[{name:'bad.json',type:'application/json',text:async()=>'{'}];await h.run('loadJsonFiles(files)');assert.equal(h.run('DATASETS.length'),1);
    h.run('DATA.strategy.name="<img src=x onerror=alert(1)>";renderStrategy()');assert.ok(!h.element('strategyBody').innerHTML.includes('<img'));
    h.run('clearAllDatasets()');assert.equal(h.run('DATA'),null);
  });
}
test('Both entry points contain identical HTML',()=>assert.equal(fs.readFileSync(path.join(root,'index.html'),'utf8'),fs.readFileSync(path.join(root,'report.html'),'utf8')));
