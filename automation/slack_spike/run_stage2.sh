#!/bin/sh
# Stage 2: generate the synthetic report, then post it to Slack.
set -e

REPORT_PATH=$(python generate_report.py | sed -n 's/^Wrote: //p')
echo "Generated: $REPORT_PATH"

python post_to_slack.py "$REPORT_PATH"
