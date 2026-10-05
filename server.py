import os
import shutil
import tempfile
import urllib.parse
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, jsonify, request, send_file, send_from_directory

app = Flask(__name__, static_folder=None)
BASE = os.path.dirname(os.path.abspath(__file__))

# Only these sites are accepted
ALLOWED = ("youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com")
BASE_OPTS = {"quiet": True, "no_warnings": True, "noplaylist": True}


def allowed(url):
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https"):
        return False
    return any(host == d or host.endswith("." + d) for d in ALLOWED)


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/<name>")
def static_files(name):
    if name in ("background.jpg", "youtube.png", "facebook.png", "tiktok.png"):
        return send_from_directory(BASE, name)
    return jsonify(error="Not found"), 404


@app.post("/api/info")
def info():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not allowed(url):
        return jsonify(error="Only YouTube, Facebook and TikTok links are supported."), 400
    try:
        with yt_dlp.YoutubeDL({**BASE_OPTS, "skip_download": True}) as ydl:
            d = ydl.extract_info(url, download=False)
    except Exception:
        return jsonify(error="Could not read this link. Check the URL or try again."), 422
    return jsonify(
        title=d.get("title") or "Video Ready",
        thumbnail=d.get("thumbnail"),
        uploader=d.get("uploader"),
        duration=d.get("duration"),
    )


@app.get("/api/download")
def download():
    url = (request.args.get("url") or "").strip()
    fmt = request.args.get("format", "video")
    quality = request.args.get("quality", "HD")
    if not allowed(url):
        return jsonify(error="Only YouTube, Facebook and TikTok links are supported."), 400

    tmp = tempfile.mkdtemp(prefix="kod_")
    opts = {**BASE_OPTS, "outtmpl": os.path.join(tmp, "%(title).80s.%(ext)s")}

    if fmt == "mp3":
        opts.update(
            format="bestaudio/best",
            postprocessors=[{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        )
    else:
        h = 1080 if quality == "HD" else 360
        opts.update(
            format=f"bv*[height<={h}]+ba/b[height<={h}]/b",
            merge_output_format="mp4",
        )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = [f for f in os.listdir(tmp) if not f.endswith(".part")]
        path = max((os.path.join(tmp, f) for f in files), key=os.path.getsize)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return jsonify(error="Download failed. The video may be private, removed or blocked."), 422

    resp = send_file(path, as_attachment=True, download_name=os.path.basename(path))
    resp.headers["X-Filename"] = urllib.parse.quote(os.path.basename(path))
    resp.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
