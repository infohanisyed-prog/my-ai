# MY-AI — Vercel + GitHub deployment package

This version adapts the existing plain HTML/CSS/JS frontend and Groq-powered Python API for Vercel Functions. Persistent user accounts, sessions, and chats use Supabase Postgres; Vercel's function filesystem is not used for user data.

## What changed
- Preserved the existing frontend files and same-origin API paths.
- Replaced the long-running `http.server` deployment entry with a FastAPI app at `api/index.py`, supported by Vercel's Python runtime.
- Moved users, sessions, and chat history from JSON files into PostgreSQL.
- Disabled password-free demo login on the public deployment.
- Kept the Groq key server-side; never place it in `app.js`.
- Removed local `data/*.json` files from this deployment package so private/local records are not accidentally published.

## Before deploying
You need:
1. A GitHub account and a Vercel account.
2. A Supabase project (Postgres database).
3. A Groq API key.

### 1. Create the database
- Create a Supabase project.
- Open **SQL Editor** in Supabase.
- Paste and run all of `supabase_schema.sql`.
- In Supabase project settings, find the PostgreSQL connection string (URI). Use the direct connection string or the pooler connection string recommended for serverless clients.
- Keep the database password private.

### 2. Push this folder to GitHub
Create a new private repository, for example `my-ai-chatbot`.
On your computer, open a terminal in this extracted project folder and run:

```bash
git init
git add .
git commit -m "Prepare MY-AI for Vercel deployment"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/my-ai-chatbot.git
git push -u origin main
```

Replace `YOUR-USERNAME` with your GitHub username. Do not upload `.env`, API keys, database passwords, or private user data.

### 3. Import into Vercel
- Sign in to Vercel and choose **Add New → Project**.
- Import the GitHub repository you just created.
- Keep the project root at the repository root.
- No frontend build command is required for this plain HTML/CSS/JS project.
- Deploy after setting the environment variables below (or add them in Project Settings and redeploy).

### 4. Add Vercel Environment Variables
In Vercel → Project → Settings → Environment Variables, add:

| Name | Value |
|---|---|
| `GROQ_API_KEY` | Your Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` (or a model available in your Groq account) |
| `DATABASE_URL` | Your Supabase PostgreSQL connection URI |

Apply them to **Production**, **Preview**, and **Development** as appropriate. Do not add quotes around values. Then redeploy.

### 5. Test the live site
Open the Vercel deployment URL:
- Register a new account (password must be at least 8 characters).
- Log out and log back in.
- Create a chat and send a message.
- Refresh the page and verify chat history remains.
- Check `/api/health` to confirm `databaseConfigured` and `groqConfigured` are true.

## Important notes
- Public registration is enabled. Share the website URL, not your API keys or database URL.
- The public demo-login endpoint is deliberately disabled; each visitor should create their own account.
- This package uses the database connection string only on the server. Do not expose it in frontend JavaScript.
- For production, configure database backups and monitor Groq usage/limits. Add rate limiting and email verification before inviting a large public audience.
- The existing standalone `server.py` is retained for local reference, but Vercel runs `api/index.py`.
- `Secure` cookies require HTTPS; Vercel deployments use HTTPS.
