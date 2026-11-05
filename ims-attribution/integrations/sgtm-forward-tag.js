// Server GTM custom tag sandbox code. Configure fields + permissions per docs/GTM.md.
const getAllEventData = require('getAllEventData');
const sendHttpRequest = require('sendHttpRequest');
const JSON = require('JSON');
const e = getAllEventData();
if (e.event_name !== 'ims_touch' || e.ims_analytics_consent != 1) {
  data.gtmOnSuccess();
  return;
}
const payload = {
  event_id: e.ims_event_id, visitor_id: e.ims_visitor_id, ts: e.ims_ts,
  source: e.ims_source || 'direct', medium: e.ims_medium || '',
  campaign: e.ims_campaign || '(none)', analytics_consent: true,
  marketing_consent: e.ims_marketing_consent == 1
};
if (payload.marketing_consent) {
  payload.signals={};
  ['gclid','gbraid','wbraid','fbc','fbp'].forEach(function(k){if(e['ims_'+k])payload.signals[k]=e['ims_'+k];});
}
if (e.ims_order_id) payload.order_id = e.ims_order_id;
sendHttpRequest(data.endpoint, {
  method: 'POST', timeout: 5000,
  headers: {'Content-Type': 'application/json','X-IMS-Bridge-Key': data.bridgeKey}
}, JSON.stringify(payload)).then(function(response) {
  if (response.statusCode >= 200 && response.statusCode < 300) data.gtmOnSuccess();
  else data.gtmOnFailure();
}, data.gtmOnFailure);
