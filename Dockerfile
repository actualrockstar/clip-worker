FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

COPY app /srv/app

# work dir for temp files
RUN mkdir -p /work

EXPOSE 8080
CMD ["uvicorn", "app.app:app", "--host", "0.0.0.0", "--port", "8080"]