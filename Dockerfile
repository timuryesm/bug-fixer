# Sandbox image for running target repos' test suites in isolation.
# Built once, reused across all bug-fixing runs.

FROM python:3.13-slim

# Install pytest into the image so it's always available, even if the target
# repo's own dependencies don't pull it in. --no-cache-dir keeps the image
# smaller by not retaining pip's download cache.
RUN pip install --no-cache-dir pytest

# Working directory for mounted target repos.
WORKDIR /work

# Make Python output unbuffered so we get test progress in real time,
# not all at once when the container exits.
ENV PYTHONUNBUFFERED=1

# No CMD on purpose — `docker run` always specifies what to execute.