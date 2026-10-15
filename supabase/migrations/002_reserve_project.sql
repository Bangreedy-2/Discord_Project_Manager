-- Atomic per-user project cap. Locks per (guild, user) so concurrent creates serialize.
create or replace function reserve_project(
  p_guild bigint, p_creator bigint, p_name text, p_bypass boolean
) returns uuid language plpgsql as $$
declare
  v_max int; v_count int; v_id uuid;
begin
  perform pg_advisory_xact_lock(
    hashtextextended(p_guild::text || ':' || p_creator::text, 0));
  select coalesce((select max_projects_per_user from guild_settings
                   where guild_id = p_guild), 3) into v_max;
  select count(*) into v_count from projects
   where guild_id = p_guild and creator_id = p_creator
     and status in ('pending','active','broken');
  if not p_bypass and v_count >= v_max then
    raise exception 'project_cap_reached' using errcode = 'P0001';
  end if;
  insert into projects (guild_id, name, creator_id)
       values (p_guild, p_name, p_creator) returning id into v_id;
  return v_id;
end $$;

revoke all on function reserve_project(bigint, bigint, text, boolean) from public, anon, authenticated;
