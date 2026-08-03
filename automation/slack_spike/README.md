# Slack delivery spike

Staged proof for [#38](https://github.com/hd-stack-1858/tcb-demand-planning/issues/38)
(Slack report delivery), de-risking each layer before the next:

1. **Local docker → report saved locally** — `generate_report.py` alone. Proves
   Docker build/run/volume-mount mechanics with zero external dependencies.
2. **Local docker → Slack** — `run_stage2.sh` (generate, then `post_to_slack.py`).
   Proves the Slack Web API upload flow works, still running on a local machine.
3. **Cloud docker → Slack** — same image, deployed as a Cloud Run Job (reusing
   the pattern proven in `automation/gcp_spike/`). Proves it end-to-end from
   the actual production environment.

Slack delivery uses the Web API directly (`chat.postMessage` / the
`files.getUploadURLExternal` → upload → `files.completeUploadExternal` flow) —
**no SMTP involved**. SMTP is specific to the existing Gmail-based email
alerts (`automation/email_sender.py`), a completely separate mechanism.

## Required credentials (you create these — see below)

| Var | What |
|---|---|
| `SLACK_BOT_TOKEN` | `xoxb-...` token, scopes: `chat:write`, `files:write` |
| `SLACK_CHANNEL_ID` | Channel to post to — bot must be invited to it |

Create the Slack app at api.slack.com/apps → From scratch → add the two Bot
Token Scopes above under OAuth & Permissions → Install to Workspace → copy the
Bot User OAuth Token. Invite the bot to the target channel
(`/invite @<app name>`), then get the channel ID from its channel details panel.

## Running stage 1 (no credentials needed)

```bash
docker build -t slack-spike-stage1 automation/slack_spike/
docker run --rm -v "$(pwd)/output:/output" slack-spike-stage1 python generate_report.py
```

## Running stage 2

```bash
docker build -t slack-spike-stage2 automation/slack_spike/
docker run --rm \
  -e SLACK_BOT_TOKEN=<token> \
  -e SLACK_CHANNEL_ID=<channel-id> \
  -v "$(pwd)/output:/output" \
  slack-spike-stage2
```

## Stage 3 (later)

Once 1 and 2 are proven, deploy the same image as a Cloud Run Job — same
`gcloud run jobs deploy` / Secret Manager pattern already used in
`automation/gcp_spike/03_deploy_job.sh`, with `SLACK_BOT_TOKEN` as a secret
instead of a local env var.
