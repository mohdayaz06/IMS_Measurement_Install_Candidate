const {test}=require('node:test');const assert=require('node:assert/strict');const vm=require('node:vm');const fs=require('node:fs');const {webcrypto}=require('node:crypto');
function setup(){const items=new Map(),calls=[];const storage={getItem:k=>items.get(k)||null,setItem:(k,v)=>items.set(k,v),removeItem:k=>items.delete(k)};
 const w={localStorage:storage};vm.runInNewContext(fs.readFileSync('web/pixel.js','utf8'),{window:w,crypto:webcrypto,URL,Date,fetch:async(url,opts)=>{calls.push(JSON.parse(opts.body));return {ok:true,json:async()=>({status:'accepted'})};}});
 return {t:w.IMSAttribution.create({baseUrl:'https://tracking.example',tenant:'a'}),items,calls};}
test('no identity or event without analytics consent',async()=>{const {t,items,calls}=setup();await t.pageView('https://shop.example/?utm_source=meta','');assert.equal(items.size,0);assert.equal(calls.length,0);});
test('one touch per session and consent withdrawal clears identity',async()=>{const {t,calls,items}=setup();await t.consent(true,false);await t.pageView('https://shop.example/','');await t.pageView('https://shop.example/product','');assert.equal(calls.length,1);await t.consent(false);assert.equal(items.size,0);});
test('paid classification requires UTMs or Google ad click ID',async()=>{const {t,calls}=setup();await t.consent(true,true);await t.pageView('https://shop.example/?utm_source=meta&utm_medium=paid_social&utm_campaign=123','');assert.equal(calls[0].source,'meta');assert.equal(calls[0].campaign,'123');assert.equal(calls[0].marketing_consent,true);});
test('Shopify global order ID normalizes without creating value',async()=>{const {t,calls}=setup();await t.consent(true,true);await t.observeOrder('gid://shopify/Order/123');assert.equal(calls[0].order_id,'123');assert.equal(calls[0].revenue,undefined);});
test('Simpli.fi browser purchase fires only once with marketing permission',async()=>{
 const items=new Map(),requests=[];const storage={getItem:k=>items.get(k)||null,setItem:(k,v)=>items.set(k,v),removeItem:k=>items.delete(k)};
 class ImageMock{set src(url){requests.push(url);queueMicrotask(()=>this.onload());}}
 const w={localStorage:storage,Image:ImageMock};
 vm.runInNewContext(fs.readFileSync('web/pixel.js','utf8'),{window:w,crypto:webcrypto,URL,Date,setTimeout,clearTimeout,fetch:async()=>({ok:true,json:async()=>({status:'accepted'})})});
 const t=w.IMSAttribution.create({baseUrl:'https://tracking.example',tenant:'a',simpli:{type:'image',url:'https://i.simpli.fi/dpx?order={{order_id}}&value={{value}}'}});
 await t.consent(true,false);await t.observeOrder('one',{value:100,currency:'USD'});assert.equal(requests.length,0);
 await t.consent(true,true);await t.observeOrder('one',{value:100,currency:'USD'});await t.observeOrder('one',{value:100,currency:'USD'});
 assert.equal(requests.length,1);assert(requests[0].includes('value=100'));
});
