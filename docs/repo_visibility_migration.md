# Repo Visibility Migration — Public → Private

## Why this was investigated

The repo (`hd-stack-1858/tcb-demand-planning`) is currently public. The stated assumption
(#2) was that this was required by Streamlit Community Cloud, which supposedly needed either
a public repo or a PAT-based connection to deploy. That assumption was never documented or
verified — this doc replaces the assumption with a confirmed answer.

## Finding: the assumption was wrong

**Streamlit Community Cloud fully supports deploying from private repositories.** No PAT is
required. Source: [Streamlit's official docs](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-account/manage-your-github-connection).

How it works:
- Community Cloud connects to GitHub via OAuth. The default OAuth scope only covers public
  repos.
- To deploy from a private repo, you grant Community Cloud the additional `repo` OAuth scope.
  Streamlit then creates a **read-only GitHub Deploy Key** and pulls the repo over SSH — not a
  PAT.
- You must have **admin** permission on the repo to deploy it (already true for the current
  owner/collaborators here).
- GitHub notifies repo admins whenever Streamlit creates that read-only deploy key, as a
  security transparency measure.

**Caveat to flag to PV:** even with the source repo private, the *deployed app URL* itself is
still publicly reachable unless viewer restrictions are separately configured in Community
Cloud's app settings. Making the repo private stops public code/history access — it does not
by itself make the running app private. If the app itself needs to be gated, that's a separate
Streamlit Cloud setting, out of scope for this issue.

There is no technical blocker to flipping this repo to private. The public-repo requirement
this issue was predicated on does not exist (or no longer exists) for Community Cloud.

## Test plan for the switch

Run in order — do not flip visibility until steps 1–2 pass, and do not consider the migration
done until steps 3–5 pass:

1. **Baseline (repo still public):** Confirm both Streamlit apps (`ui/tinysteps_app.py`,
   `ui/growthspurt_app.py`) are currently deployed and reachable on Community Cloud. Note their
   current app URLs.
2. **Local smoke test:** `streamlit run ui/tinysteps_app.py` and
   `streamlit run ui/growthspurt_app.py` locally against `TCB_ENV=dev` — confirm both load
   without errors. This isolates "did the flip break something" from "was something already
   broken."
3. **Flip visibility:** Repo owner (PV) changes repo visibility to private via GitHub repo
   Settings → Danger Zone → Change visibility.
4. **Grant Streamlit Cloud private-repo access:** In Streamlit Community Cloud → account
   settings → GitHub connection, re-authorize with the `repo` OAuth scope so Community Cloud
   can access the now-private repo. Expect a GitHub notification about a new deploy key being
   created per app/repo.
5. **Post-flip verification:** Confirm both apps still build and serve without a manual
   redeploy being required beyond the re-authorization step. If Community Cloud shows a broken
   connection, re-link each app's GitHub source in its app settings.
6. **Rollback plan:** If step 5 fails and can't be resolved quickly, flip the repo back to
   public immediately — Community Cloud deploys degrade gracefully back to public-repo access
   without further action.

## Decision

Research + documentation only in this pass. Per PV, the actual visibility flip (step 3) and
Streamlit Cloud reconnection (step 4) are executed by PV directly — not by the coding agent —
because of the blast radius (affects all collaborator access) called out in the issue.
