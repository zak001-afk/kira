-- ============================================================================
-- KIRA — Shared knowledge schema for Supabase
-- ============================================================================
-- PURPOSE
--   Stores ONLY shared, non-personal web knowledge (web research summaries,
--   learned public web pages, general facts).
--
--   NEVER stored here (kept local in kira_memory.db):
--     - conversations
--     - user names / identity
--     - personal preferences
--     - tasks, reminders, todos
--     - private notes
--
-- SECURITY
--   KIRA connects with the PUBLIC anon key only. Row Level Security is
--   enabled below so the anon key can never bypass these policies.
--   NEVER use the service_role key with KIRA.
--
-- HOW TO APPLY
--   Supabase Dashboard -> SQL Editor -> paste this file -> Run.
-- ============================================================================

-- Required for gen_random_uuid() on older projects (built-in on PG 13+).
create extension if not exists pgcrypto;

-- Trigram index support for fuzzy ILIKE searches.
create extension if not exists pg_trgm;

-- ----------------------------------------------------------------------------
-- Table: shared knowledge entries
-- ----------------------------------------------------------------------------
create table if not exists public.shared_knowledge (
    id           uuid primary key default gen_random_uuid(),

    -- kind of knowledge, e.g. 'web_search', 'web_page', 'fact'
    kind         text not null default 'web_research',

    -- stable topic key; (kind, topic) pairs are upserted, never duplicated
    topic        text not null,

    -- human-readable title (optional)
    title        text,

    -- the shared knowledge content itself (non-personal only)
    content      text not null,

    -- where the knowledge came from (optional)
    source_url   text,

    -- optional: the Supabase Auth user that contributed the entry
    contributed_by uuid references auth.users (id) on delete set null,

    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),

    constraint shared_knowledge_kind_topic_unique unique (kind, topic),
    constraint shared_knowledge_kind_not_blank
        check (length(btrim(kind)) > 0),
    constraint shared_knowledge_topic_not_blank
        check (length(btrim(topic)) > 0),
    constraint shared_knowledge_content_not_blank
        check (length(btrim(content)) > 0)
);

comment on table public.shared_knowledge is
    'Shared, NON-personal web knowledge for KIRA. Personal data (names, '
    'preferences, conversations, tasks, private notes) must stay local in '
    'kira_memory.db and must never be inserted here.';

-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------
create index if not exists shared_knowledge_kind_idx
    on public.shared_knowledge (kind);

create index if not exists shared_knowledge_topic_idx
    on public.shared_knowledge (topic);

create index if not exists shared_knowledge_updated_at_idx
    on public.shared_knowledge (updated_at desc);

create index if not exists shared_knowledge_content_trgm_idx
    on public.shared_knowledge using gin (content gin_trgm_ops);

create index if not exists shared_knowledge_title_trgm_idx
    on public.shared_knowledge using gin (title gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- Keep updated_at fresh on upsert/update
-- ----------------------------------------------------------------------------
create or replace function public.set_shared_knowledge_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists shared_knowledge_updated_at_trigger
    on public.shared_knowledge;

create trigger shared_knowledge_updated_at_trigger
    before insert or update on public.shared_knowledge
    for each row
    execute function public.set_shared_knowledge_updated_at();

-- ----------------------------------------------------------------------------
-- Row Level Security
-- ----------------------------------------------------------------------------
-- KIRA uses the anon (public) key. The policies below make the shared
-- knowledge base world-readable, allow KIRA instances to contribute
-- entries, but only authenticated users can modify or delete them.
-- ----------------------------------------------------------------------------
alter table public.shared_knowledge enable row level security;

-- Everyone (including KIRA with the anon key) can read shared knowledge.
drop policy if exists "shared_knowledge_public_read"
    on public.shared_knowledge;
create policy "shared_knowledge_public_read"
    on public.shared_knowledge
    for select
    to anon, authenticated
    using (true);

-- KIRA instances may contribute new shared knowledge entries.
drop policy if exists "shared_knowledge_public_insert"
    on public.shared_knowledge;
create policy "shared_knowledge_public_insert"
    on public.shared_knowledge
    for insert
    to anon, authenticated
    with check (true);

-- Only authenticated users may update existing entries.
drop policy if exists "shared_knowledge_auth_update"
    on public.shared_knowledge;
create policy "shared_knowledge_auth_update"
    on public.shared_knowledge
    for update
    to authenticated
    using (true)
    with check (true);

-- Only authenticated users may delete entries.
drop policy if exists "shared_knowledge_auth_delete"
    on public.shared_knowledge;
create policy "shared_knowledge_auth_delete"
    on public.shared_knowledge
    for delete
    to authenticated
    using (true);
