"""Database tables: admins, profile, skills, projects, certificates, experiences,
contact_messages, website_settings (+ a small project<->skill link table)."""
import json
from datetime import datetime, timezone

from flask_login import UserMixin

from extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Admin(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    last_login = db.Column(db.DateTime)


class Profile(TimestampMixin, db.Model):
    __tablename__ = "profile"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False, default="Ruban.S")
    title = db.Column(db.String(150), default="")
    about = db.Column(db.Text, default="")
    location = db.Column(db.String(150), default="")
    email = db.Column(db.String(150), default="")
    phone = db.Column(db.String(40), default="")
    linkedin_url = db.Column(db.String(300), default="")
    github_url = db.Column(db.String(300), default="")
    tagline = db.Column(db.String(200), default="")
    education = db.Column(db.String(200), default="")
    institution = db.Column(db.String(200), default="")
    education_status = db.Column(db.String(100), default="")
    photo = db.Column(db.String(300), default="")  # relative path inside uploads/


class WebsiteSetting(TimestampMixin, db.Model):
    __tablename__ = "website_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(80), unique=True, nullable=False)
    value = db.Column(db.Text, default="")


class Skill(TimestampMixin, db.Model):
    __tablename__ = "skills"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(100), default="")  # CSS class(es), e.g. "devicon-python-plain colored"
    proficiency = db.Column(db.Integer, default=0, nullable=False)  # 0-100, set by the admin
    position = db.Column(db.Integer, default=0, nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)


project_skills = db.Table(
    "project_skills",
    db.Column("project_id", db.Integer, db.ForeignKey("projects.id"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id"), primary_key=True),
)


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    short_description = db.Column(db.String(300), default="")
    category = db.Column(db.String(80), default="")
    overview = db.Column(db.Text, default="")
    problem = db.Column(db.Text, default="")
    solution = db.Column(db.Text, default="")
    features = db.Column(db.Text, default="")  # one feature per line
    methodology = db.Column(db.Text, default="")
    github_url = db.Column(db.String(300), default="")
    live_url = db.Column(db.String(300), default="")
    completed_on = db.Column(db.Date)
    thumbnail = db.Column(db.String(300), default="")
    screenshots = db.Column(db.Text, default="[]")  # JSON list of relative paths
    published = db.Column(db.Boolean, default=True, nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    technologies = db.relationship("Skill", secondary=project_skills, backref=db.backref("projects", lazy=True))

    @property
    def screenshot_list(self):
        try:
            return list(json.loads(self.screenshots or "[]"))
        except ValueError:
            return []

    @screenshot_list.setter
    def screenshot_list(self, value):
        self.screenshots = json.dumps(list(value))

    @property
    def feature_list(self):
        return [line.strip() for line in (self.features or "").splitlines() if line.strip()]

    @property
    def tech_names(self):
        seen, names = set(), []
        for skill in self.technologies:
            if skill.name not in seen:
                seen.add(skill.name)
                names.append(skill.name)
        return names


class Certificate(TimestampMixin, db.Model):
    __tablename__ = "certificates"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    organization = db.Column(db.String(200), default="")
    issue_date = db.Column(db.Date)
    description = db.Column(db.Text, default="")
    credential_url = db.Column(db.String(300), default="")
    file_path = db.Column(db.String(300), default="")
    file_type = db.Column(db.String(10), default="image")  # "image" or "pdf"
    published = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)


class Experience(TimestampMixin, db.Model):
    __tablename__ = "experiences"
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(150), nullable=False)
    organization = db.Column(db.String(200), default="")
    kind = db.Column(db.String(40), default="Internship")
    period = db.Column(db.String(100), default="")
    description = db.Column(db.Text, default="")
    published = db.Column(db.Boolean, default=True, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(64), default="")
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    email_sent = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------- defaults / seed data
DEFAULT_SETTINGS = {
    "site_title": "Ruban.S | Aspiring Web and AI Developer",
    "meta_description": "Portfolio of Ruban.S, an aspiring Web and AI/ML developer from Tirunelveli, Tamil Nadu - Python, Flask, web technologies and Generative AI.",
    "hero_subtitle": "Aspiring Web and AI Developer",
    "hero_tagline": "Turning Ideas Into Reality.",
    "personal_tagline": "Compete with Yourself.",
    "faith_tagline": "Assures us of God's plans for our future and hope.",
    "typing_words": "Web Developer\nPython Developer\nAspiring AI/ML Developer\nTechnology Enthusiast",
    "footer_text": "Ruban.S | Aspiring Web and AI Developer",
    "resume_title": "Ruban.S - Resume",
    "resume_url": "https://drive.google.com/file/d/1gW0_uuFmw-4czgqd09jWexWVoeU2WOei/view?usp=drivesdk",
    "resume_file": "",
    "resume_source": "url",  # "url" or "file": whichever was saved most recently wins
}

DEFAULT_ABOUT = (
    "I'm Ruban.S, an aspiring AI/ML Developer and Web Developer passionate about building meaningful "
    "digital experiences and intelligent solutions.\n\n"
    "I enjoy transforming ideas into practical applications, exploring emerging technologies and developing "
    "solutions that address real-world problems.\n\n"
    "With an interest in Python development, modern web technologies, Machine Learning and Generative AI, "
    "I'm continuously expanding my technical knowledge through hands-on projects, internships and practical learning.\n\n"
    "My goal is to combine creativity, technology and problem-solving to build impactful digital solutions.\n\n"
    "I believe in continuous improvement, innovation and one simple principle: Compete with Yourself."
)

SKILL_CATEGORIES = [
    "Programming Languages",
    "Frontend Development",
    "Backend Development",
    "Database Management",
    "Artificial Intelligence & Machine Learning",
    "Development Tools",
]

# (name, category, icon classes). Proficiency starts at 0 on purpose: set real values in the admin dashboard.
DEFAULT_SKILLS = [
    ("Python", "Programming Languages", "devicon-python-plain colored"),
    ("Java", "Programming Languages", "devicon-java-plain colored"),
    ("JavaScript", "Programming Languages", "devicon-javascript-plain colored"),
    ("HTML", "Frontend Development", "devicon-html5-plain colored"),
    ("CSS", "Frontend Development", "devicon-css3-plain colored"),
    ("JavaScript", "Frontend Development", "devicon-javascript-plain colored"),
    ("React", "Frontend Development", "devicon-react-original colored"),
    ("Python", "Backend Development", "devicon-python-plain colored"),
    ("Flask", "Backend Development", "devicon-flask-original"),
    ("FastAPI", "Backend Development", "devicon-fastapi-plain colored"),
    ("Java", "Backend Development", "devicon-java-plain colored"),
    ("MySQL", "Database Management", "devicon-mysql-original colored"),
    ("MongoDB", "Database Management", "devicon-mongodb-plain colored"),
    ("Oracle APEX", "Database Management", "devicon-oracle-original colored"),
    ("Machine Learning", "Artificial Intelligence & Machine Learning", "bi bi-cpu"),
    ("Natural Language Processing (NLP)", "Artificial Intelligence & Machine Learning", "bi bi-chat-square-text"),
    ("Generative AI", "Artificial Intelligence & Machine Learning", "bi bi-stars"),
    ("Git", "Development Tools", "devicon-git-plain colored"),
    ("GitHub", "Development Tools", "devicon-github-original"),
    ("Visual Studio Code", "Development Tools", "devicon-vscode-plain colored"),
    ("Postman", "Development Tools", "devicon-postman-plain colored"),
]


def seed_defaults():
    """Create the profile, settings and starter skills the first time the app runs."""
    if Profile.query.first() is None:
        db.session.add(Profile(
            full_name="Ruban.S",
            title="Web Developer | Aspiring AI/ML Developer",
            about=DEFAULT_ABOUT,
            location="Tirunelveli, Tamil Nadu, India.",
            email="rubansamuel2007@gmail.com",
            phone="9092241520",
            linkedin_url="https://www.linkedin.com/in/ruban-s-8073b8371",
            github_url="https://github.com/rubansamuel2007-stack",
            tagline="Compete with Yourself.",
            education="Bachelor of Computer Applications (BCA)",
            institution="St. John's College, Palayamkottai.",
            education_status="Currently pursuing",
        ))
    existing = {s.key for s in WebsiteSetting.query.all()}
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            db.session.add(WebsiteSetting(key=key, value=value))
    if Skill.query.count() == 0:
        for i, (name, category, icon) in enumerate(DEFAULT_SKILLS):
            db.session.add(Skill(name=name, category=category, icon=icon, proficiency=0, position=i))
    db.session.commit()
