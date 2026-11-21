# 🚀 Daily Startup Guide (Super Simple)

Follow these steps in order. Do not skip steps.

> ⚠️ **First:** Make sure **Docker Desktop** is open and running!

---

## 🟢 Part 1: Start Everything (Daily Routine)

### Step 1: Start Database & Backend
Open **Terminal 1** in VS Code, paste this, and press Enter:

```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml up -d db mailpit backend
```

*(Wait about 5-10 seconds for the database and backend to turn green)*

---

### Step 2: Start the Website (Frontend)
Open **Terminal 2** (click the `+` icon in the terminal panel), paste this, and press Enter:

```powershell
npm --prefix frontend run dev
```

*(Keep this terminal open while you work!)*

---

### Step 3: Open the Website in Your Browser
Open Chrome/Edge and go to:
👉 **http://localhost:3000**

**Login Credentials:**
- **Email:** `admin@acme.test`
- **Password:** `ChangeMe!12345`

You are ready to code! 🎉

---

## 🔴 Part 2: Stop Everything (When You Are Done)

1. Go to **Terminal 2** (Frontend) and press:
   `Ctrl + C` (then type `y` if asked)

2. Go to **Terminal 1** and run:
   ```powershell
   docker compose --env-file .env -f infrastructure\docker-compose.yml stop
   ```

---

## ❓ "Do I need to run Alembic Migrations every day?"

**No!** You do **not** need to run migrations every day.
- Docker saves all your database tables permanently in a volume (`pgdata`).
- When you stop Docker at the end of the day, your data and tables stay safe.

**When DO you run migrations?** Only in 2 situations:
1. **The very first time** you set up the database on a new computer.
2. **When you add new database tables or columns** in your code (or `git pull` new ones).

If you are ever unsure, it is safe to run it anytime in **Terminal 1**:
```powershell
docker compose --env-file .env -f infrastructure\docker-compose.yml exec backend alembic upgrade head
```
*(If tables are already up to date, it just does nothing!)*

---

## 🛠️ Part 3: Cheat Sheet (Only When You Need It)

| What happened? | Run this command: |
|---|---|
| **I changed Python code and need backend to update** | `docker compose --env-file .env -f infrastructure\docker-compose.yml restart backend` |
| **I need to update database tables (run migrations)** | `docker compose --env-file .env -f infrastructure\docker-compose.yml exec backend alembic upgrade head` |
| **I want to see backend error logs** | `docker logs infrastructure-backend-1 --tail 50 -f` |
| **I need fresh demo accounts / sample data** | `docker compose --env-file .env -f infrastructure\docker-compose.yml exec backend python -m app.scripts.seed` |
| **I want to start AI worker & n8n workflows** | `docker compose --env-file .env -f infrastructure\docker-compose.yml up -d worker dispatcher n8n_db n8n` |

---

## 📌 Useful Links

- **CRM Website:** [http://localhost:3000](http://localhost:3000)
- **Backend API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Local Email Inbox (Mailpit):** [http://localhost:8025](http://localhost:8025)
| If you need to... | Run this command: |
| --- | --- |
| Reload backend after editing Python code | `docker compose --env-file .env -f infrastructure\docker-compose.yml restart backend` |
| Apply database changes (migrations) | `docker compose --env-file .env -f infrastructure\docker-compose.yml exec backend alembic upgrade head` |
| See backend error logs | `docker logs infrastructure-backend-1 --tail 50 -f` |
| Reset demo data / users | `docker compose --env-file .env -f infrastructure\docker-compose.yml exec backend python -m app.scripts.seed` |
