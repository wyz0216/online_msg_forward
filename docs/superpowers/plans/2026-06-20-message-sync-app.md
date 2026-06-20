# Message Sync App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small FastAPI web app where registered users can create private text/file/image messages with optional expiration, plus an Ubuntu deployment script.

**Architecture:** The app uses FastAPI routes with server-rendered Jinja2 pages. SQLite stores users and message metadata, while uploaded files are stored on disk under a configured upload directory. Cleanup runs opportunistically on requests and through a token-protected local endpoint intended for a systemd timer.

**Tech Stack:** Python, FastAPI, Jinja2, SQLite, pytest, httpx, uvicorn, python-multipart.

---

### Task 1: Project Skeleton And Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_config.py` with tests for default settings and environment overrides.

- [ ] **Step 2: Run configuration tests and verify they fail**

Run: `python -m pytest tests/test_config.py -q`
Expected: failure because `app.config` does not exist.

- [ ] **Step 3: Add dependencies and minimal config implementation**

Create `requirements.txt`, `.gitignore`, `app/__init__.py`, and `app/config.py`.

- [ ] **Step 4: Run configuration tests and verify they pass**

Run: `python -m pytest tests/test_config.py -q`
Expected: all tests pass.

### Task 2: Database And Authentication

**Files:**
- Create: `app/db.py`
- Create: `app/auth.py`
- Create: `tests/conftest.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write failing auth tests**

Cover registration, duplicate username rejection, successful login, bad password rejection, and protected home access.

- [ ] **Step 2: Run auth tests and verify they fail**

Run: `python -m pytest tests/test_auth.py -q`
Expected: failure because app routes and auth functions do not exist.

- [ ] **Step 3: Implement SQLite tables, password hashing, session auth, and auth routes**

Implement `users` table, password hashing with `passlib[bcrypt]`, login/logout/register routes, and current-user dependency.

- [ ] **Step 4: Run auth tests and verify they pass**

Run: `python -m pytest tests/test_auth.py -q`
Expected: all auth tests pass.

### Task 3: Messages, Uploads, Permissions, And Cleanup

**Files:**
- Create: `app/messages.py`
- Modify: `app/main.py`
- Test: `tests/test_messages.py`

- [ ] **Step 1: Write failing message tests**

Cover private message visibility, private download/delete enforcement, text message creation, upload size rejection, allowed expiration choices, and cleanup deleting expired records and files.

- [ ] **Step 2: Run message tests and verify they fail**

Run: `python -m pytest tests/test_messages.py -q`
Expected: failure because message routes do not exist.

- [ ] **Step 3: Implement message routes and cleanup**

Implement message creation, download, delete, owner checks, file storage with random stored names, expiration validation, and token-protected cleanup.

- [ ] **Step 4: Run message tests and verify they pass**

Run: `python -m pytest tests/test_messages.py -q`
Expected: all message tests pass.

### Task 4: Templates, Styles, And App Wiring

**Files:**
- Create: `app/main.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/templates/register.html`
- Create: `app/templates/index.html`
- Create: `app/static/style.css`

- [ ] **Step 1: Wire app factory and pages**

Create a `create_app()` factory, mount static files, initialize the database at startup, include auth/message routes, and render the required pages.

- [ ] **Step 2: Run all Python tests**

Run: `python -m pytest -q`
Expected: all tests pass.

### Task 5: Deployment Script And Documentation

**Files:**
- Create: `deploy_ubuntu.sh`
- Modify: `README.md`

- [ ] **Step 1: Add deployment script**

Create an Ubuntu script that installs Python dependencies, copies the project to `/opt/online_msg_forward`, creates `.env`, creates a systemd app service, creates a cleanup timer, and does not install or modify nginx.

- [ ] **Step 2: Add README usage and deployment notes**

Document local run, tests, environment variables, and nginx ownership.

- [ ] **Step 3: Verify shell script syntax**

Run: `bash -n deploy_ubuntu.sh`
Expected: no syntax errors.

- [ ] **Step 4: Run full verification**

Run: `python -m pytest -q`
Expected: all tests pass.

