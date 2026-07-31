FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir requests
COPY generate_report.py post_to_slack.py run_stage2.sh .
RUN chmod +x run_stage2.sh

ENTRYPOINT ["./run_stage2.sh"]
