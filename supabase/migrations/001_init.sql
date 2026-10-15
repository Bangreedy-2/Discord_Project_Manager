-- Core tables. Discord objects are stored by snowflake id (bigint), never by name.

create table guild_settings (
  guild_id              bigint primary key,
  max_projects_per_user int  not null default 3,
  max_channels_per_proj int  not null default 15
);

create table projects (
  id              uuid primary key default gen_random_uuid(),
  guild_id        bigint not null,
  name            text   not null,
  creator_id      bigint not null,
  status          text   not null default 'pending'
                  check (status in ('pending','active','broken','deleting')),
  category_id     bigint unique,
  owner_role_id   bigint unique,
  member_role_id  bigint unique,
  viewer_role_id  bigint unique,
  created_at      timestamptz not null default now()
);
create unique index projects_name_uq on projects (guild_id, lower(name))
  where status <> 'deleting';
create index projects_creator_idx on projects (guild_id, creator_id);

create table project_channels (
  channel_id      bigint primary key,
  project_id      uuid not null references projects(id) on delete cascade,
  kind            text not null check (kind in ('text','voice','forum')),
  is_public       boolean not null default false,
  public_can_post boolean not null default false,
  created_by      bigint not null,
  created_at      timestamptz not null default now()
);
create index project_channels_project_idx on project_channels (project_id);

create table audit_log (
  id          bigserial primary key,
  guild_id    bigint not null,
  project_id  uuid references projects(id) on delete set null,
  actor_id    bigint not null,
  action      text   not null,   -- 'project.create', 'channel.visibility', 'member.set', ...
  target_id   bigint,
  details     jsonb  not null default '{}',
  created_at  timestamptz not null default now()
);
create index audit_log_project_idx on audit_log (project_id, created_at desc);

-- RLS on with no policies: the public API keys can read nothing.
-- The bot connects with the database connection string, which bypasses RLS.
alter table guild_settings   enable row level security;
alter table projects         enable row level security;
alter table project_channels enable row level security;
alter table audit_log        enable row level security;
