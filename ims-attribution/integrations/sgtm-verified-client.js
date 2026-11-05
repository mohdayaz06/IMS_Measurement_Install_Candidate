// Server GTM CUSTOM CLIENT sandbox code; configure gatewayKey field + permissions.
// Reference template source, not an importable .tpl. Validate in sGTM Preview.
const getRequestPath = require('getRequestPath');
const getRequestHeader = require('getRequestHeader');
const getRequestBody = require('getRequestBody');
const claimRequest = require('claimRequest');
const runContainer = require('runContainer');
const setResponseStatus = require('setResponseStatus');
const returnResponse = require('returnResponse');
const JSON = require('JSON');
if (getRequestPath() !== '/ims/verified') return;
claimRequest();
if (getRequestHeader('x-ims-gateway-key') !== data.gatewayKey) {
  setResponseStatus(401);returnResponse();return;
}
const e=JSON.parse(getRequestBody());
if (!e || e.event_name !== 'purchase' || !e.transaction_id || e.marketing_consent !== true) {
  setResponseStatus(400);returnResponse();return;
}
runContainer(e,function(){setResponseStatus(202);returnResponse();});
