# Clip Worker

This service downloads a video from **Google Drive**, cuts clips using **FFmpeg**, and saves them locally on the host machine.

It is designed to be triggered by **n8n** and exposed externally via a **Cloudflare Tunnel**.

---

# Prerequisites

Install the following tools:

- Docker
- Docker Compose
- Cloudflare Tunnel (`cloudflared`)
- n8n
- Google Cloud service account with Drive API access

Create the following project structure:

```
clip-worker/
  docker-compose.yml
  Dockerfile
  app/
    app.py
    requirements.txt
  secrets/
    service_account.json
```

Create the output directory for clips:

```bash
mkdir -p ~/clips-output
```

---

## Step 1 — Share your Google Drive folder with the service account

Open your service account file:

```
secrets/service_account.json
```

Find the `client_email` field:

```
clip-worker@your-project-id.iam.gserviceaccount.com
```

Share the Google Drive folder where you upload videos with this email.

Permission required: **Viewer**

This allows the worker to download the original video.

---

## Step 2 — Start the clip worker

From the project root:

```bash
docker compose up --build
```

The API should now be running locally on:

```
http://localhost:8080
```

---

## Step 3 — Verify the service is running

Run a health check:

```bash
curl http://localhost:8080/health
```

Expected response:

```json
{"ok": true}
```

You can also open in a browser:

```
http://localhost:8080/health
```

---

## Step 4 — Start the Cloudflare tunnel

Expose the local API so n8n can reach it.

Run:

```bash
cloudflared tunnel --url http://localhost:8080
```

Cloudflare will generate a public URL such as:

```
https://random-name.trycloudflare.com
```

---

## Step 5 — Configure n8n

Create an **HTTP Request** node.

Example configuration:

```
POST https://random-name.trycloudflare.com/clip
```

Example request body:

```json
{
  "driveFileId": "={{$json.id}}",
  "fileName": "={{$json.name}}",
  "fastCopy": false,
  "clips": [
    {
      "start": "00:00:10",
      "end": "00:00:25",
      "name": "clip_1"
    }
  ]
}
```

---

## Step 6 — Output location

Generated clips are saved locally on the host machine:

```
~/clips-output/
```

Folder structure:

```
clips-output/
  video-name/
    job-id/
      clip_001.mp4
      clip_002.mp4
```

You can preview, delete, or upload clips from this folder.

---

## Workflow Overview

```
Upload video → Google Drive
        ↓
n8n trigger
        ↓
HTTP request → clip-worker
        ↓
Download video from Drive
        ↓
FFmpeg cuts clips
        ↓
Clips saved locally
```

---

## Stopping the service

```bash
docker compose down
```

---

## Viewing logs

```bash
docker compose logs -f
```
