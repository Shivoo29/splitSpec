FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace

# Fixture + test deps only. The sandbox never gets the model API key.
COPY docker/sandbox-requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

CMD ["pytest", "-q"]
