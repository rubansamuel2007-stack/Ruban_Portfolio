"""Helpers: safe uploads, slugs, settings, resume links, email sending."""
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import current_app, url_for

from config import UPLOAD_DIR, UPLOAD_SUBDIRS
from extensions import db
from models import DEFAULT_SETTINGS, WebsiteSetting

IMAGE_KINDS = {"jpg", "png", "webp"}
DOC_KINDS = {"jpg", "png", "pdf"}
PDF_ONLY = {"pdf"}


class UploadError(Exception):
    pass


# ------------------------------------------------------------------ uploads
def sniff_kind(stream):
    """Detect the real file type from its first bytes (never trust the file name)."""
    head = stream.read(16)
    stream.seek(0)
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"%PDF"):
        return "pdf"
    return None


def save_upload(file_storage, subdir, allowed):
    """Validate and store an uploaded file. Returns 'subdir/filename' or None if nothing was uploaded."""
    if not file_storage or not file_storage.filename:
        return None
    if subdir not in UPLOAD_SUBDIRS:
        raise UploadError("Invalid upload folder.")
    kind = sniff_kind(file_storage.stream)
    if kind not in allowed:
        names = ", ".join(sorted(k.upper() for k in allowed))
        raise UploadError(f"'{file_storage.filename}' is not an allowed file type. Allowed: {names}.")
    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    limit = current_app.config["MAX_PDF_BYTES"] if kind == "pdf" else current_app.config["MAX_IMAGE_BYTES"]
    if size > limit:
        raise UploadError(f"'{file_storage.filename}' is too large (max {limit // (1024 * 1024)} MB).")
    folder = UPLOAD_DIR / subdir
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{kind}"
    file_storage.save(folder / name)
    return f"{subdir}/{name}"


def safe_upload_path(rel_path):
    """Resolve a relative upload path, returning None if it escapes the uploads folder."""
    if not rel_path:
        return None
    path = (UPLOAD_DIR / rel_path).resolve()
    try:
        path.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return path


def delete_upload(rel_path):
    path = safe_upload_path(rel_path)
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def upload_url(rel_path):
    return url_for("public.uploaded_file", filename=rel_path) if rel_path else ""


def file_kind_from_path(rel_path):
    return "pdf" if rel_path.lower().endswith(".pdf") else "image"


# ------------------------------------------------------------------ text helpers
def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:80] or "project"


def unique_slug(model, title, exclude_id=None):
    base = slugify(title)
    slug, n = base, 2
    while True:
        q = model.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(model.id != exclude_id)
        if q.first() is None:
            return slug
        slug = f"{base}-{n}"
        n += 1


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def is_valid_email(value):
    return bool(value) and len(value) <= 150 and bool(EMAIL_RE.match(value))


def is_valid_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def github_username(url):
    parts = [p for p in urlparse(url or "").path.split("/") if p]
    return parts[0] if parts else ""


# ------------------------------------------------------------------ settings
def get_settings():
    data = dict(DEFAULT_SETTINGS)
    for row in WebsiteSetting.query.all():
        data[row.key] = row.value or ""
    return data


def set_setting(key, value):
    row = WebsiteSetting.query.filter_by(key=key).first()
    if row is None:
        row = WebsiteSetting(key=key, value=value)
        db.session.add(row)
    else:
        row.value = value


# ------------------------------------------------------------------ resume
def _drive_id(url):
    match = re.search(r"/file/d/([A-Za-z0-9_\-]+)", url or "")
    return match.group(1) if match else None


def resume_info(settings):
    """Work out which resume the public site should use (the most recently saved: upload or URL)."""
    file_rel = settings.get("resume_file", "")
    url = settings.get("resume_url", "")
    if settings.get("resume_source") == "file" and file_rel and safe_upload_path(file_rel) and safe_upload_path(file_rel).is_file():
        view = upload_url(file_rel)
        return {"title": settings.get("resume_title"), "view_url": view, "preview_url": view,
                "download_url": url_for("public.resume_download"), "source": "file", "available": True}
    drive = _drive_id(url)
    if url:
        preview = f"https://drive.google.com/file/d/{drive}/preview" if drive else url
        return {"title": settings.get("resume_title"), "view_url": url, "preview_url": preview,
                "download_url": url_for("public.resume_download"), "source": "url", "available": True}
    return {"title": settings.get("resume_title"), "view_url": "", "preview_url": "",
            "download_url": "", "source": "none", "available": False}


def resume_download_target(settings):
    """Direct download URL for an external resume link."""
    url = settings.get("resume_url", "")
    drive = _drive_id(url)
    if drive:
        return f"https://drive.google.com/uc?export=download&id={drive}"
    return url


# ------------------------------------------------------------------ email
def send_contact_email(msg):
    """Send a contact message through the Resend API. Returns (ok, error_text)."""
    cfg = current_app.config
    if not cfg["RESEND_API_KEY"]:
        return False, "RESEND_API_KEY is not configured"
    subject = re.sub(r"[\r\n]+", " ", msg.subject)[:150]
    body = (
        f"New message from your portfolio website\n\n"
        f"Name:    {msg.name}\nEmail:   {msg.email}\nSubject: {subject}\n\n{msg.message}\n"
    )
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {cfg['RESEND_API_KEY']}", "Content-Type": "application/json"},
            json={"from": cfg["RESEND_FROM_EMAIL"], "to": [cfg["CONTACT_TO_EMAIL"]], "reply_to": msg.email,
                  "subject": f"[Portfolio] {subject}", "text": body},
            timeout=10,
        )
    except requests.RequestException as exc:
        return False, f"network error: {exc.__class__.__name__}"
    if resp.status_code >= 400:
        return False, f"Resend returned {resp.status_code}: {resp.text[:200]}"
    return True, ""


# ------------------------------------------------------------------ ordering
def next_position(model, top=False, **filters):
    rows = [r.position for r in model.query.filter_by(**filters).all()]
    if not rows:
        return 0
    return (min(rows) - 1) if top else (max(rows) + 1)


def reorder(model, item, direction, scope=None):
    q = model.query
    if scope is not None:
        q = q.filter(scope)
    items = q.order_by(model.position, model.id).all()
    for i, it in enumerate(items):
        it.position = i
    idx = items.index(item)
    j = idx - 1 if direction == "up" else idx + 1
    if 0 <= j < len(items):
        items[idx].position, items[j].position = items[j].position, items[idx].position
    db.session.commit()
