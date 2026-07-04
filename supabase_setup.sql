-- WildLens AI — Supabase Database Setup
-- Run this ONCE in your Supabase project's SQL Editor:
-- Dashboard → SQL Editor → New query → paste this → Run

-- 1. Scan history (every image classification)
create table if not exists scans (
  id           text primary key default gen_random_uuid()::text,
  session_id   text,
  species      text,
  confidence   float,
  model_type   text,
  latency_ms   float,
  created_at   timestamptz default now()
);

-- 2. Chat message logs
create table if not exists chat_logs (
  id              bigint generated always as identity primary key,
  session_id      text,
  role            text,           -- 'user' or 'assistant'
  content         text,
  species_context text,
  created_at      timestamptz default now()
);

-- 3. Citizen science contributions
create table if not exists science_contributions (
  id          bigint generated always as identity primary key,
  scan_id     text,
  session_id  text,
  species     text,
  location    text,
  created_at  timestamptz default now()
);

-- 4. Enterprise reports generated
create table if not exists reports (
  id          bigint generated always as identity primary key,
  session_id  text,
  species     text,
  ai_powered  boolean default false,
  created_at  timestamptz default now()
);

-- 5. Mock premium signups
create table if not exists premium_signups (
  id          bigint generated always as identity primary key,
  session_id  text,
  plan        text,
  amount_usd  int,
  status      text,
  created_at  timestamptz default now()
);

-- Enable Row Level Security (open read/write for anon for demo purposes)
alter table scans                enable row level security;
alter table chat_logs            enable row level security;
alter table science_contributions enable row level security;
alter table reports              enable row level security;
alter table premium_signups      enable row level security;

create policy "Allow all for anon" on scans                for all using (true) with check (true);
create policy "Allow all for anon" on chat_logs            for all using (true) with check (true);
create policy "Allow all for anon" on science_contributions for all using (true) with check (true);
create policy "Allow all for anon" on reports              for all using (true) with check (true);
create policy "Allow all for anon" on premium_signups      for all using (true) with check (true);
