# Rafta Scalable Price Tracking Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build Rafta into a reliable, scalable price-tracking system that can serve thousands of users, track products until users mark them as purchased, and send price-drop/target notifications with controlled scraping/proxy cost.

**Architecture:** Move from a single cron script that loops over all products into a queue-based tracking pipeline. Products get normalized, scheduled, fetched through a provider ladder, parsed by domain adapters, stored as price observations, and notified through deduplicated notification jobs. Proxy/ScraperAPI remains useful as one provider, but it must not be the whole architecture.

**Tech Stack:** Current repo uses static `index.html`, Supabase, GitHub Actions/Render cron, Python `takip.py`, ScraperAPI, Resend, Web Push. Future-ready additions are Supabase schema migrations, provider abstraction, queue tables, per-domain adapters, and monitoring tables.

---

## Strategic Answer

The current ScraperAPI/proxy approach can work for an MVP, but **by itself it will not be enough for thousands of users**.

Why:
- A single cron that checks every product every run does not scale linearly; cost grows directly with product count.
- ScraperAPI free/low tiers will hit 403/quota quickly.
- Some stores block scraping aggressively, especially Trendyol/Amazon-like targets.
- Users expect continuous reliability, but ecommerce pages change often.
- Notification correctness needs price history, duplicate prevention, and user-specific preferences.

The sustainable direction is:
1. Keep ScraperAPI/proxy as one fallback provider.
2. Add direct fetch and structured-data parsing first.
3. Add domain-specific adapters for stores.
4. Add a `next_check_at` scheduling model instead of checking everything every time.
5. Add backoff for failures and lower frequency for stable products.
6. Add deduplicated notifications.
7. Add monitoring so failed domains are visible before users complain.

---

## Phase 1: Stabilize the Current MVP

### Task 1: Confirm GitHub Actions run after latest patch

**Objective:** Verify the latest commit reduces repeated 400/403 log noise.

**Files:**
- No code changes expected.

**Steps:**
1. Open GitHub Actions → `Fiyat Takip`.
2. Run workflow manually.
3. Check logs.
4. Expected:
   - ScraperAPI 403 appears at most once per run when quota is exhausted.
   - Missing Supabase columns are skipped instead of repeatedly crashing each product.
   - Direct-fetch products still update.

**Verification:**
- Workflow ends green or at least processes products without crashing the whole run.

---

### Task 2: Add missing Supabase tracking columns

**Objective:** Make cost/backoff tracking persistent instead of only in-memory per run.

**Supabase SQL:**

```sql
alter table public.urunler
add column if not exists son_kontrol timestamptz,
add column if not exists sonraki_kontrol timestamptz,
add column if not exists hata_sayisi integer default 0,
add column if not exists son_hata text,
add column if not exists scrape_yontemi text,
add column if not exists son_basarili_kontrol timestamptz;

create index if not exists idx_urunler_tracking_due
on public.urunler (sonraki_kontrol, satin_alindi, guncelleme_istegi);
```

**Files:**
- Optionally create: `supabase/migrations/001_tracking_columns.sql`

**Verification:**
- Run workflow again.
- Expected: no `Could not find column` errors.

---

### Task 3: Change product selection to due products only

**Objective:** Stop checking every product every run.

**Modify:**
- `takip.py`

**Current behavior:**
- Fetches recent/all products with a limit.

**Target behavior:**
- Fetch products where:
  - `satin_alindi` is false or null
  - and either `guncelleme_istegi = true`
  - or `sonraki_kontrol is null`
  - or `sonraki_kontrol <= now()`

**Expected query idea:**
```text
/rest/v1/urunler?select=*&or=(guncelleme_istegi.eq.true,sonraki_kontrol.is.null,sonraki_kontrol.lte.<now>)&order=guncelleme_istegi.desc,sonraki_kontrol.asc&limit=40
```

**Tests:**
- Add a helper test for query construction if extracted into a function.

**Verification:**
- Workflow checks only due products.

---

### Task 4: Implement next-check scheduling

**Objective:** Reduce proxy cost and avoid hammering stores.

**Modify:**
- `takip.py`
- `test_takip_helpers.py`

**Rules:**
- Manual update requested: check immediately.
- Successful scrape:
  - default next check: 6 hours
  - recently changed price: 3 hours
  - stable for long time: 12–24 hours later
- Failed scrape:
  - 1st fail: 6 hours
  - 2nd fail: 12 hours
  - 3+ fails: 24 hours
- Purchased/rafıma alındı: stop tracking.

**Test cases:**
- `test_next_check_after_success_default`
- `test_next_check_after_failure_backoff`
- `test_manual_update_bypasses_schedule`

**Verification:**
- Supabase row gets `sonraki_kontrol` updated.

---

## Phase 2: Make Tracking Reliable Per Store

### Task 5: Create a provider ladder abstraction

**Objective:** Separate fetching logic from parsing logic.

**Modify:**
- `takip.py`

**Design:**
```python
providers = [
  direct_fetch,
  scraperapi_plain,
  scraperapi_premium_no_render,
  scraperapi_render_premium,
  playwright_optional,
]
```

Each provider returns:
```python
{
  "ok": bool,
  "html": str | None,
  "mode": str,
  "error": str | None,
  "cost_level": int,
}
```

**Tests:**
- Provider stops after first successful price extraction.
- Provider skips ScraperAPI after 403.

---

### Task 6: Add domain adapters

**Objective:** Avoid one generic regex trying to parse every store.

**Create/Modify:**
- `takip.py` initially, later split into `adapters/` if repo grows.

**Adapters:**
- `parse_trendyol(html, url)`
- `parse_boyner(html, url)`
- `parse_hepsiburada(html, url)`
- `parse_zara(html, url)`
- `parse_bershka(html, url)`
- `parse_generic(html, url)`

**Order:**
1. Domain adapter
2. JSON-LD
3. meta price
4. regex fallback

**Tests:**
- Fixture HTML snippets for each supported store.

---

### Task 7: Normalize URLs before insert and before scrape

**Objective:** Prevent duplicate products and broken app/share URLs.

**Modify:**
- `index.html` for frontend normalization if not already complete.
- `takip.py` for backend normalization.

**Rules:**
- Remove tracking params: `utm_*`, `gclid`, `fbclid`, etc.
- Preserve variant params: `merchantId`, `boutiqueId`, `colorId`, `sizeId`, `sku`, etc.
- Reject non-product pages where possible.

**Verification:**
- Same product share URL and clean URL map to same normalized URL.

---

## Phase 3: Notification Correctness

### Task 8: Store numeric prices separately

**Objective:** Avoid comparing strings like `729,95 TL` incorrectly.

**Supabase SQL:**
```sql
alter table public.urunler
add column if not exists son_fiyat_num numeric,
add column if not exists ilk_fiyat_num numeric;

alter table public.fiyat_gecmisi
add column if not exists fiyat_num numeric;
```

**Modify:**
- `takip.py`

**Behavior:**
- Store display price and numeric price.
- Compare numeric values only.

---

### Task 9: Deduplicate notifications

**Objective:** Prevent users from receiving repeated emails/pushes for the same price.

**Supabase SQL:**
```sql
create table if not exists public.bildirim_loglari (
  id bigint generated by default as identity primary key,
  urun_id bigint not null,
  email text,
  bildirim_tipi text not null,
  fiyat_num numeric,
  created_at timestamptz default now()
);

create unique index if not exists idx_bildirim_unique_price
on public.bildirim_loglari (urun_id, bildirim_tipi, fiyat_num);
```

**Modify:**
- `takip.py`

**Rules:**
- Notify price drop only once per new lower price.
- Notify target reached once per target event.

---

### Task 10: Respect “satın aldım / rafıma alındı” semantics

**Objective:** Clarify whether current button means purchased or shelved.

**Open question:**
- User said current UI shows `rafıma al`; desired final meaning is `satın aldım` to stop tracking.

**Recommendation:**
- Keep product tracking while it is in the shelf.
- Add/rename a clear button: `Satın aldım`.
- When clicked:
  - set `satin_alindi = true`
  - stop future tracking
  - keep price history visible

**Modify:**
- `index.html`
- `takip.py` query should exclude `satin_alindi=true`.

---

## Phase 4: Scale Beyond MVP

### Task 11: Move from GitHub Actions cron to a dedicated worker

**Objective:** GitHub Actions is acceptable for MVP but not ideal for thousands of users.

**Recommended path:**
- Short term: Render cron can work.
- Medium term: Supabase Edge Function + queue, or a small VPS/Render worker.
- Long term: dedicated queue worker with concurrency, rate limits, and provider budgets.

**Why:**
- GitHub Actions has schedule delays and runtime limits.
- Secrets/logs/observability are limited.
- Scaling by concurrency is awkward.

---

### Task 12: Add monitoring dashboard data

**Objective:** Know which domains fail and why.

**Supabase SQL:**
```sql
create table if not exists public.scrape_runs (
  id bigint generated by default as identity primary key,
  started_at timestamptz default now(),
  finished_at timestamptz,
  checked_count integer default 0,
  success_count integer default 0,
  failure_count integer default 0,
  scraperapi_count integer default 0,
  direct_count integer default 0
);
```

**Use:**
- Later display admin metrics.

---

## Cost Strategy

### Keep costs low by design

1. Do not use proxy unless direct parsing fails.
2. Do not use render unless non-render proxy fails.
3. Do not recheck every product every run.
4. Do not retry failing domains aggressively.
5. Cache domain/provider failures per run.
6. Prioritize manual updates and products with recent price movement.
7. Stop tracking when `satin_alindi=true`.

### ScraperAPI viability

ScraperAPI is okay as an MVP provider, but at scale use it as one provider among several. Later compare:
- ScraperAPI
- Bright Data
- Oxylabs
- ScrapingBee
- Zyte
- store-specific public APIs/embedded JSON where available

No paid upgrades should be made without explicit user approval.

---

## Immediate Next Step Recommendation

Do this next, in order:

1. Wait for the latest GitHub Actions run result.
2. If it still has 400 errors, add the missing Supabase columns from Task 2.
3. If ScraperAPI 403 remains, accept it until quota resets; do not upgrade yet.
4. Implement Task 3 and Task 4 so thousands of products do not all get checked each run.
5. Then add numeric prices and notification dedupe.

This gives the strongest foundation before adding more stores or paying for proxy capacity.
