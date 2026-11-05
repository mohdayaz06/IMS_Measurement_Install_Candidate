// Shopify Customer Events CUSTOM pixel JavaScript, without script tags.
// Set customer privacy: Analytics required. Marketing permissions handled independently.
// Host the SDK on your TLS endpoint. Sandbox browser origin must be tested and allowlisted.
const IMS_BASE='https://tracking.example.com';
const IMS_TENANT='replace-client-id';
let privacy=init.customerPrivacy||{};
let ready;
function sdk(){
  if(!ready) ready=new Promise((resolve,reject)=>{
    const s=document.createElement('script');s.src=IMS_BASE+'/pixel.js';
    s.onload=()=>resolve(window.IMSAttribution.create({baseUrl:IMS_BASE,tenant:IMS_TENANT,storage:browser.localStorage}));
    s.onerror=reject;document.head.appendChild(s);
  });
  return ready;
}
async function tracker(){
  // Do not create browser identity until analytics permission exists.
  if(privacy.analyticsProcessingAllowed!==true)return null;
  const t=await sdk();await t.consent(true,privacy.marketingAllowed===true&&privacy.saleOfDataAllowed===true);return t;
}
if(typeof api!=='undefined'&&api.customerPrivacy){
  api.customerPrivacy.subscribe('visitorConsentCollected',async e=>{
    privacy=e.customerPrivacy||{};
    if(ready){const t=await ready;await t.consent(privacy.analyticsProcessingAllowed===true,privacy.marketingAllowed===true&&privacy.saleOfDataAllowed===true);}
  });
}
analytics.subscribe('page_viewed',async e=>{
  try{const t=await tracker();if(t)await t.pageView(e.context.document.location.href,e.context.document.referrer||'');}
  catch(err){console.error('IMS page tracking failed');}
});
analytics.subscribe('checkout_completed',async e=>{
  try{const t=await tracker();const checkout=e.data.checkout;const order=checkout.order;if(t&&order)await t.observeOrder(order.id,{value:checkout.totalPrice.amount,currency:checkout.currencyCode});}
  catch(err){console.error('IMS order observation failed');}
});
// This script observes order ID only. Signed orders/paid webhook creates revenue.
// For a production Shopify app, replace this custom pixel with a Web Pixel extension.
