import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from threading import Thread

import instaloader
from flask import Flask, render_template, request, send_file

app = Flask(__name__)


def username_from_input(value):
    value = (value or "").strip()

    match = re.search(
        r"(?:www\.)?instagram\.com/([A-Za-z0-9._]+)",
        value,
        re.IGNORECASE
    )

    if match:
        username = match.group(1)
    else:
        username = value.lstrip("@").split("?")[0].strip("/")

    if not re.fullmatch(r"[A-Za-z0-9._]+", username):
        raise ValueError("Informe um perfil válido do Instagram.")

    return username


def cleanup_later(workdir):
    """Remove os arquivos temporários após um intervalo."""
    import time
    time.sleep(900)
    shutil.rmtree(workdir, ignore_errors=True)


@app.route("/", methods=["GET", "POST"])
def index():

    if request.method == "GET":
        return render_template("index.html")

    workdir = Path(tempfile.mkdtemp(prefix="reels_"))

    try:
        username = username_from_input(
            request.form.get("profile")
        )

        limit = int(request.form.get("limit", 10))
        limit = min(max(limit, 1), 50)

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
            quiet=True
        )

        profile = instaloader.Profile.from_username(
            loader.context,
            username
        )

        count = 0

        for post in profile.get_posts():

            if not post.is_video:
                continue

            loader.download_post(
                post,
                target=username
            )

            count += 1

            if count >= limit:
                break

        videos = list(
            (workdir / username).glob("*.mp4")
        )

        if not videos:
            raise RuntimeError(
                "Nenhum vídeo público foi encontrado."
            )

        zip_path = workdir / (
            f"{username}_ultimos_{len(videos)}_videos.zip"
        )

        with zipfile.ZipFile(
            zip_path,
            "w",
            zipfile.ZIP_STORED
        ) as archive:

            for video in videos:
                archive.write(
                    video,
                    arcname=video.name
                )

        response = send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_path.name,
            mimetype="application/zip"
        )

        Thread(
            target=cleanup_later,
            args=(workdir,),
            daemon=True
        ).start()

        return response

    except Exception as exc:

        shutil.rmtree(
            workdir,
            ignore_errors=True
        )

        message = str(exc)
        lower_message = message.lower()

        if any(term in lower_message for term in [
            "401",
            "403",
            "429",
            "login",
            "rate limit",
            "please wait"
        ]):
            message = (
                "O Instagram bloqueou ou limitou a consulta "
                "automática. Tente novamente mais tarde."
            )

        elif "404" in lower_message:
            message = (
                "Perfil não encontrado ou indisponível."
            )

        return render_template(
            "index.html",
            error=message
        ), 400


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
            )
