-- ============================================================================
-- KIRA — Shared knowledge schema for Supabase
-- ============================================================================
-- PURPOSE
--   Stores ONLY shared, non-personal knowledge:
--     - public web research (search summaries)      -> 'web_research'
--     - learned public web pages                    -> 'web_page'
--     - shared project knowledge (architecture,
--       conventions, build steps)                   -> 'project_knowledge'
--
--   NEVER stored here (kept local in kira_memory.db on each machine):
--     - conversations
--     - user names / identity facts
--     - personal preferences
--     - tasks, reminders and todos
--     - private notes
--
-- SECURITY
--   KIRA connects with the PUBLIC anon (publishable) key only.
--   Row Level Security is enabled below, so that key can never read or
--   write anything outside the policies defined here.
--   NEVER use the service_role key with KIRA: it bypasses RLS and is not
--   needed by this schema.
--
-- HOW TO APPLY
--   Supabase Dashboard -> SQL Editor -> paste this file -> Run.
--   The script is idempotent and safe to re-run.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Extensions
-- ----------------------------------------------------------------------------
-- gen_random_uuid() for primary keys (built in on PostgreSQL 13+).
create extension if not exists pgcrypto;

-- Trigram indexes/matching for fuzzy ILIKE searches.
create extension if not exists pg_trgm;

-- ----------------------------------------------------------------------------
-- Table: shared knowledge entries
-- ----------------------------------------------------------------------------
create table if not exists public.shared_knowledge (
    id            uuid primary key default gen_random_uuid(),

    -- knowledge kind; must stay in sync with ALLOWED_KINDS in
    -- kira_shared_memory.py
    kind          text not null default 'web_research',

    -- stable topic key; (kind, topic) pairs are upserted, never duplicated
    topic         text not null,

    -- human-readable title (optional)
    title         text,

    -- the shared knowledge itself (non-personal content only)
    content       text not null,

    -- where the knowledge came from (optional)
    source_url    text,

    -- optional free-form labels, e.g. {'python','docs'}
    tags          text[] not null default '{}'::text[],

    -- optional: Supabase Auth user that contributed the entry.
    -- KIRA uses the anon key, so this stays null for KIRA-written rows.
    contributed_by uuid references auth.users (id) on delete set null,

    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),

    -- full-text search vector, maintained by PostgreSQL itself
    search_vector tsvector generated always as (
        to_tsvector(
            'simple',
            coalesce(title, '') || ' ' ||
            coalesce(topic, '') || ' ' ||
            coalesce(content, '')
        )
    ) stored,

    constraint shared_knowledge_kind_topic_unique unique (kind, topic),

    constraint shared_knowledge_kind_allowed check (
        kind in ('web_research', 'web_page', 'project_knowledge')
    ),

    constraint shared_knowledge_topic_not_blank
        check (length(btrim(topic)) > 0),
    constraint shared_knowledge_content_not_blank
        check (length(btrim(content)) > 0),

    -- keep payloads in sync with the limits enforced by kira_shared_memory.py
    constraint shared_knowledge_topic_length check (length(topic) <= 160),
    constraint shared_knowledge_title_length
        check (title is null or length(title) <= 300),
    constraint shared_knowledge_content_length check (length(content) <= 8000),
    constraint shared_knowledge_source_url_length
        check (source_url is null or length(source_url) <= 2000)
);

comment on table public.shared_knowledge is 'Shared, NON-personal knowledge for KIRA (public web research, learned web pages, shared project knowledge). Personal data - names, preferences, conversations, tasks and private notes - must stay local in kira_memory.db and must never be inserted here.';

comment on column public.shared_knowledge.kind is
    'One of: web_research, web_page, project_knowledge.';
comment on column public.shared_knowledge.topic is
    'Stable topic key. (kind, topic) is unique and used for upserts.';

-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------
create index if not exists shared_knowledge_kind_idx
    on public.shared_knowledge (kind);

create index if not exists shared_knowledge_topic_idx
    on public.shared_knowledge (topic);

create index if not exists shared_knowledge_updated_at_idx
    on public.shared_knowledge (updated_at desc);

create index if not exists shared_knowledge_search_vector_idx
    on public.shared_knowledge using gin (search_vector);

create index if not exists shared_knowledge_content_trgm_idx
    on public.shared_knowledge using gin (content gin_trgm_ops);

create index if not exists shared_knowledge_title_trgm_idx
    on public.shared_knowledge using gin (title gin_trgm_ops);

create index if not exists shared_knowledge_tags_idx
    on public.shared_knowledge using gin (tags);

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
-- Privacy guard (defense in depth)
-- ----------------------------------------------------------------------------
-- Rejects content that looks personal/private even if some client tries to
-- write it (this applies to every role, including service_role). KIRA also
-- refuses such payloads client-side in kira_shared_memory.py.
-- ----------------------------------------------------------------------------
create or replace function public.shared_knowledge_privacy_guard()
returns trigger
language plpgsql
as $$
declare
    haystack text;
begin
    haystack := coalesce(new.topic, '') || ' ' ||
                coalesce(new.title, '') || ' ' ||
                coalesce(new.content, '');

    -- Identity / preference / private-note phrases.
    if haystack ~* '\ymy (full |first |last |nick ?)?name\M'
       or haystack ~* '\ymy (favorite|favourite|preferred)\M'
       or haystack ~* '\yi (prefer|like|love|hate|dislike|enjoy)\y'
       or haystack ~* '\ymy (birthday|address|phone|email|salary|boss|manager)\M'
       or haystack ~* '\ymy (wife|husband|partner|son|daughter|mother|father|family)\y'
       or haystack ~* '\y(remember that my|keep this local|between us|confidential)\y'
       or haystack ~* '\y(password|passphrase|api[ _-]?key|access[ _-]?token|credentials?|private[ _-]?key)\y'
       or haystack ~* '\y(sk-[A-Za-z0-9_-]{8,})\y'
       or haystack ~* '[[:alnum:]._%+-]+@[[:alnum:]-]+\.[[:alpha:]]{2,}'
    then
        raise exception
            'shared_knowledge rejects personal/private data; keep it in the local kira_memory.db'
            using errcode = 'check_violation';
    end if;

    return new;
end;
$$;

drop trigger if exists shared_knowledge_privacy_guard_trigger
    on public.shared_knowledge;

create trigger shared_knowledge_privacy_guard_trigger
    before insert or update on public.shared_knowledge
    for each row
    execute function public.shared_knowledge_privacy_guard();

-- ----------------------------------------------------------------------------
-- Row Level Security
-- ----------------------------------------------------------------------------
-- KIRA uses the anon (publishable) key. The policies below make shared
-- knowledge world-readable, let KIRA instances contribute entries, and
-- reserve updates/deletes for authenticated users.
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
    with check (
        kind in ('web_research', 'web_page', 'project_knowledge')
        and length(btrim(topic)) between 1 and 160
        and length(content) between 1 and 8000
        and length(coalesce(title, '')) <= 300
        and length(coalesce(source_url, '')) <= 2000
    );

-- Refreshing a known (kind, topic) is what KIRA's upsert does, and
-- PostgreSQL checks INSERT ... ON CONFLICT DO UPDATE against this policy.
-- The anon key may therefore refresh entries as well as add them; this is
-- the behaviour that keeps the shared knowledge base up to date without a
-- service_role key. Deletion stays restricted to authenticated users.
--
-- If you prefer an append-only knowledge base, drop this policy: KIRA then
-- only adds topics it has not seen before and leaves existing rows untouched.
drop policy if exists "shared_knowledge_public_update"
    on public.shared_knowledge;
create policy "shared_knowledge_public_update"
    on public.shared_knowledge
    for update
    to anon, authenticated
    using (true)
    with check (
        kind in ('web_research', 'web_page', 'project_knowledge')
        and length(btrim(topic)) between 1 and 160
        and length(content) between 1 and 8000
        and length(coalesce(title, '')) <= 300
        and length(coalesce(source_url, '')) <= 2000
    );

-- Only authenticated users may delete entries.
drop policy if exists "shared_knowledge_auth_delete"
    on public.shared_knowledge;
create policy "shared_knowledge_auth_delete"
    on public.shared_knowledge
    for delete
    to authenticated
    using (true);

-- anon needs INSERT + UPDATE (upsert does insert .. on conflict update).
grant select, insert, update on public.shared_knowledge to anon;
grant select, insert, update, delete on public.shared_knowledge to authenticated;

-- ----------------------------------------------------------------------------
-- Search function used by kira_shared_memory.search_shared_knowledge()
-- ----------------------------------------------------------------------------
-- Full-text search first, ILIKE fallback for short or partial queries.
-- SECURITY INVOKER: RLS of the calling role still applies.
-- ----------------------------------------------------------------------------
create or replace function public.search_shared_knowledge(
    p_query text,
    p_limit integer default 5,
    p_kind  text default null
)
returns setof public.shared_knowledge
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
    with params as (
        select
            nullif(btrim(coalesce(p_query, '')), '') as raw_query,
            websearch_to_tsquery(
                'simple',
                btrim(coalesce(p_query, ''))
            ) as ts_query
    )
    select k.*
    from public.shared_knowledge k
    cross join params p
    where p.raw_query is not null
      and (p_kind is null or k.kind = p_kind)
      and (
            (
                p.ts_query is not null
                and p.ts_query::text <> ''
                and k.search_vector @@ p.ts_query
            )
            or k.topic   ilike '%' || p.raw_query || '%'
            or k.title   ilike '%' || p.raw_query || '%'
            or k.content ilike '%' || p.raw_query || '%'
      )
    order by
        case
            when p.ts_query is not null
                 and p.ts_query::text <> ''
                 and k.search_vector @@ p.ts_query
            then ts_rank(k.search_vector, p.ts_query)
            else 0
        end desc,
        k.updated_at desc
    limit least(greatest(coalesce(p_limit, 5), 1), 50);
$$;

comment on function public.search_shared_knowledge(text, integer, text) is
    'Ranked shared-knowledge search for KIRA (full-text + ILIKE fallback). '
    'Only non-personal shared knowledge is stored in this table.';

revoke all on function public.search_shared_knowledge(text, integer, text)
    from public;
grant execute on function public.search_shared_knowledge(text, integer, text)
    to anon, authenticated;

-- ----------------------------------------------------------------------------
-- Quick verification (optional — uncomment to check the setup)
-- ----------------------------------------------------------------------------
-- select tablename, rowsecurity
--   from pg_tables where schemaname = 'public'
--  and tablename = 'shared_knowledge';
--
-- select policyname, roles, cmd from pg_policies
--  where tablename = 'shared_knowledge' order by policyname;
--
-- insert into public.shared_knowledge (kind, topic, title, content, source_url)
-- values ('web_research', 'python_decorators',
--         'Python decorators',
--         'Decorators wrap a function and return a new callable.',
--         'https://docs.python.org/3/glossary.html#term-decorator');
--
-- select * from public.search_shared_knowledge('python decorators', 5);
