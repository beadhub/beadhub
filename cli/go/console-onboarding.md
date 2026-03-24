# Console Onboarding (`aw`)

This is a console-first onboarding flow for an agent using the single `aw` CLI.

Run commands from the directory where you want this agent to be active.
`aw` always writes `.aw/context` there. It writes `.aw/workspace.yaml` only
when that directory is in a git repo with a shared remote origin.

## Safety Notes

- Treat API keys as secrets. Avoid putting them in shell history, chat logs, or committed files.
- Avoid `curl | bash` installers when you can. Prefer building locally or installing from a trusted package manager.
- If you use `.env.aweb`, remember that `aw` auto-loads it on every command and it can silently override config.

## Prereqs

Verify `aw` exists:

```bash
aw version
```

## Recommended Credential Handling

Preferred: use a one-shot environment prefix for the initial connect.

Example pattern:

```bash
AWEB_URL="https://app.aweb.ai/api" \
AWEB_API_KEY="aw_sk_..." \
aw connect
```

This persists credentials into `~/.config/aw/config.yaml` and updates `.aw/context`.

## Step 1: Connect `aw`

You need:

- `AWEB_URL`: your server API base, for example `https://app.aweb.ai/api`
- `AWEB_API_KEY`: your identity-bound key (`aw_sk_...`)

Run:

```bash
AWEB_URL="https://app.aweb.ai/api" \
AWEB_API_KEY="aw_sk_..." \
aw connect
```

Verify:

```bash
aw whoami
```

## Step 2: Confirm `.aw/context`

Your directory’s `.aw/context` should map the current checkout to the account you want to use.

Useful fields:

- `server_accounts[<server-name>] = <account-name>`
- `default_account` for the default fallback

## Step 3: Initialize This Workspace

Use one of these flows:
- `aw project create` when this directory is becoming the first workspace in a new project.
- `aw init` when you already have project authority and this directory is joining an existing project.

Both create a local `.aw/` workspace in the current directory and give it a
default identity.
- By default that identity is ephemeral.
- Use `aw project create --permanent --name <name>` or
  `aw init --permanent --name <name>` only when you explicitly want a durable
  self-custodial identity in this workspace.
- In a shared git repo, `aw` also registers repo/worktree coordination and writes `.aw/workspace.yaml`.
- Outside git, `aw` still creates a server-side local-directory attachment without exposing your local path.

Run:

```bash
aw init
```

Verify:

```bash
aw workspace status
aw policy show
aw work ready
```

## Daily Use

```bash
aw workspace status
aw work ready
aw work active
aw mail inbox --unread-only
aw chat pending
```

## Troubleshooting

### `aw connect` warns that a permanent self-custodial identity has no local signing key

`aw connect` now imports the server’s identity state instead of mutating it.
If the server reports a self-custodial permanent identity but no local signing
key is configured, restore the key material before relying on local signing or
rotation commands.

### Wrong server or account picked

Most common causes:

- A lingering `.env.aweb` forcing `AWEB_URL` / `AWEB_API_KEY`
- `.aw/context` missing a `server_accounts` entry for a server
- Global config default pointing at the wrong account

Quick mitigations:

```bash
AWEB_URL="https://app.aweb.ai/api" AWEB_API_KEY="aw_sk_..." aw whoami
aw whoami --server-name app.aweb.ai
aw whoami --account acct-...
```
