-- Run this entire script once in your Supabase SQL Editor.
create table if not exists public.users (
  id text primary key,
  email text unique not null,
  name text not null,
  salt text not null,
  password_hash text not null,
  created_at timestamptz not null default now()
);
create table if not exists public.sessions (
  token text primary key,
  user_id text not null references public.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
create table if not exists public.chats (
  id text primary key,
  user_id text not null references public.users(id) on delete cascade,
  title text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  messages jsonb not null default '[]'::jsonb
);
create index if not exists chats_user_updated_idx on public.chats(user_id, updated_at desc);
-- Do not enable public table access. The app accesses Postgres through its server-side DATABASE_URL.
