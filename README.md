# Project Orchestrator

A Discord bot that turns one server into a project-management community. Any member can create up to 3 projects; each project gets its own category and three roles (Owner, Member, Viewer), and owners manage their project's channels and people through slash commands.

**The bot is the gatekeeper.** Project owners get no Discord management permissions. Every action is a slash command, and the bot checks Supabase to confirm the invoker owns that specific project before it acts.

## Commands

| Command | Who | What it does |
| --- | --- | --- |
| `/project create name` | anyone | Creates the category, roles and a `#general` channel (60 s cooldown, 3 per user) |
| `/project delete project` | creator or admin | Deletes the category, every channel in it and the roles, after confirmation |
| `/project info project` | anyone | Owners, members, viewers and channels |
| `/project list` | anyone | Your projects, all active ones, and your remaining quota |
| `/channel create project name [type]` | owner | Text, voice or forum channel (15 per project by default) |
| `/channel rename / topic / delete channel` | owner | Only for channels inside your project's category |
| `/channel visibility channel public` | owner | Public = everyone can read, only project members can post |
| `/member set project user role` | owner | Adds someone or changes their tier (owner, member, viewer) |
| `/member remove project user` | owner | A project always keeps at least one owner |
| `/orchestrator settings [max_projects] [max_channels]` | admin | View or change the limits |
| `/orchestrator repair [project]` | admin | Check and fix drift (missing roles, category, overwrites) |

Server admins can act on every project and are exempt from the project cap.

## Setup

### 1. Discord application

1. Create an application at <https://discord.com/developers/applications> and add a bot.
2. Under **Bot**, enable the **Server Members Intent** (used to list role holders and to repair projects).
3. Invite it with the scopes `bot applications.commands` and these permissions: **Manage Roles, Manage Channels, View Channels, Send Messages, Send Messages in Threads, Create Public Threads, Add Reactions, Read Message History, Manage Messages, Connect, Speak**. Discord only lets the bot grant permissions it holds itself, so it needs every permission the project roles get. Permissions integer: `309509303376`.
   `https://discord.com/oauth2/authorize?client_id=<APP_ID>&scope=bot+applications.commands&permissions=309509303376`
4. In **Server settings → Roles**, drag the bot's role near the top. It can only manage roles below its own.
5. Keep **Manage Roles** limited to admins, so nobody can hand out project roles behind the bot's back.

### 2. Supabase

1. Create a Supabase project.
2. Apply the migrations in `supabase/migrations/`, either with the CLI (`supabase link --project-ref <ref>` then `supabase db push`) or by pasting them into the SQL editor in order.
3. Copy the **connection pooler** string (Project settings → Database → Connection string → Transaction pooler) into `DATABASE_URL`.

Every table has row level security enabled with no policies, so the public API keys can read nothing. The bot connects with the database connection string, which stays only in the bot's environment.

### 3. Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in DISCORD_TOKEN, DATABASE_URL, DEV_GUILD_ID
python -m bot.main
```

With `DEV_GUILD_ID` set, commands sync instantly to that server. Leave it empty in production to sync globally (can take up to an hour to appear).

Run `/ping` to check the bot is alive.

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `DISCORD_TOKEN` | yes | Bot token |
| `DATABASE_URL` | yes | Supabase pooler connection string |
| `DEV_GUILD_ID` | no | Server to sync commands to during development |
| `LOG_LEVEL` | no | `DEBUG`, `INFO` (default), `WARNING` |
| `LOG_FORMAT` | no | `json` for one JSON object per line |

## Deploy

The included `Dockerfile` runs the bot; any small VPS, Railway or Fly.io works. Set the environment variables above and leave `DEV_GUILD_ID` empty. The bot needs no inbound ports.

```bash
docker build -t orchestrator .
docker run --env-file .env orchestrator
```

## Development

```bash
pytest                      # unit and service tests (no Discord or database needed)
TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres pytest   # also run SQL tests
DATABASE_URL=... python -m scripts.check_cap   # smoke-test the 3-project cap against a real database
```

The database tests expect the migrations to be applied to that database (CI does this against Postgres 17).

### Layout

```
bot/
  main.py         Bot subclass: db pool, cogs, command sync, error handler
  config.py       environment settings
  errors.py       user-facing domain errors
  db/             asyncpg pool and repositories
  domain/         dataclasses and pure permission-overwrite builders
  services/       all rules: authz, projects, channels, members, reconcile
  cogs/           slash commands and event listeners (parse input, reply)
  ui/             confirmation buttons and autocomplete
supabase/migrations/
tests/
```

## Behaviour notes

- Project creation is a saga: reserve a row, create roles, category and `#general`, give the creator the Owner role, then activate. Any failure rolls back what was created.
- The bot listens for hand edits. A deleted project role or category is recreated, channels created by hand inside a project category are tracked, and deleted channels are untracked. On startup every project is checked; reservations stuck in `pending` for 10 minutes are cleaned up.
- Decisions on the plan's open questions, all easy to change: only the creator or an admin can delete a project; the cap slot stays with the creator; public channels are read-only for non-members (`public_can_post` exists in the schema for later); there is no archive state yet.
