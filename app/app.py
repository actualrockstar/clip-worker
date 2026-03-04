import io
import os
import shutil
import subprocess
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account


# ---------------- Config ----------------
WORKDIR = os.getenv("WORKDIR", "/work")
OUTPUT_BASE = os.getenv("OUTPUT_BASE", "/clips")
FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")

# Prefer OAuth token (personal Drive) if present; fallback to service account if present.
TOKEN_FILE = os.getenv("TOKEN_FILE", "/secrets/token.json")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/secrets/service_account.json")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# --------------------------------------


app = FastAPI(title="Clip Worker", version="1.1")


class ClipSpec(BaseModel):
    start: str = Field(..., description="Timestamp like 00:00:10.500")
    end: str = Field(..., description="Timestamp like 00:00:25.000")
    name: Optional[str] = Field(None, description="Optional clip name; .mp4 will be added")


class ClipRequest(BaseModel):
    driveFileId: str
    fileName: Optional[str] = None
    clips: List[ClipSpec]
    # If true, do fast stream-copy cutting (may be slightly inaccurate)
    fastCopy: bool = False


def drive_client():
    """
    Build a Google Drive client using either:
    - OAuth token.json (preferred for personal Google Drive), or
    - Service account JSON (works best with Shared Drives / Workspace, but can read shared folders too).

    We only need read access (download the input video), so drive.readonly is enough.
    """
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    if os.path.exists(SERVICE_ACCOUNT_FILE):
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    raise RuntimeError(
        "No Google auth found. Provide either /secrets/token.json (OAuth) "
        "or /secrets/service_account.json (service account) to download from Google Drive."
    )


def download_drive_file(service, file_id: str, out_path: str):
    request = service.files().get_media(fileId=file_id)
    with io.FileIO(out_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def run_ffmpeg_cut(input_path: str, start: str, end: str, out_path: str, fast_copy: bool):
    # Frame-accurate (re-encode) by default
    if fast_copy:
        cmd = [FFMPEG, "-y", "-ss", start, "-to", end, "-i", input_path, "-c", "copy", out_path]
    else:
        cmd = [
            FFMPEG, "-y",
            "-ss", start, "-to", end,
            "-i", input_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            out_path
        ]

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-2000:]}")


def safe_fs_name(name: str) -> str:
    """
    Make a filename safe-ish for folders across macOS/Windows/Linux.
    """
    name = name.strip().replace("/", "_").replace("\\", "_")
    # Keep it simple; you can expand this if needed
    return "".join(c if c.isalnum() or c in (" ", "_", "-", ".") else "_" for c in name).strip()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/clip")
def clip(req: ClipRequest):
    if not req.clips:
        raise HTTPException(status_code=400, detail="clips[] is empty")

    os.makedirs(WORKDIR, exist_ok=True)
    os.makedirs(OUTPUT_BASE, exist_ok=True)

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(WORKDIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    input_path = os.path.join(job_dir, "input_video")

    try:
        service = drive_client()

        # If fileName wasn't provided, fetch it for nicer output folder naming
        if not req.fileName:
            meta = service.files().get(fileId=req.driveFileId, fields="name,mimeType").execute()
            req.fileName = meta.get("name", "video.mp4")

        video_stem = os.path.splitext(req.fileName)[0] or "video"
        video_stem = safe_fs_name(video_stem)

        # Persistent output folder (mounted from host)
        out_dir = os.path.join(OUTPUT_BASE, video_stem, job_id)
        os.makedirs(out_dir, exist_ok=True)

        # Download source video to temp
        download_drive_file(service, req.driveFileId, input_path)

        results = []
        for i, clip_spec in enumerate(req.clips, start=1):
            base = clip_spec.name or f"{video_stem}_clip_{i:03d}"
            base = safe_fs_name(base)
            out_filename = f"{base}.mp4"
            out_path = os.path.join(out_dir, out_filename)

            run_ffmpeg_cut(input_path, clip_spec.start, clip_spec.end, out_path, req.fastCopy)

            results.append({
                "name": out_filename,
                "localPath": out_path
            })

        return {
            "jobId": job_id,
            "sourceFileName": req.fileName,
            "outputDir": out_dir,
            "clipsSaved": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Always clean temp (downloaded input + scratch). Outputs remain on host.
        shutil.rmtree(job_dir, ignore_errors=True)