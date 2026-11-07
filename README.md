# Ruban.S | Aspiring Web and AI Developer - Portfolio with Admin Dashboard

A complete personal portfolio website with a private admin dashboard. You can add or change **projects, skills,
certificates, experience, your photo, your resume and all text** from the browser. Nothing is hard-coded, so you never
have to edit source code to update the site.

**Stack (kept deliberately simple):** Python Flask + Jinja2 templates, SQLite database (SQLAlchemy), Flask-Login for the
admin login, plain HTML/CSS/JavaScript for the front end, Resend for contact-form email.

> Note on the original brief: it mentioned several databases/frameworks (SQLite, MongoDB, FastAPI, React, Framer Motion).
> This project follows the "simple stack" section: **Flask + SQLite + vanilla JS**. Animations are done with CSS and
> the browser's IntersectionObserver (Framer Motion needs React, which the brief excludes) and respect the
> "reduce motion" setting.

---

## 1. Folder structure

```
Ruban_Portfolio/
|-- app.py                  Application factory, security headers, error pages, "create-admin" command
|-- config.py               All settings, read from environment variables / .env
|-- extensions.py           Database, login, CSRF and rate-limiter objects
|-- models.py               Database tables + default content (profile, settings, starter skills)
|-- utils.py                Safe file uploads, settings helpers, resume logic, Resend email
|-- requirements.txt        Python packages
|-- .env.example            Template for your private settings (copy to .env)
|-- render.yaml             One-click deployment settings for Render
|-- setup_and_run.bat       Windows helper: installs everything and starts the site
|-- routes/
|   |-- public.py           Public pages, contact API, GitHub API (cached), resume download, sitemap
|   `-- admin.py            Login, setup, and every admin CRUD page, backup download
|-- templates/
|   |-- base.html, index.html, project_detail.html, error.html
|   `-- admin/              base, login, setup, dashboard, profile, skills, skill_form, projects,
|                           project_form, certificates, certificate_form, experiences, experience_form,
|                           resume, media, messages, settings, _macros
|-- static/
|   |-- css/style.css       Public website styles
|   |-- css/admin.css       Admin dashboard styles
|   |-- js/main.js          Menu, typing effect, scroll animations, certificate viewer, contact form, GitHub
|   `-- img/                Favicon and placeholders (avatar, project)
|-- tests/test_app.py       Automated tests (login, CRUD, uploads, contact form, security)
`-- data/                   Created automatically: portfolio.db, uploads/, secret_key.txt  (never commit this)
```

**Responsibilities**

| Part | What it does |
|---|---|
| Front end (templates, CSS, JS) | Everything visitors see; the admin screens |
| Back end (Flask routes) | Validates input, checks login, reads/writes the database, sends email |
| Database (SQLite) | Profile, skills, projects, certificates, experience, messages, settings, admin account |
| File storage (`data/uploads/`) | Profile photo, project images, certificates, resumes (`profile/`, `projects/`, `certificates/`, `resumes/`) |

---

## 2. Run it on your Windows PC with VS Code

### One-time preparation
1. Install **Python 3.11 or newer** from <https://www.python.org/downloads/>. On the first installer screen tick
   **"Add python.exe to PATH"**.
2. Install **VS Code** from <https://code.visualstudio.com/> and, inside it, the **Python** extension.

### Steps
1. Download `Ruban_Portfolio.zip`, right-click it, choose **Extract All...** and pick a folder (e.g. `C:\Projects`).
2. Open VS Code -> **File -> Open Folder...** -> choose the `Ruban_Portfolio` folder.
3. Open the terminal: **Terminal -> New Terminal** (PowerShell is fine).
4. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   venv\Scripts\activate
   ```
   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.
   (Your prompt should now start with `(venv)`.)
5. Install the packages:
   ```powershell
   pip install -r requirements.txt
   ```
6. Create your settings file:
   ```powershell
   copy .env.example .env
   ```
   Open `.env` and **change `ADMIN_SETUP_KEY`** to your own long random text. (Add your Resend key later, see section 4.)
7. Start the website:
   ```powershell
   python app.py
   ```
8. Open <http://127.0.0.1:5000> in your browser. Stop the server with **Ctrl+C**.

> Shortcut: after extracting, you can simply **double-click `setup_and_run.bat`** - it does steps 4-7 for you.

### Create your admin account (first time only)
1. Go to <http://127.0.0.1:5000/admin/setup>.
2. Enter the setup key from your `.env`, choose a username and a password (at least 10 characters).
3. Log in at <http://127.0.0.1:5000/admin/login>.

This setup page works **only while no admin exists**; afterwards it returns "not found".
Forgot your password? Run `flask --app app create-admin` in the terminal - it creates or resets an admin.

### First things to do in the dashboard
1. **Profile** - upload your photograph (until then a clean "R.S" placeholder is shown).
2. **Skills** - set your real proficiency percentages (they start at 0 and no bar is shown for 0 - nothing is invented).
3. **Projects** - add your projects (thumbnail, screenshots, description, technologies, links). Tick *Featured* to show
   it in the Featured Projects section.
4. **Certifications**, **Experience**, **Resume** - add content as you earn it.

### Run the automated tests (optional)
```powershell
python -m unittest discover -s tests -v
```
They use a temporary database, so your real data is not touched.

---

## 3. What each admin page does

| Page | Features |
|---|---|
| Dashboard | Totals (projects, published, certificates, skills, messages), latest updates, recent messages, quick actions |
| Profile | Name, title, about, location, email, phone, LinkedIn, GitHub, tagline, education, upload/replace/remove photo |
| Skills | Add, edit, delete, change category, set % level, reorder (arrows), enable/disable |
| Projects | Create/edit/delete, thumbnail + multiple screenshots, technologies picked from your skills, GitHub/live URLs, category, completion date, publish/unpublish, feature, reorder |
| Certifications | Upload JPG/PNG/PDF, edit details, replace file, publish/hide, reorder, delete |
| Resume | Upload a PDF **or** use a link (e.g. Google Drive); the most recently saved one is used by the website; change displayed title; live preview |
| Experience | Internships, workshops, jobs: add/edit/delete/reorder/publish |
| Images | Library of all uploaded files, shows which are in use, upload more, delete unused files |
| Messages | Name, email, subject, message, date, read/unread, reply, delete |
| Website Settings | Site title, search description, hero subtitle/tagline, typing words, footer text, social links, change password, **download backup** |

---

## 4. Contact form email (Resend)

1. Create a free account at <https://resend.com> and create an **API key**.
2. Put it in `.env`: `RESEND_API_KEY=re_xxxxxxxx` (never put it in HTML or JavaScript).
3. **Important limitation of the free test sender:** `onboarding@resend.dev` can only deliver to the email address you
   used to register on Resend. Register Resend with `rubansamuel2007@gmail.com`, **or** verify your own domain in Resend
   and set `RESEND_FROM_EMAIL=Portfolio <hello@yourdomain.com>`.
4. `CONTACT_TO_EMAIL` is where messages are delivered (default: your Gmail).

Every message is **also saved in the database** (Admin -> Messages), even if email delivery fails, so nothing is lost.
Spam protection: hidden honeypot field, minimum fill-in time, duplicate detection, server-side validation and rate limits
(5 per hour per visitor).

---

## 5. Deploy to Render (simplest reliable way)

1. Create a GitHub repository and upload the project **without** `.env` and `data/` (the included `.gitignore` handles it).
2. On <https://render.com> choose **New -> Blueprint**, select your repo. Render reads `render.yaml`.
3. In the Render dashboard fill in the environment variables marked "sync: false": `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, optional `GITHUB_TOKEN`.
   Open the generated `ADMIN_SETUP_KEY` value (Environment tab) - you need it for the setup page.
4. After the first deploy open `https://your-app.onrender.com/admin/setup`, create your admin account, then log in.

Manual setup instead of a Blueprint: *New -> Web Service*, build command `pip install -r requirements.txt`, start command
`gunicorn app:app --workers 1 --threads 4 --timeout 60`, add a **Disk** mounted at `/var/data`, and set the environment
variables `DATA_DIR=/var/data`, `COOKIE_SECURE=true`, `SECRET_KEY` (any long random text), `ADMIN_SETUP_KEY`, `RESEND_API_KEY`.

### Database persistence, uploaded files and backups (please read)
* The database is a single SQLite file and uploads are normal files. **Both live in `DATA_DIR`.**
* Render's normal disk is **erased on every deploy and restart**. To keep your data you need a **Render Disk** (paid
  "Starter" plan or higher, around US$7/month) mounted at `/var/data` with `DATA_DIR=/var/data`. This is already in `render.yaml`.
* On a free plan without a Disk, everything you add through the dashboard would disappear on redeploy. Do not use that for the real site.
* **Backups:** Admin -> Website Settings -> **Download backup** gives one ZIP with `portfolio.db` and all `uploads/`.
  Download one regularly (e.g. monthly and before any big change).
* **Restore:** stop the app, put `portfolio.db` into `DATA_DIR` and the `uploads` folder next to it, start the app.
* Use only **one** web worker (as configured): SQLite and the in-memory rate limiter are designed for a single small instance.

---

## 6. Security summary

* Passwords are hashed (Werkzeug); login is rate-limited (10 attempts / 15 min) and shows the same error for unknown users and wrong passwords.
* Every `/admin/*` page (except login/setup) is blocked on the **server** for anonymous visitors; all changes are POST requests protected by **CSRF tokens**.
* Sessions expire after `SESSION_HOURS` (default 8), cookies are `HttpOnly` + `SameSite=Lax` (+ `Secure` on HTTPS).
* Uploads: file type is detected from the file's real content (not its name), only JPG/PNG/WebP (images) and PDF are
  accepted, size limits (5 MB images, 10 MB PDF), random file names, path-traversal protection.
* Secrets (secret key, Resend key, GitHub token) come from environment variables - never from front-end code.
* CORS: the API is same-origin only (no cross-origin access is enabled).
* Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) and `Cache-Control: no-store` on admin pages.

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognised | Reinstall Python and tick "Add python.exe to PATH", then reopen VS Code |
| `/admin/setup` says setup is locked | Set `ADMIN_SETUP_KEY` in `.env` and restart `python app.py` |
| Icons/fonts look missing | The site loads icon fonts from a CDN; check your internet connection |
| GitHub section says unavailable | GitHub rate limit; wait or add `GITHUB_TOKEN` to `.env` |
| Contact form works but no email arrives | Check `RESEND_API_KEY`; with the free test sender the recipient must be your Resend account email. The message is still in Admin -> Messages |
| "Your form session expired" | Reload the page and submit again |
#   R u b a n _ P o r t f o l i o  
 