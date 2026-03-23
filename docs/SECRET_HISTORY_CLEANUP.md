# Secret History Cleanup Runbook

Use this runbook after any secret is committed.

## 1) Rotate the exposed key immediately

1. Revoke the leaked key at the provider dashboard.
2. Create a replacement key.
3. Update deployment and local environments with the new key.

## 2) Remove secrets from git history

Preferred tool: `git filter-repo`.

```bash
pip install git-filter-repo
git filter-repo --path .env --invert-paths
```

If only one line needs replacement in history, use `--replace-text`:

```bash
cat > replacements.txt <<'EOF'
sk-proj-==>REDACTED_OPENAI_KEY
EOF
git filter-repo --replace-text replacements.txt
```

## 3) Force push rewritten history

```bash
git push --force --all
git push --force --tags
```

## 4) Invalidate old clones

All collaborators must re-clone or hard reset to the rewritten history.

## 5) Verify cleanup

```bash
git log -p -- .env
git grep -n "sk-proj-" $(git rev-list --all)
```

Both checks must return no leaked secret.

## 6) Prevent recurrence

1. Keep `.env` ignored.
2. Use `.env.example` placeholders only.
3. Enable pre-commit secret scanning (`scripts/install_git_hooks.ps1`).
