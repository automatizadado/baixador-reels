import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import instaloader
from flask import Flask, render_template, request, send_file, after_this_request

app = Flask(__name__)

def username_from_input(value):
    value = (value or "").strip()
    match = re.search(r"instagram\.com/([A-Za-z0-9._]+)", value)
    username = match.group(1) if match else value.lstrip("@").split("?")[0].strip("/")
    if not re.fullmatch(r"[A-Za-z0-9._]+", username):
        raise ValueError("URL ou usuário inválido.")
    return username

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("index.html")

    workdir = Path(tempfile.mkdtemp(prefix="reels_"))
    try:
        username = username_from_input(request.form.get("profile"))
        limit = min(max(int(request.form.get("limit", 50)), 1), 50)

        loader = instaloader.Instaloader(
            dirname_pattern=str(workdir / "{target}"),
            filename_pattern="{date_utc}_UTC_{shortcode}",
            download_pictures=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            quiet=True,
        )

        profile = instaloader.Profile.from_username(loader.context, username)
        count = 0

        for post in profile.get_posts():
            if post.is_video:
                loader.download_post(post, target=username)
                count += 1
                if count >= limit:
                    break

        if count == 0:
            raise RuntimeError("Nenhum vídeo público foi encontrado.")

        zip_path = workdir / f"{username}_ultimos_{count}_videos.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for video in (workdir / username).glob("*.mp4"):
                archive.write(video, video.name)

        @after_this_request
        def cleanup(response):
            shutil.rmtree(workdir, ignore_errors=True)
            return response

        return send_file(zip_path, as_attachment=True, download_name=zip_path.name)

    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        message = str(exc)
        low = message.lower()
        if "401" in message or "429" in message or "login" in low:
            message = (
                "O Instagram recusou a consulta anônima ou aplicou um limite temporário. "
                "Tente novamente mais tarde."
            )
        return render_template("index.html", error=message), 400

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
