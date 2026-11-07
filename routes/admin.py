"""Private admin dashboard: authentication + CRUD for every kind of content."""
import hmac
import io
import os
import sqlite3
import tempfile
import zipfile
from datetime import date

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request, send_file,
                   session, url_for)
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from config import UPLOAD_DIR, UPLOAD_SUBDIRS
from extensions import db, limiter
from models import (SKILL_CATEGORIES, Admin, Certificate, ContactMessage, Experience, Profile, Project,
                    Skill, utcnow)
from utils import (DOC_KINDS, IMAGE_KINDS, PDF_ONLY, UploadError, delete_upload, file_kind_from_path,
                   get_settings, is_valid_email, is_valid_url, next_position, reorder, safe_upload_path,
                   save_upload, set_setting, unique_slug)

bp = Blueprint("admin", __name__, url_prefix="/admin")

OPEN_ENDPOINTS = {"admin.login", "admin.setup"}
DUMMY_HASH = generate_password_hash("not-a-real-password")  # keeps login timing similar for unknown users

RESOURCES = {
    "skills": (Skill, "admin.skills"),
    "projects": (Project, "admin.projects"),
    "certificates": (Certificate, "admin.certificates"),
    "experiences": (Experience, "admin.experiences"),
}
KINDS = ["Internship", "Workshop", "Course", "Experience", "Achievement", "Other"]


@bp.before_request
def require_login():
    if request.endpoint in OPEN_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("admin.login", next=request.path))
    return None


# ---------------------------------------------------------------- small helpers
def fstr(name, maxlen=None):
    value = (request.form.get(name) or "").strip()
    return value[:maxlen] if maxlen else value


def fbool(name):
    return request.form.get(name) in ("on", "1", "true", "yes")


def fdate(name, errors, label):
    raw = fstr(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        errors.append(f"{label} is not a valid date.")
        return None


def furl(name, errors, label):
    value = fstr(name, 300)
    if value and not is_valid_url(value):
        errors.append(f"{label} must start with http:// or https://")
    return value


def show_errors(errors):
    for e in errors:
        flash(e, "error")


def safe_next(target):
    if target and target.startswith("/admin") and not target.startswith("//"):
        return target
    return url_for("admin.dashboard")


# ---------------------------------------------------------------- auth
@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if Admin.query.count() == 0:
        return redirect(url_for("admin.setup"))
    if request.method == "POST":
        username = fstr("username", 40)
        password = request.form.get("password") or ""
        user = Admin.query.filter_by(username=username).first()
        valid = check_password_hash(user.password_hash if user else DUMMY_HASH, password)
        if user and valid:
            session.clear()
            login_user(user)
            session.permanent = True
            user.last_login = utcnow()
            db.session.commit()
            return redirect(safe_next(request.args.get("next")))
        flash("Invalid username or password.", "error")
    return render_template("admin/login.html")


@bp.route("/setup", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def setup():
    """One-time creation of the first admin. Disabled forever once an admin exists."""
    if Admin.query.count() > 0:
        abort(404)
    setup_key = current_app.config["ADMIN_SETUP_KEY"]
    if request.method == "POST" and setup_key:
        username, password, confirm = fstr("username", 40), request.form.get("password") or "", request.form.get("confirm") or ""
        errors = []
        if not hmac.compare_digest((request.form.get("setup_key") or "").encode(), setup_key.encode()):
            errors.append("The setup key is incorrect.")
        if len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if len(password) < 10:
            errors.append("Password must be at least 10 characters.")
        if password != confirm:
            errors.append("The two passwords do not match.")
        if errors:
            show_errors(errors)
        else:
            db.session.add(Admin(username=username, password_hash=generate_password_hash(password)))
            db.session.commit()
            flash("Admin account created. Please log in.", "success")
            return redirect(url_for("admin.login"))
    return render_template("admin/setup.html", enabled=bool(setup_key))


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------- dashboard
@bp.route("/")
@bp.route("/dashboard")
def dashboard():
    stats = {
        "projects": Project.query.count(),
        "published": Project.query.filter_by(published=True).count(),
        "certificates": Certificate.query.count(),
        "skills": Skill.query.count(),
        "experiences": Experience.query.count(),
        "messages": ContactMessage.query.count(),
        "unread": ContactMessage.query.filter_by(is_read=False).count(),
    }
    activity = []
    for model, label, attr in ((Project, "Project", "title"), (Certificate, "Certificate", "title"),
                               (Skill, "Skill", "name"), (Experience, "Experience", "role")):
        for obj in model.query.order_by(model.updated_at.desc()).limit(5).all():
            activity.append((obj.updated_at, label, getattr(obj, attr)))
    activity.sort(key=lambda a: a[0], reverse=True)
    latest_messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(5).all()
    return render_template("admin/dashboard.html", stats=stats, activity=activity[:8], latest_messages=latest_messages)


# ---------------------------------------------------------------- profile
@bp.route("/profile", methods=["GET", "POST"])
def profile():
    p = Profile.query.first()
    if request.method == "POST":
        errors = []
        full_name = fstr("full_name", 100)
        email = fstr("email", 150)
        if not full_name:
            errors.append("Full name is required.")
        if email and not is_valid_email(email):
            errors.append("Email address is not valid.")
        linkedin = furl("linkedin_url", errors, "LinkedIn URL")
        github = furl("github_url", errors, "GitHub URL")
        new_photo = None
        if not errors:
            try:
                new_photo = save_upload(request.files.get("photo"), "profile", IMAGE_KINDS)
            except UploadError as exc:
                errors.append(str(exc))
        if errors:
            show_errors(errors)
        else:
            p.full_name, p.title = full_name, fstr("title", 150)
            p.about, p.location = fstr("about", 5000), fstr("location", 150)
            p.email, p.phone = email, fstr("phone", 40)
            p.linkedin_url, p.github_url = linkedin, github
            p.tagline = fstr("tagline", 200)
            p.education, p.institution = fstr("education", 200), fstr("institution", 200)
            p.education_status = fstr("education_status", 100)
            if new_photo:
                delete_upload(p.photo)
                p.photo = new_photo
            elif fbool("remove_photo"):
                delete_upload(p.photo)
                p.photo = ""
            db.session.commit()
            flash("Profile saved.", "success")
            return redirect(url_for("admin.profile"))
    return render_template("admin/profile.html", p=p)


# ---------------------------------------------------------------- generic move / toggle
@bp.post("/<resource>/<int:item_id>/move/<direction>")
def move(resource, item_id, direction):
    if resource not in RESOURCES or direction not in ("up", "down"):
        abort(404)
    model, endpoint = RESOURCES[resource]
    item = db.get_or_404(model, item_id)
    scope = (Skill.category == item.category) if resource == "skills" else None
    reorder(model, item, direction, scope)
    return redirect(url_for(endpoint))


@bp.post("/<resource>/<int:item_id>/toggle")
def toggle(resource, item_id):
    if resource not in RESOURCES:
        abort(404)
    model, endpoint = RESOURCES[resource]
    item = db.get_or_404(model, item_id)
    if resource == "skills":
        item.enabled = not item.enabled
        state = "enabled" if item.enabled else "disabled"
    else:
        item.published = not item.published
        state = "published" if item.published else "hidden"
    db.session.commit()
    flash(f"Item {state}.", "success")
    return redirect(url_for(endpoint))


@bp.post("/projects/<int:pid>/feature")
def project_feature(pid):
    project = db.get_or_404(Project, pid)
    project.featured = not project.featured
    db.session.commit()
    flash("Marked as featured." if project.featured else "Removed from featured.", "success")
    return redirect(url_for("admin.projects"))


# ---------------------------------------------------------------- skills
@bp.route("/skills")
def skills():
    items = Skill.query.order_by(Skill.position, Skill.id).all()
    groups = {}
    for s in items:
        groups.setdefault(s.category, []).append(s)
    ordered = [c for c in SKILL_CATEGORIES if c in groups] + sorted(c for c in groups if c not in SKILL_CATEGORIES)
    return render_template("admin/skills.html", groups=[(c, groups[c]) for c in ordered])


def _skill_form(item):
    f = {}
    if item:
        f = {"name": item.name, "category": item.category, "icon": item.icon,
             "proficiency": item.proficiency, "enabled": item.enabled}
    else:
        f = {"enabled": True, "proficiency": 0, "category": SKILL_CATEGORIES[0]}
    if request.method == "POST":
        errors = []
        name, category, icon = fstr("name", 80), fstr("category", 80), fstr("icon", 100)
        raw = fstr("proficiency") or "0"
        try:
            level = int(raw)
            if not 0 <= level <= 100:
                raise ValueError
        except ValueError:
            level = 0
            errors.append("Proficiency must be a whole number from 0 to 100.")
        if not name:
            errors.append("Skill name is required.")
        if not category:
            errors.append("Category is required.")
        if icon and not all(c.isalnum() or c in "- " for c in icon):
            errors.append("Icon classes may only contain letters, numbers, spaces and hyphens.")
        if errors:
            show_errors(errors)
            f = request.form.to_dict()
        else:
            if item is None:
                item = Skill(position=next_position(Skill, category=category))
                db.session.add(item)
            elif item.category != category:
                item.position = next_position(Skill, category=category)
            item.name, item.category, item.icon = name, category, icon
            item.proficiency, item.enabled = level, fbool("enabled")
            db.session.commit()
            flash("Skill saved.", "success")
            return redirect(url_for("admin.skills"))
    categories = list(SKILL_CATEGORIES) + sorted({s.category for s in Skill.query.all()} - set(SKILL_CATEGORIES))
    return render_template("admin/skill_form.html", item=item, f=f, categories=categories)


@bp.route("/skills/new", methods=["GET", "POST"])
def skill_new():
    return _skill_form(None)


@bp.route("/skills/<int:sid>/edit", methods=["GET", "POST"])
def skill_edit(sid):
    return _skill_form(db.get_or_404(Skill, sid))


@bp.post("/skills/<int:sid>/delete")
def skill_delete(sid):
    skill = db.get_or_404(Skill, sid)
    skill.projects.clear()  # detach from any projects first
    db.session.delete(skill)
    db.session.commit()
    flash("Skill deleted.", "success")
    return redirect(url_for("admin.skills"))


# ---------------------------------------------------------------- projects
@bp.route("/projects")
def projects():
    items = Project.query.order_by(Project.position, Project.id).all()
    return render_template("admin/projects.html", items=items)


def _unique_skills():
    seen, result = set(), []
    for s in Skill.query.order_by(Skill.position, Skill.id).all():
        if s.name not in seen:
            seen.add(s.name)
            result.append(s)
    return result


def _project_form(item):
    all_skills = _unique_skills()
    if item:
        f = {k: getattr(item, k) for k in ("title", "short_description", "category", "overview", "problem",
                                           "solution", "features", "methodology", "github_url", "live_url",
                                           "published", "featured")}
        f["completed_on"] = item.completed_on.isoformat() if item.completed_on else ""
        selected = set(item.tech_names)
    else:
        f, selected = {"published": True}, set()

    if request.method == "POST":
        errors = []
        title = fstr("title", 200)
        if not title:
            errors.append("Project title is required.")
        github = furl("github_url", errors, "GitHub URL")
        live = furl("live_url", errors, "Live demo URL")
        completed = fdate("completed_on", errors, "Completion date")
        picked = set(request.form.getlist("technologies"))
        saved_files, thumb, shots = [], None, []
        if not errors:
            try:
                thumb = save_upload(request.files.get("thumbnail"), "projects", IMAGE_KINDS)
                if thumb:
                    saved_files.append(thumb)
                for fs in request.files.getlist("screenshots"):
                    path = save_upload(fs, "projects", IMAGE_KINDS)
                    if path:
                        saved_files.append(path)
                        shots.append(path)
            except UploadError as exc:
                errors.append(str(exc))
        if errors:
            for path in saved_files:
                delete_upload(path)
            show_errors(errors)
            f = request.form.to_dict()
            selected = picked
        else:
            if item is None:
                item = Project(slug=unique_slug(Project, title), position=next_position(Project, top=True))
                db.session.add(item)
            item.title = title
            item.short_description = fstr("short_description", 300)
            item.category = fstr("category", 80)
            item.overview, item.problem = fstr("overview", 8000), fstr("problem", 8000)
            item.solution, item.features = fstr("solution", 8000), fstr("features", 8000)
            item.methodology = fstr("methodology", 8000)
            item.github_url, item.live_url, item.completed_on = github, live, completed
            item.published, item.featured = fbool("published"), fbool("featured")
            if thumb:
                delete_upload(item.thumbnail)
                item.thumbnail = thumb
            elif fbool("remove_thumbnail"):
                delete_upload(item.thumbnail)
                item.thumbnail = ""
            current = item.screenshot_list
            for rel in request.form.getlist("delete_screenshots"):
                if rel in current:
                    current.remove(rel)
                    delete_upload(rel)
            item.screenshot_list = current + shots
            chosen, seen = [], set()
            for s in Skill.query.filter(Skill.name.in_(picked)).order_by(Skill.id).all() if picked else []:
                if s.name not in seen:
                    seen.add(s.name)
                    chosen.append(s)
            item.technologies = chosen
            db.session.commit()
            flash("Project saved.", "success")
            return redirect(url_for("admin.projects"))
    return render_template("admin/project_form.html", item=item, f=f, skills=all_skills, selected=selected)


@bp.route("/projects/new", methods=["GET", "POST"])
def project_new():
    return _project_form(None)


@bp.route("/projects/<int:pid>/edit", methods=["GET", "POST"])
def project_edit(pid):
    return _project_form(db.get_or_404(Project, pid))


@bp.post("/projects/<int:pid>/delete")
def project_delete(pid):
    project = db.get_or_404(Project, pid)
    delete_upload(project.thumbnail)
    for rel in project.screenshot_list:
        delete_upload(rel)
    project.technologies = []
    db.session.delete(project)
    db.session.commit()
    flash("Project deleted.", "success")
    return redirect(url_for("admin.projects"))


# ---------------------------------------------------------------- certificates
@bp.route("/certificates")
def certificates():
    items = Certificate.query.order_by(Certificate.position, Certificate.id).all()
    return render_template("admin/certificates.html", items=items)


def _certificate_form(item):
    if item:
        f = {"title": item.title, "organization": item.organization, "description": item.description,
             "credential_url": item.credential_url, "published": item.published,
             "issue_date": item.issue_date.isoformat() if item.issue_date else ""}
    else:
        f = {"published": True}
    if request.method == "POST":
        errors = []
        title = fstr("title", 200)
        if not title:
            errors.append("Certificate title is required.")
        cred = furl("credential_url", errors, "Credential URL")
        issued = fdate("issue_date", errors, "Issue date")
        upload = request.files.get("file")
        has_new = bool(upload and upload.filename)
        if item is None and not has_new:
            errors.append("Please choose a certificate file (JPG, PNG or PDF).")
        new_path = None
        if not errors and has_new:
            try:
                new_path = save_upload(upload, "certificates", DOC_KINDS)
            except UploadError as exc:
                errors.append(str(exc))
        if errors:
            show_errors(errors)
            f = request.form.to_dict()
        else:
            if item is None:
                item = Certificate(position=next_position(Certificate))
                db.session.add(item)
            item.title, item.organization = title, fstr("organization", 200)
            item.description, item.credential_url, item.issue_date = fstr("description", 3000), cred, issued
            item.published = fbool("published")
            if new_path:
                delete_upload(item.file_path)
                item.file_path = new_path
                item.file_type = file_kind_from_path(new_path)
            db.session.commit()
            flash("Certificate saved.", "success")
            return redirect(url_for("admin.certificates"))
    return render_template("admin/certificate_form.html", item=item, f=f)


@bp.route("/certificates/new", methods=["GET", "POST"])
def certificate_new():
    return _certificate_form(None)


@bp.route("/certificates/<int:cid>/edit", methods=["GET", "POST"])
def certificate_edit(cid):
    return _certificate_form(db.get_or_404(Certificate, cid))


@bp.post("/certificates/<int:cid>/delete")
def certificate_delete(cid):
    cert = db.get_or_404(Certificate, cid)
    delete_upload(cert.file_path)
    db.session.delete(cert)
    db.session.commit()
    flash("Certificate deleted.", "success")
    return redirect(url_for("admin.certificates"))


# ---------------------------------------------------------------- experiences
@bp.route("/experiences")
def experiences():
    items = Experience.query.order_by(Experience.position, Experience.id).all()
    return render_template("admin/experiences.html", items=items)


def _experience_form(item):
    if item:
        f = {"role": item.role, "organization": item.organization, "kind": item.kind,
             "period": item.period, "description": item.description, "published": item.published}
    else:
        f = {"published": True, "kind": "Internship"}
    if request.method == "POST":
        role = fstr("role", 150)
        if not role:
            show_errors(["Role / title is required."])
            f = request.form.to_dict()
        else:
            if item is None:
                item = Experience(position=next_position(Experience, top=True))
                db.session.add(item)
            item.role, item.organization = role, fstr("organization", 200)
            item.kind, item.period = fstr("kind", 40) or "Experience", fstr("period", 100)
            item.description, item.published = fstr("description", 3000), fbool("published")
            db.session.commit()
            flash("Experience saved.", "success")
            return redirect(url_for("admin.experiences"))
    return render_template("admin/experience_form.html", item=item, f=f, kinds=KINDS)


@bp.route("/experiences/new", methods=["GET", "POST"])
def experience_new():
    return _experience_form(None)


@bp.route("/experiences/<int:eid>/edit", methods=["GET", "POST"])
def experience_edit(eid):
    return _experience_form(db.get_or_404(Experience, eid))


@bp.post("/experiences/<int:eid>/delete")
def experience_delete(eid):
    db.session.delete(db.get_or_404(Experience, eid))
    db.session.commit()
    flash("Experience deleted.", "success")
    return redirect(url_for("admin.experiences"))


# ---------------------------------------------------------------- resume
@bp.route("/resume", methods=["GET", "POST"])
def resume():
    from utils import resume_info
    if request.method == "POST":
        action = request.form.get("action")
        settings = get_settings()
        if action == "title":
            title = fstr("resume_title", 150)
            if not title:
                show_errors(["Resume title cannot be empty."])
            else:
                set_setting("resume_title", title)
                db.session.commit()
                flash("Resume title updated.", "success")
        elif action == "url":
            errors = []
            url = furl("resume_url", errors, "Resume URL")
            if not url and not errors:
                errors.append("Please enter a resume URL.")
            if errors:
                show_errors(errors)
            else:
                set_setting("resume_url", url)
                set_setting("resume_source", "url")
                db.session.commit()
                flash("Resume URL saved. The website now uses this link.", "success")
        elif action == "upload":
            try:
                path = save_upload(request.files.get("resume_file"), "resumes", PDF_ONLY)
            except UploadError as exc:
                path = None
                show_errors([str(exc)])
            else:
                if path is None:
                    show_errors(["Please choose a PDF file to upload."])
                else:
                    delete_upload(settings.get("resume_file"))
                    set_setting("resume_file", path)
                    set_setting("resume_source", "file")
                    db.session.commit()
                    flash("New resume uploaded. The website now uses it.", "success")
        elif action == "remove_file":
            delete_upload(settings.get("resume_file"))
            set_setting("resume_file", "")
            set_setting("resume_source", "url")
            db.session.commit()
            flash("Uploaded resume removed. The website uses the resume URL again.", "success")
        return redirect(url_for("admin.resume"))
    return render_template("admin/resume.html", info=resume_info(get_settings()))


# ---------------------------------------------------------------- media library
def _used_files():
    used = set()
    p = Profile.query.first()
    if p and p.photo:
        used.add(p.photo)
    for proj in Project.query.all():
        if proj.thumbnail:
            used.add(proj.thumbnail)
        used.update(proj.screenshot_list)
    for cert in Certificate.query.all():
        if cert.file_path:
            used.add(cert.file_path)
    resume_file = get_settings().get("resume_file")
    if resume_file:
        used.add(resume_file)
    return used


@bp.route("/media")
def media():
    used = _used_files()
    files = []
    for sub in UPLOAD_SUBDIRS:
        folder = UPLOAD_DIR / sub
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if path.is_file():
                    rel = f"{sub}/{path.name}"
                    files.append({"rel": rel, "folder": sub, "size_kb": max(1, path.stat().st_size // 1024),
                                  "used": rel in used, "pdf": path.suffix == ".pdf"})
    return render_template("admin/media.html", files=files)


@bp.post("/media/upload")
def media_upload():
    """Upload extra images into the library (for reuse; attach them from the other admin pages)."""
    folder = request.form.get("folder")
    if folder not in ("profile", "projects"):
        abort(400)
    count = 0
    try:
        for fs in request.files.getlist("files"):
            if save_upload(fs, folder, IMAGE_KINDS):
                count += 1
    except UploadError as exc:
        flash(str(exc), "error")
    if count:
        flash(f"{count} image(s) uploaded.", "success")
    return redirect(url_for("admin.media"))


@bp.post("/media/delete")
def media_delete():
    rel = request.form.get("path", "")
    path = safe_upload_path(rel)
    if path is None or not path.is_file() or rel.split("/")[0] not in UPLOAD_SUBDIRS:
        abort(404)
    if rel in _used_files():
        flash("That file is in use. Remove it from its project, certificate or profile first.", "error")
    else:
        delete_upload(rel)
        flash("File deleted.", "success")
    return redirect(url_for("admin.media"))


# ---------------------------------------------------------------- contact messages
@bp.route("/messages")
def messages():
    items = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template("admin/messages.html", items=items)


@bp.post("/messages/<int:mid>/toggle")
def message_toggle(mid):
    msg = db.get_or_404(ContactMessage, mid)
    msg.is_read = not msg.is_read
    db.session.commit()
    return redirect(url_for("admin.messages"))


@bp.post("/messages/<int:mid>/delete")
def message_delete(mid):
    db.session.delete(db.get_or_404(ContactMessage, mid))
    db.session.commit()
    flash("Message deleted.", "success")
    return redirect(url_for("admin.messages"))


# ---------------------------------------------------------------- website settings
SETTING_FIELDS = ("site_title", "meta_description", "hero_subtitle", "hero_tagline", "personal_tagline",
                  "faith_tagline", "typing_words", "footer_text")


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    p = Profile.query.first()
    if request.method == "POST":
        errors = []
        linkedin = furl("linkedin_url", errors, "LinkedIn URL")
        github = furl("github_url", errors, "GitHub URL")
        if not fstr("site_title"):
            errors.append("Website title is required.")
        if errors:
            show_errors(errors)
        else:
            for key in SETTING_FIELDS:
                set_setting(key, fstr(key, 1000))
            p.linkedin_url, p.github_url = linkedin, github
            db.session.commit()
            flash("Website settings saved.", "success")
            return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", S=get_settings(), p=p)


@bp.post("/password")
def password():
    errors = []
    if not check_password_hash(current_user.password_hash, request.form.get("current_password") or ""):
        errors.append("Your current password is incorrect.")
    new, confirm = request.form.get("new_password") or "", request.form.get("confirm_password") or ""
    if len(new) < 10:
        errors.append("The new password must be at least 10 characters.")
    if new != confirm:
        errors.append("The new passwords do not match.")
    if errors:
        show_errors(errors)
    else:
        current_user.password_hash = generate_password_hash(new)
        db.session.commit()
        flash("Password changed.", "success")
    return redirect(url_for("admin.settings"))


@bp.route("/backup")
def backup():
    """Download a ZIP containing a consistent copy of the database and every uploaded file."""
    buf = io.BytesIO()
    db_path = db.engine.url.database
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if db_path and os.path.exists(db_path):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
            tmp.close()
            src, dst = sqlite3.connect(db_path), sqlite3.connect(tmp.name)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            zf.write(tmp.name, "portfolio.db")
            os.unlink(tmp.name)
        for path in UPLOAD_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, f"uploads/{path.relative_to(UPLOAD_DIR).as_posix()}")
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"portfolio-backup-{date.today().isoformat()}.zip")
