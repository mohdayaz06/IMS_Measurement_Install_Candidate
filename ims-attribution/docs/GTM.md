# GTM server-side installation contract

Installation candidate 1.0 supplies importable templates dist/ims-http-client.tpl and dist/ims-ledger-forwarder.tpl, plus original sandbox JavaScript. Use INSTALL-FIRST.md for the current HTTP collection path and generated tenant settings; the GA4 transport recipe below remains optional. Import structure and API behavior have local mock tests; live GTM Preview remains required. The templates are import assets, not a complete container preconnected to merchant accounts.

## Browser journey to IMS

1. Create the server container and custom first-party domain such as `tags.client.example`. Configure DNS/TLS and restrict administration to IMS staff.
2. Configure the standard GA4 client. In the web Google tag, set `server_container_url` to that domain. Use a separate measurement configuration if necessary to prevent duplicate page/purchase events.
3. Serve `web/pixel.js` from the IMS API domain. Instantiate with `mode:'sgtm'`, the GA4 measurement ID, tenant and API base URL. Connect `.consent(analyticsAllowed, marketingAllowed)` to the merchant CMP. Use `.pageView(location.href, document.referrer)` on actual navigations. Consent must not be hardcoded to true.
4. Create a server custom tag using `integrations/sgtm-forward-tag.js`. Add text fields `endpoint` and `bridgeKey`. Endpoint = `https://tracking.example.com/bridge/CLIENT_ID`; key is the per-client bridge secret returned at provisioning.
5. Grant read-event-data permission for the `ims_*` parameters and `event_name`. Grant send-HTTP permission only to the exact IMS endpoint. Create a trigger for `ims_touch` events claimed by the GA4 client. Keep credentials in server configuration, never the web container.
6. Configure your GA4 destination tag to exclude `ims_touch` if these operational events should not enter GA4. Avoid accidentally collecting them twice through both a direct route and sGTM.

The default SDK mode posts directly to `/collect/TENANT` as a pilot/fallback route. It is not a claim that all traffic already uses server GTM. The Shopify custom pixel source uses this fallback because it cannot assume a parent-page `gtag` exists inside Shopify's sandbox. For a supported app installation implement a Shopify Web Pixel extension plus deterministic checkout/order linkage; quote this explicitly.

## Verified purchases from IMS to ad destinations

1. Create a custom server CLIENT using `integrations/sgtm-verified-client.js`. Add a text field `gatewayKey` with a new random 32+ byte secret. Grant request path/header/body access for `/ims/verified` and `x-ims-gateway-key`; allow `claimRequest`, `runContainer`, response status and response return APIs as required by current GTM permissions.
2. Create a private server-only JSON configuration mapping tenant to `{ "endpoint": "https://tags.client.example/ims/verified", "key": "SECRET" }`. Set `IMS_GATEWAYS_FILE` to the file path. Never place it in source control or a client reporting dataset.
3. Schedule `python3 -m integrations.deliver_conversions` once a minute using a single-instance lock. It sends only verified orders joined to order observations with marketing permission. Stable event ID survives retries.
4. Configure Google Ads conversion tracking and/or GA4 purchase tags, Meta CAPI using a reviewed maintained server template, and Simpli.fi only through its confirmed supported account interface. Use merchant-specific IDs/secrets and consent triggers.
5. Map `transaction_id`, `value`, `currency`, `event_id`, `event_time` and `client_id`. The envelope includes action_source, configured origin URL and recorded consented gclid/gbraid/wbraid/fbc/fbp when available. For Google configure accepted identifier/conversion-action fields; for Meta map action source, source URL and fbc/fbp to its supported user-data schema. Email, phone, IP and user agent are intentionally omitted from this sender. Confirm source URL and matching quality, and add authorized enrichment if needed. A pseudonymous IMS client ID alone is not an adequate substitute for vendor-required matching fields.
6. If legacy browser Meta Purchase remains active, use EXACTLY the same event ID as the server event. The legacy pixel uses a different ID convention; cut it over or change its ID before dual sending. Do not simultaneously import GA4 purchases into Google Ads and fire the same direct Google Ads conversion action without deliberate configuration.

`gateway_accepted` means the server container returned 2xx. It does not prove any ad platform accepted, matched or attributed the event. Native tag responses, Meta Test Events and Google diagnostics are separate acceptance checks. Simpli.fi script/image pixels cannot simply be executed from a server and assumed to retain browser attribution.

## Required Preview tests

- Consent denied: no IMS identity, collection or ad forwarding.
- Analytics only: journey permitted; advertising forwarding blocked.
- Both allowed: one IMS order and one stable destination event ID.
- Unknown gateway key: 401 and no tags fire.
- Replay: one ledger order; destination dedup tested independently.
- Each hostname, Shopify checkout sandbox, thank-you page refresh and cross-domain checkout verified.
- No raw media costs, pricing rules, gateway credentials or agency tokens appear in page source, browser requests or client reports.
