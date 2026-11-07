"""Public website routes + small JSON APIs (contact form, GitHub data)."""
import time
from datetime import timedelta

import requests
from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)

from config import UPLOAD_DIR
from extensions import csrf, db, limiter
from models import (SKILL_CATEGORIES, Certificate, ContactMessage, Experience, Profile, Project,
                    Skill, utcnow)
from utils import (get_settings, github_username, is_valid_email, resume_download_target,
                   safe_upload_path)

bp = Blueprint("public", __name__)

_gh_cache = {"ts": 0.0, "user": None, "data": None}


def group_skills(skills):
    """Group enabled skills by category in a sensible order."""
    groups = {}
    for s in skills:
        groups.setdefault(s.category, []).append(s)
    ordered = [c for c in SKILL_CATEGORIES if c in groups]
    ordered += sorted(c for c in groups if c not in SKILL_CATEGORIES)
    return [(c, groups[c]) for c in ordered]


@bp.route("/")
def index():
    skills = Skill.query.filter_by(enabled=True).order_by(Skill.position, Skill.id).all()
    projects = Project.query.filter_by(published=True).order_by(Project.position, Project.id).all()
    return render_template(
        "index.html",
        skill_groups=group_skills(skills),
        projects=projects,
        featured=[p for p in projects if p.featured][:3],
        categories=sorted({p.category for p in projects if p.category}),
        experiences=Experience.query.filter_by(published=True).order_by(Experience.position, Experience.id).all(),
        certificates=Certificate.query.filter_by(published=True).order_by(Certificate.position, Certificate.id).all(),
        skill_count=len(skills),
    )


@bp.route("/project/<slug>")
def project_detail(slug):
    project = Project.query.filter_by(slug=slug, published=True).first_or_404()
    return render_template("project_detail.html", project=project)


@bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    path = safe_upload_path(filename)
    if path is None or not path.is_file():
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename, max_age=3600)


@bp.route("/resume/download")
def resume_download():
    settings = get_settings()
    rel = settings.get("resume_file", "")
    path = safe_upload_path(rel)
    if settings.get("resume_source") == "file" and path and path.is_file():
        return send_from_directory(UPLOAD_DIR, rel, as_attachment=True, download_name="Ruban_S_Resume.pdf")
    target = resume_download_target(settings)
    if not target:
        abort(404)
    return redirect(target)


@bp.route("/robots.txt")
def robots():
    body = f"User-agent: *\nDisallow: /admin/\nSitemap: {url_for('public.sitemap', _external=True)}\n"
    return current_app.response_class(body, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    urls = [url_for("public.index", _external=True)]
    urls += [url_for("public.project_detail", slug=p.slug, _external=True)
             for p in Project.query.filter_by(published=True).all()]
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "".join(f"<url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>")
    return current_app.response_class(xml, mimetype="application/xml")


# ---------------------------------------------------------------- contact form API
@bp.route("/api/contact", methods=["POST"])
@limiter.limit("5 per hour;15 per day")
def contact():
    from utils import send_contact_email  # local import keeps module load light

    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()

    # Spam protection 1: honeypot field that real visitors never see or fill.
    if (data.get("website") or "").strip():
        return jsonify({"ok": True, "message": "Thank you! Your message has been sent."})

    # Spam protection 2: forms submitted faster than a human could type.
    try:
        elapsed = float(data.get("elapsed_ms") or 0)
    except (TypeError, ValueError):
        elapsed = 0
    if elapsed < 2500:
        return jsonify({"ok": False, "error": "That was very fast. Please take a moment and try again."}), 400

    errors = {}
    if not 2 <= len(name) <= 100:
        errors["name"] = "Please enter your name (2-100 characters)."
    if not is_valid_email(email):
        errors["email"] = "Please enter a valid email address."
    if not 3 <= len(subject) <= 150:
        errors["subject"] = "Please enter a subject (3-150 characters)."
    if not 10 <= len(message) <= 3000:
        errors["message"] = "Your message must be between 10 and 3000 characters."
    if errors:
        return jsonify({"ok": False, "error": "Please fix the highlighted fields.", "fields": errors}), 400

    # Spam protection 3: the same person sending the same text again within 10 minutes.
    since = utcnow() - timedelta(minutes=10)
    duplicate = ContactMessage.query.filter(
        ContactMessage.email == email, ContactMessage.message == message, ContactMessage.created_at >= since
    ).first()
    if duplicate:
        return jsonify({"ok": False, "error": "This message was already sent. Thank you!"}), 409

    msg = ContactMessage(name=name, email=email, subject=subject, message=message,
                         ip_address=(request.remote_addr or "")[:64])
    db.session.add(msg)
    db.session.commit()  # always keep a copy in the database, even if email delivery fails

    ok, err = send_contact_email(msg)
    if ok:
        msg.email_sent = True
        db.session.commit()
    else:
        current_app.logger.warning("Contact email not delivered: %s", err)
    return jsonify({"ok": True, "message": "Thank you! Your message has been sent. I'll get back to you soon."})


# ---------------------------------------------------------------- GitHub API (cached)
@bp.route("/api/github")
@limiter.limit("60 per hour")
def github():
    profile = Profile.query.first()
    username = github_username(profile.github_url if profile else "")
    if not username:
        return jsonify({"ok": False, "error": "No GitHub profile is configured."}), 404

    ttl = current_app.config["GITHUB_CACHE_SECONDS"]
    cached = _gh_cache["data"] if _gh_cache["user"] == username else None
    if cached and time.time() - _gh_cache["ts"] < ttl:
        return jsonify(cached)

    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ruban-portfolio"}
    token = current_app.config["GITHUB_TOKEN"]
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        user_resp = requests.get(f"https://api.github.com/users/{username}", headers=headers, timeout=8)
        if user_resp.status_code == 404:
            return jsonify({"ok": False, "error": "GitHub user not found."}), 404
        if user_resp.status_code in (403, 429):
            raise RuntimeError("rate limited")
        user_resp.raise_for_status()
        repo_resp = requests.get(f"https://api.github.com/users/{username}/repos", headers=headers,
                                 params={"sort": "pushed", "per_page": 30}, timeout=8)
        repo_resp.raise_for_status()
        u = user_resp.json()
        repos = [r for r in repo_resp.json() if not r.get("fork")][:6]
        payload = {
            "ok": True,
            "user": {"login": u.get("login"), "name": u.get("name"), "avatar_url": u.get("avatar_url"),
                     "bio": u.get("bio"), "public_repos": u.get("public_repos", 0),
                     "followers": u.get("followers", 0), "html_url": u.get("html_url")},
            "repos": [{"name": r["name"], "description": r.get("description"), "html_url": r["html_url"],
                       "language": r.get("language"), "stars": r.get("stargazers_count", 0),
                       "updated_at": r.get("pushed_at")} for r in repos],
        }
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        current_app.logger.warning("GitHub API error: %s", exc)
        if cached:  # serve slightly old data rather than an error
            return jsonify(dict(cached, stale=True))
        return jsonify({"ok": False, "error": "GitHub data is temporarily unavailable."}), 502

    _gh_cache.update(ts=time.time(), user=username, data=payload)
    return jsonify(payload)
