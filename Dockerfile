FROM python:3.11-slim

WORKDIR /app

RUN pip install aiohttp beautifulsoup4 anthropic --break-system-packages

COPY job_scout.py .

CMD ["python", "-u", "job_scout.py"]
