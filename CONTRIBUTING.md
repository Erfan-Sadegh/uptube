# Contributing to Uptube

## Access Model

Every contributor uses their own GitHub account. Do not share SSH keys, `.env` files, API keys, Google OAuth secrets, or Metis tokens.

For the easiest setup on Windows, use HTTPS cloning with Git Credential Manager or GitHub Desktop. SSH is fine for developers who already know it, but it is not required.

## Recommended Beginner Flow

1. Ask the repo owner to add your GitHub account as a collaborator.
2. Clone with HTTPS:

```powershell
git clone https://github.com/Erfan-Sadegh/uptube.git
cd uptube
```

3. When Git asks for login, use the browser-based GitHub sign-in window. Do not paste passwords or tokens into chat.
4. Copy local config:

```powershell
Copy-Item .env.example .env
```

5. Fill `.env` with your own local development values.
6. Install and run using the project docs:

```powershell
.\scripts\start-local.ps1
```

## Daily Git Rules

- Pull before starting work:

```powershell
git pull
```

- Check what changed before committing:

```powershell
git status
git diff
```

- Commit small, meaningful changes:

```powershell
git add .
git commit -m "Describe the change"
```

- Push your branch:

```powershell
git push
```

## What Must Never Be Committed

- `.env`
- API keys and OAuth secrets
- local SQLite databases
- downloaded videos/audio
- `node_modules`
- `.next`
- logs

These are already covered by `.gitignore`, but always check `git status` before committing.
