"""End-to-end tests. Run from the project folder with:  python -m unittest discover -s tests -v

They use a temporary database and upload folder, so your real data is never touched.
CSRF protection stays ON, exactly as in production.
"""
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="portfolio_test_")
os.environ["DATA_DIR"] = _tmp
os.environ["ADMIN_SETUP_KEY"] = "test-setup-key"
os.environ["RATELIMIT_ENABLED"] = "false"
os.environ["RESEND_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from models import Certificate, ContactMessage, Experience, Project, Skill, Profile  # noqa: E402
from utils import get_settings  # noqa: E402

PASSWORD = "CorrectHorse-9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


def token(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = False  # keep real error handlers
        cls.client = app.test_client()

    def post(self, url, data=None, page=None, **kw):
        """POST with a valid CSRF token taken from `page` (any page containing a form)."""
        page = page or "/admin/login"
        html = self.client.get(page).get_data(as_text=True)
        data = dict(data or {})
        data["csrf_token"] = token(html)
        return self.client.post(url, data=data, **kw)

    # ---- order matters: tests are numbered
    def test_01_public_pages_and_defaults(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        for text in ("Ruban.S", "Turning Ideas Into Reality", "Compete with Yourself", "Machine Learning",
                     "rubansamuel2007@gmail.com", "Tirunelveli"):
            self.assertIn(text, html)
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)
        self.assertEqual(self.client.get("/nope").status_code, 404)

    def test_02_admin_requires_login(self):
        for path in ("/admin/dashboard", "/admin/projects", "/admin/skills", "/admin/backup", "/admin/messages"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/admin/login", r.headers["Location"])
        # anonymous POST is refused (CSRF or login) and never changes data
        r = self.client.post("/admin/projects/1/delete")
        self.assertIn(r.status_code, (302, 400))

    def test_03_setup_login_logout(self):
        r = self.client.get("/admin/login")
        self.assertEqual(r.status_code, 302)  # no admin yet -> setup
        bad = self.post("/admin/setup", {"setup_key": "wrong", "username": "ruban", "password": PASSWORD,
                                         "confirm": PASSWORD}, page="/admin/setup")
        self.assertIn(b"setup key is incorrect", bad.data)
        weak = self.post("/admin/setup", {"setup_key": "test-setup-key", "username": "ruban", "password": "short",
                                          "confirm": "short"}, page="/admin/setup")
        self.assertIn(b"at least 10", weak.data)
        ok = self.post("/admin/setup", {"setup_key": "test-setup-key", "username": "ruban", "password": PASSWORD,
                                        "confirm": PASSWORD}, page="/admin/setup")
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(self.client.get("/admin/setup").status_code, 404)  # one-time only

        wrong = self.post("/admin/login", {"username": "ruban", "password": "nope-nope-nope"})
        self.assertIn(b"Invalid username or password", wrong.data)
        good = self.post("/admin/login", {"username": "ruban", "password": PASSWORD})
        self.assertEqual(good.status_code, 302)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)
        out = self.post("/admin/logout", page="/admin/dashboard")
        self.assertEqual(out.status_code, 302)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 302)
        self.post("/admin/login", {"username": "ruban", "password": PASSWORD})  # log back in for the rest

    def test_04_all_admin_pages_render(self):
        for path in ("/admin/dashboard", "/admin/profile", "/admin/skills", "/admin/skills/new", "/admin/projects",
                     "/admin/projects/new", "/admin/certificates", "/admin/certificates/new", "/admin/resume",
                     "/admin/experiences", "/admin/experiences/new", "/admin/media", "/admin/messages",
                     "/admin/settings"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_05_skills_crud(self):
        page = "/admin/skills/new"
        self.post(page, {"name": "Django", "category": "Backend Development", "proficiency": "70",
                         "icon": "devicon-django-plain", "enabled": "on"}, page=page)
        with app.app_context():
            skill = Skill.query.filter_by(name="Django").one()
            sid = skill.id
            self.assertEqual(skill.proficiency, 70)
        self.assertIn("Django", self.client.get("/").get_data(as_text=True))
        # invalid proficiency rejected
        r = self.post(f"/admin/skills/{sid}/edit", {"name": "Django", "category": "Backend Development",
                                                    "proficiency": "150"}, page=page)
        self.assertIn(b"0 to 100", r.data)
        # edit + disable
        self.post(f"/admin/skills/{sid}/edit", {"name": "Django 5", "category": "Frameworks", "proficiency": "55"},
                  page="/admin/skills")
        with app.app_context():
            s = db.session.get(Skill, sid)
            self.assertEqual((s.name, s.category, s.proficiency, s.enabled), ("Django 5", "Frameworks", 55, False))
        self.assertNotIn("Django 5", self.client.get("/").get_data(as_text=True))
        # reorder + toggle
        self.assertEqual(self.post(f"/admin/skills/{sid}/move/up", page="/admin/skills").status_code, 302)
        self.post(f"/admin/skills/{sid}/toggle", page="/admin/skills")
        with app.app_context():
            self.assertTrue(db.session.get(Skill, sid).enabled)
        self.post(f"/admin/skills/{sid}/delete", page="/admin/skills")
        with app.app_context():
            self.assertIsNone(db.session.get(Skill, sid))

    def test_06_project_crud_with_uploads(self):
        page = "/admin/projects/new"
        with app.app_context():
            python_id = Skill.query.filter_by(name="Python").first().id  # noqa: F841
        data = {
            "title": "Smart Chatbot", "category": "AI/ML", "short_description": "A tiny NLP chatbot.",
            "overview": "Overview text", "problem": "Problem text", "solution": "Solution text",
            "features": "Fast\nAccurate", "methodology": "Agile", "github_url": "https://github.com/x/y",
            "live_url": "https://example.com", "completed_on": "2026-08-01", "published": "on", "featured": "on",
            "technologies": ["Python", "Flask"],
            "thumbnail": (io.BytesIO(PNG), "thumb.png"),
            "screenshots": [(io.BytesIO(JPG), "a.jpg"), (io.BytesIO(PNG), "b.png")],
        }
        r = self.post(page, data, page=page, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            p = Project.query.filter_by(title="Smart Chatbot").one()
            pid, slug = p.id, p.slug
            self.assertEqual(slug, "smart-chatbot")
            self.assertEqual(sorted(p.tech_names), ["Flask", "Python"])
            self.assertEqual(len(p.screenshot_list), 2)
            thumb = p.thumbnail
            self.assertTrue(thumb.startswith("projects/"))
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Smart Chatbot", html)
        detail = self.client.get(f"/project/{slug}")
        self.assertEqual(detail.status_code, 200)
        for text in ("Problem text", "Solution text", "Agile", "Fast", "AI/ML", "https://github.com/x/y"):
            self.assertIn(text, detail.get_data(as_text=True))
        self.assertEqual(self.client.get("/uploads/" + thumb).status_code, 200)

        # edit: change title, delete one screenshot
        with app.app_context():
            first = Project.query.get(pid).screenshot_list[0]
        edit = {"title": "Smart Chatbot v2", "category": "AI/ML", "published": "on", "delete_screenshots": first,
                "technologies": ["Python"]}
        self.post(f"/admin/projects/{pid}/edit", edit, page=f"/admin/projects/{pid}/edit")
        with app.app_context():
            p = db.session.get(Project, pid)
            self.assertEqual(p.title, "Smart Chatbot v2")
            self.assertEqual(p.slug, "smart-chatbot")  # links stay stable
            self.assertEqual(len(p.screenshot_list), 1)
            self.assertFalse(p.featured)
        self.assertEqual(self.client.get("/uploads/" + first).status_code, 404)

        # bad uploads are rejected and nothing is saved
        bad = {"title": "Evil", "thumbnail": (io.BytesIO(b"<?php echo 1; ?>"), "shell.png")}
        r = self.post(page, bad, page=page, content_type="multipart/form-data")
        self.assertIn(b"not an allowed file type", r.data)
        with app.app_context():
            self.assertIsNone(Project.query.filter_by(title="Evil").first())
        big = {"title": "Big", "thumbnail": (io.BytesIO(PNG + b"0" * (5 * 1024 * 1024)), "big.png")}
        r = self.post(page, big, page=page, content_type="multipart/form-data")
        self.assertIn(b"too large", r.data)

        # unpublish hides it from the public site; feature + reorder work
        self.post(f"/admin/projects/{pid}/toggle", page="/admin/projects")
        self.assertEqual(self.client.get(f"/project/{slug}").status_code, 404)
        self.post(f"/admin/projects/{pid}/feature", page="/admin/projects")
        self.assertEqual(self.post(f"/admin/projects/{pid}/move/down", page="/admin/projects").status_code, 302)

        # delete removes the row and its files
        self.post(f"/admin/projects/{pid}/delete", page="/admin/projects")
        with app.app_context():
            self.assertIsNone(db.session.get(Project, pid))
        self.assertEqual(self.client.get("/uploads/" + thumb).status_code, 404)

    def test_07_certificates(self):
        page = "/admin/certificates/new"
        no_file = self.post(page, {"title": "Python Course"}, page=page, content_type="multipart/form-data")
        self.assertIn(b"choose a certificate file", no_file.data)
        r = self.post(page, {"title": "Python Course", "organization": "Coursera", "issue_date": "2026-05-01",
                             "published": "on", "file": (io.BytesIO(PDF), "c.pdf")},
                      page=page, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        with app.app_context():
            c = Certificate.query.one()
            cid, path = c.id, c.file_path
            self.assertEqual(c.file_type, "pdf")
        self.assertIn("Python Course", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/uploads/" + path).status_code, 200)
        # replace the file with an image
        self.post(f"/admin/certificates/{cid}/edit", {"title": "Python Course", "file": (io.BytesIO(PNG), "c.png")},
                  page=f"/admin/certificates/{cid}/edit", content_type="multipart/form-data")
        with app.app_context():
            c = db.session.get(Certificate, cid)
            self.assertEqual(c.file_type, "image")
            self.assertFalse(c.published)  # checkbox left unticked -> hidden
        self.assertEqual(self.client.get("/uploads/" + path).status_code, 404)
        self.post(f"/admin/certificates/{cid}/delete", page="/admin/certificates")
        with app.app_context():
            self.assertEqual(Certificate.query.count(), 0)

    def test_08_experience_profile_settings(self):
        page = "/admin/experiences/new"
        self.post(page, {"role": "Python Intern", "organization": "Acme", "kind": "Internship",
                         "period": "Jun 2026", "published": "on"}, page=page)
        self.assertIn("Python Intern", self.client.get("/").get_data(as_text=True))
        with app.app_context():
            eid = Experience.query.one().id
        self.post(f"/admin/experiences/{eid}/delete", page="/admin/experiences")

        # profile photo upload + removal
        pdata = {"full_name": "Ruban.S", "email": "rubansamuel2007@gmail.com", "title": "Web Developer",
                 "photo": (io.BytesIO(JPG), "me.jpg")}
        self.post("/admin/profile", pdata, page="/admin/profile", content_type="multipart/form-data")
        with app.app_context():
            photo = Profile.query.first().photo
        self.assertTrue(photo)
        self.assertIn(photo, self.client.get("/").get_data(as_text=True))
        self.post("/admin/profile", {"full_name": "Ruban.S", "remove_photo": "on"}, page="/admin/profile")
        with app.app_context():
            self.assertEqual(Profile.query.first().photo, "")
        bad = self.post("/admin/profile", {"full_name": "R", "email": "not-an-email"}, page="/admin/profile")
        self.assertIn(b"not valid", bad.data)

        # settings
        self.post("/admin/settings", {"site_title": "New Title", "hero_tagline": "Hello world",
                                      "typing_words": "A\nB", "footer_text": "Foot"}, page="/admin/settings")
        with app.app_context():
            self.assertEqual(get_settings()["site_title"], "New Title")
        self.assertIn("New Title", self.client.get("/").get_data(as_text=True))

    def test_09_resume(self):
        page = "/admin/resume"
        up = self.post(page, {"action": "upload", "resume_file": (io.BytesIO(PDF), "r.pdf")}, page=page,
                       content_type="multipart/form-data")
        self.assertEqual(up.status_code, 302)
        r = self.client.get("/resume/download")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"%PDF"))
        notpdf = self.post(page, {"action": "upload", "resume_file": (io.BytesIO(PNG), "r.pdf")}, page=page,
                           content_type="multipart/form-data", follow_redirects=True)
        self.assertIn(b"not an allowed file type", notpdf.data)
        self.post(page, {"action": "title", "resume_title": "My CV"}, page=page)
        self.assertIn("My CV", self.client.get("/").get_data(as_text=True))
        # back to the external link
        self.post(page, {"action": "remove_file"}, page=page)
        r = self.client.get("/resume/download")
        self.assertEqual(r.status_code, 302)
        self.assertIn("drive.google.com", r.headers["Location"])

    def test_10_contact_form(self):
        html = self.client.get("/").get_data(as_text=True)
        tok = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
        hdr = {"X-CSRFToken": tok}
        good = {"name": "Visitor", "email": "v@example.com", "subject": "Hello there",
                "message": "I would like to work with you.", "elapsed_ms": 9000, "website": ""}
        no_token = self.client.post("/api/contact", json=good)
        self.assertEqual(no_token.status_code, 400)
        bad = self.client.post("/api/contact", json=dict(good, email="nope"), headers=hdr)
        self.assertEqual(bad.status_code, 400)
        self.assertIn("email", bad.get_json()["fields"])
        fast = self.client.post("/api/contact", json=dict(good, elapsed_ms=100), headers=hdr)
        self.assertEqual(fast.status_code, 400)
        bot = self.client.post("/api/contact", json=dict(good, website="http://spam"), headers=hdr)
        self.assertTrue(bot.get_json()["ok"])  # silently dropped
        with app.app_context():
            self.assertEqual(ContactMessage.query.count(), 0)
        ok = self.client.post("/api/contact", json=good, headers=hdr)
        self.assertTrue(ok.get_json()["ok"])
        dup = self.client.post("/api/contact", json=good, headers=hdr)
        self.assertEqual(dup.status_code, 409)
        with app.app_context():
            m = ContactMessage.query.one()
            mid = m.id
            self.assertFalse(m.is_read)
        self.assertIn(b"Hello there", self.client.get("/admin/messages").data)
        self.post(f"/admin/messages/{mid}/toggle", page="/admin/messages")
        with app.app_context():
            self.assertTrue(db.session.get(ContactMessage, mid).is_read)
        self.post(f"/admin/messages/{mid}/delete", page="/admin/messages")
        with app.app_context():
            self.assertEqual(ContactMessage.query.count(), 0)

    def test_11_backup_media_password(self):
        r = self.client.get("/admin/backup")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/zip")
        self.assertTrue(r.data.startswith(b"PK"))
        self.assertEqual(self.client.get("/admin/media").status_code, 200)
        r = self.post("/admin/password", {"current_password": "wrong", "new_password": "AnotherPass-123",
                                          "confirm_password": "AnotherPass-123"}, page="/admin/settings",
                      follow_redirects=True)
        self.assertIn(b"current password is incorrect", r.data)
        self.post("/admin/password", {"current_password": PASSWORD, "new_password": "AnotherPass-123",
                                      "confirm_password": "AnotherPass-123"}, page="/admin/settings")
        self.post("/admin/logout", page="/admin/dashboard")
        ok = self.post("/admin/login", {"username": "ruban", "password": "AnotherPass-123"})
        self.assertEqual(ok.status_code, 302)

    def test_12_path_traversal_blocked(self):
        for url in ("/uploads/../config.py", "/uploads/..%2Fconfig.py", "/uploads/%2e%2e/models.py"):
            self.assertEqual(self.client.get(url).status_code, 404, url)


if __name__ == "__main__":
    unittest.main()
