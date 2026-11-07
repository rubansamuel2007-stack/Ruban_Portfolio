"""Ruban.S portfolio - application factory."""
import re
from datetime import datetime, timezone

import click
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from config import Config, UPLOAD_DIR, UPLOAD_SUBDIRS
from extensions import csrf, db, limiter, login_manager
from models import Admin, Profile, seed_defaults
from utils import get_settings, resume_info, upload_url


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    # Render (and most hosts) sit behind a proxy: trust it for the real client IP / https.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(Admin, int(user_id))

    from routes.admin import bp as admin_bp
    from routes.public import bp as public_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        for sub in UPLOAD_SUBDIRS:
            (UPLOAD_DIR / sub).mkdir(parents=True, exist_ok=True)
        db.create_all()
        seed_defaults()

    # ---------------------------------------------------------- template helpers
    @app.context_processor
    def inject_globals():
        settings = get_settings()
        return {
            "profile": Profile.query.first(),
            "S": settings,
            "resume": resume_info(settings),
            "upload_url": upload_url,
            "now_year": lambda: datetime.now(timezone.utc).year,
        }

    @app.template_filter("paragraphs")
    def paragraphs(text):
        return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]

    @app.template_filter("lines")
    def lines(text):
        return [p.strip() for p in (text or "").splitlines() if p.strip()]

    @app.template_filter("localtime")
    def localtime(dt, fmt="%d %b %Y, %I:%M %p"):
        from datetime import timedelta
        if not dt:
            return ""
        return (dt + timedelta(minutes=app.config["TIMEZONE_OFFSET_MIN"])).strftime(fmt)

    # ---------------------------------------------------------- security headers
    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.path.startswith("/admin"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------------------------------------------------- error handlers
    def wants_json():
        return request.path.startswith("/api/")

    def error_response(code, title, message):
        if wants_json():
            return jsonify({"ok": False, "error": message}), code
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(404)
    def not_found(_):
        return error_response(404, "Page not found", "The page you are looking for does not exist.")

    @app.errorhandler(413)
    def too_large(_):
        return error_response(413, "File too large", "The upload is too large. Please use smaller files.")

    @app.errorhandler(429)
    def too_many(_):
        return error_response(429, "Too many requests", "You are doing that too often. Please wait a while and try again.")

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        return error_response(400, "Session expired", "Your form session expired. Please reload the page and try again.")

    @app.errorhandler(500)
    def server_error(_):
        db.session.rollback()
        return error_response(500, "Something went wrong", "An unexpected error occurred. Please try again later.")

    # ---------------------------------------------------------- CLI
    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.password_option()
    def create_admin(username, password):
        """Create (or reset the password of) an admin user from the command line."""
        if len(password) < 10:
            raise click.ClickException("Password must be at least 10 characters.")
        admin = Admin.query.filter_by(username=username).first()
        if admin is None:
            admin = Admin(username=username, password_hash=generate_password_hash(password))
            db.session.add(admin)
        else:
            admin.password_hash = generate_password_hash(password)
        db.session.commit()
        click.echo(f"Admin '{username}' saved.")

    return app


app = create_app()

if __name__ == "__main__":
    import os
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
