PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS tenants (
 id TEXT PRIMARY KEY, currency TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'UTC',
 origins TEXT NOT NULL, shop TEXT UNIQUE, shop_secret TEXT, bridge_hash TEXT NOT NULL,
 lookback_days INTEGER NOT NULL DEFAULT 30
);
CREATE TABLE IF NOT EXISTS keys (
 hash TEXT PRIMARY KEY, tenant TEXT NOT NULL REFERENCES tenants(id), role TEXT NOT NULL,
 label TEXT NOT NULL, created TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS touches (
 tenant TEXT NOT NULL, event_id TEXT NOT NULL, visitor TEXT NOT NULL,
 ts TEXT NOT NULL, channel TEXT NOT NULL, campaign TEXT NOT NULL, medium TEXT NOT NULL,
 PRIMARY KEY(tenant,event_id), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS touches_journey ON touches(tenant,visitor,ts);
CREATE TABLE IF NOT EXISTS signals (
 tenant TEXT NOT NULL, visitor TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant,visitor)
);
CREATE TABLE IF NOT EXISTS ctv_impressions (
 tenant TEXT NOT NULL, impression_id TEXT NOT NULL, network_key TEXT NOT NULL,
 ts TEXT NOT NULL, campaign TEXT NOT NULL, provider TEXT NOT NULL, network_type TEXT NOT NULL,
 PRIMARY KEY(tenant,impression_id)
);
CREATE INDEX IF NOT EXISTS ctv_match ON ctv_impressions(tenant,network_key,ts);
CREATE TABLE IF NOT EXISTS ctv_order_networks (
 tenant TEXT NOT NULL, order_id TEXT NOT NULL, network_key TEXT NOT NULL,
 PRIMARY KEY(tenant,order_id), FOREIGN KEY(tenant,order_id) REFERENCES orders(tenant,order_id)
);
CREATE TABLE IF NOT EXISTS orders (
 tenant TEXT NOT NULL, order_id TEXT NOT NULL, visitor TEXT, ts TEXT NOT NULL,
 currency TEXT NOT NULL, gross INTEGER NOT NULL CHECK(gross>=0),
 customer TEXT, source TEXT NOT NULL, PRIMARY KEY(tenant,order_id),
 FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE INDEX IF NOT EXISTS orders_time ON orders(tenant,ts);
CREATE TABLE IF NOT EXISTS order_snapshots (
 tenant TEXT NOT NULL, order_id TEXT NOT NULL, updated TEXT NOT NULL,
 net INTEGER NOT NULL CHECK(net>=0), source TEXT NOT NULL,
 PRIMARY KEY(tenant,order_id), FOREIGN KEY(tenant,order_id) REFERENCES orders(tenant,order_id)
);
CREATE TABLE IF NOT EXISTS refunds (
 tenant TEXT NOT NULL, refund_id TEXT NOT NULL, order_id TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>=0), ts TEXT NOT NULL,
 PRIMARY KEY(tenant,refund_id), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS observations (
 tenant TEXT NOT NULL, order_id TEXT NOT NULL, visitor TEXT NOT NULL,
 marketing INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(tenant,order_id), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS outbox (
 tenant TEXT NOT NULL, order_id TEXT NOT NULL, event_id TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, next_attempt TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', last_status INTEGER,
 PRIMARY KEY(tenant,order_id)
);
CREATE TABLE IF NOT EXISTS spend (
 tenant TEXT NOT NULL, day TEXT NOT NULL, channel TEXT NOT NULL, campaign TEXT NOT NULL,
 currency TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>=0),
 impressions INTEGER NOT NULL CHECK(impressions>=0), clicks INTEGER NOT NULL CHECK(clicks>=0),
 PRIMARY KEY(tenant,day,channel,campaign), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS markups (
 tenant TEXT NOT NULL, channel TEXT NOT NULL, effective TEXT NOT NULL,
 bps INTEGER NOT NULL CHECK(bps BETWEEN 0 AND 100000),
 PRIMARY KEY(tenant,channel,effective), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS deliveries (
 tenant TEXT NOT NULL, delivery TEXT NOT NULL, ts TEXT NOT NULL,
 PRIMARY KEY(tenant,delivery)
);
CREATE TABLE IF NOT EXISTS experiments (
 tenant TEXT NOT NULL, id TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
 fraction REAL NOT NULL CHECK(fraction>0 AND fraction<1), salt TEXT NOT NULL,
 unit_type TEXT NOT NULL, hypothesis TEXT NOT NULL, min_units INTEGER NOT NULL,
 PRIMARY KEY(tenant,id), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS units (
 tenant TEXT NOT NULL, experiment TEXT NOT NULL, unit TEXT NOT NULL, arm TEXT NOT NULL,
 enrolled TEXT NOT NULL, PRIMARY KEY(tenant,experiment,unit),
 FOREIGN KEY(tenant,experiment) REFERENCES experiments(tenant,id)
);
CREATE TABLE IF NOT EXISTS outcomes (
 tenant TEXT NOT NULL, experiment TEXT NOT NULL, outcome TEXT NOT NULL,
 unit TEXT NOT NULL, ts TEXT NOT NULL, revenue INTEGER NOT NULL CHECK(revenue>=0),
 PRIMARY KEY(tenant,experiment,outcome),
 FOREIGN KEY(tenant,experiment,unit) REFERENCES units(tenant,experiment,unit)
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, ts TEXT NOT NULL,
 actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connectors (
 tenant TEXT NOT NULL, id TEXT NOT NULL, platform TEXT NOT NULL, channel TEXT NOT NULL, account TEXT NOT NULL,
 currency TEXT NOT NULL, timezone TEXT NOT NULL, capabilities TEXT NOT NULL,
 secret_env TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(tenant,id), FOREIGN KEY(tenant) REFERENCES tenants(id)
);
CREATE TABLE IF NOT EXISTS connector_deliveries (
 tenant TEXT NOT NULL, connector TEXT NOT NULL, delivery TEXT NOT NULL,
 body_hash TEXT NOT NULL, ts TEXT NOT NULL,
 PRIMARY KEY(tenant,connector,delivery)
);
CREATE TABLE IF NOT EXISTS job_runs (
 id INTEGER PRIMARY KEY, tenant TEXT NOT NULL, job TEXT NOT NULL,
 started TEXT NOT NULL, finished TEXT, state TEXT NOT NULL,
 detail TEXT NOT NULL DEFAULT '{}'
);
CREATE VIEW IF NOT EXISTS ledger_net AS
SELECT o.*, MAX(0,COALESCE(s.net,o.gross)-COALESCE((
 SELECT SUM(r.amount) FROM refunds r WHERE r.tenant=o.tenant AND r.order_id=o.order_id
 AND (s.updated IS NULL OR r.ts>s.updated)
),0)) AS net
FROM orders o LEFT JOIN order_snapshots s ON s.tenant=o.tenant AND s.order_id=o.order_id;
CREATE TABLE IF NOT EXISTS consent_blocks (
 tenant TEXT NOT NULL, visitor TEXT NOT NULL, scope TEXT NOT NULL, ts TEXT NOT NULL,
 PRIMARY KEY(tenant,visitor)
);
CREATE TABLE IF NOT EXISTS destination_deliveries (
 tenant TEXT NOT NULL, order_id TEXT NOT NULL, destination TEXT NOT NULL,
 event_id TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt TEXT NOT NULL, last_status INTEGER, detail TEXT NOT NULL DEFAULT '{}',
 PRIMARY KEY(tenant,order_id,destination)
);
CREATE TABLE IF NOT EXISTS experiment_publications (
 tenant TEXT NOT NULL, experiment TEXT NOT NULL, published TEXT NOT NULL,
 body TEXT NOT NULL, PRIMARY KEY(tenant,experiment)
);
CREATE TABLE IF NOT EXISTS privacy_requests (
 tenant TEXT NOT NULL, id TEXT NOT NULL, topic TEXT NOT NULL,
 created TEXT NOT NULL, state TEXT NOT NULL, body TEXT NOT NULL,
 PRIMARY KEY(tenant,id)
);
CREATE TABLE IF NOT EXISTS tenant_shutdown (
 tenant TEXT PRIMARY KEY, closed TEXT NOT NULL
);
