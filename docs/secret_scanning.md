# Secret Scanning

## Why

The repo is public. A filename-based check (`git log --all --oneline -- '*.env' '*secrets*' '*.pem' '*.key'`)
had already ruled out secret-shaped filenames, but not secrets pasted inline in code/config
and later "cleaned up" without purging git history. This closes that gap with a content-based
scanner, run both as a one-time audit and continuously in CI.

## Tooling

[gitleaks](https://github.com/gitleaks/gitleaks) — chosen over trufflehog for simplicity: it's
a single static binary, fast, and rule-based, which is sufficient for catching accidentally
committed keys/tokens. Trufflehog's live-credential-verification is unnecessary overhead for a
repo where we expect zero real hits going forward.

Config: [`.gitleaks.toml`](../.gitleaks.toml) at repo root — extends gitleaks' default ruleset
and allowlists one confirmed false positive (see below).

## One-time audit result (2026-07-26)

Full git history (209 commits) + working tree scanned with:

```bash
gitleaks detect --source . --log-opts="--all" --config .gitleaks.toml
```

**Result: clean.** One finding surfaced before the allowlist was added:

- `automation/amazon_sp_api.py:58` — `A21TJRUUN4KGV`, flagged by the `generic-api-key` rule.
  This is Amazon's public India marketplace ID constant (documented in Amazon's SP-API docs),
  not a secret. Allowlisted in `.gitleaks.toml` by exact-value regex so it won't need re-review.

No real secrets were found. No credential rotation was required.

## CI enforcement

[`.github/workflows/secret-scan.yml`](../.github/workflows/secret-scan.yml) runs gitleaks on
every push to `main` and every pull request, using `--fetch-depth: 0` so full history is
available. **A finding fails the build** — this is the enforcement mechanism called for in the
originating issue; there is no separate rotation automation.

## If gitleaks reports a real finding

1. Treat the credential as compromised — rotate it immediately, regardless of whether the repo
   was ever actually cloned by anyone else. Do not just scrub git history and consider it handled.
2. Only after rotation, add a fingerprint-based (not value-based) allowlist entry if the
   commit itself must remain in history, or purge history if feasible.
3. Do not silence a CI failure by weakening the ruleset — narrow, justified allowlist entries
   only (see the marketplace-ID entry above for the expected shape).

## Local test coverage

`tests/test_secret_scan.py` checks the config and workflow files exist, and (when gitleaks is
installed locally) re-runs the same scan gitleaks-action runs in CI.
