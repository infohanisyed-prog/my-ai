import os, uuid, time, hashlib, hmac, secrets
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import psycopg
from psycopg.rows import dict_row
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
import json

app = FastAPI(title="MY-AI API")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = os.getenv("DATABASE_URL", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
COOKIE_NAME = "myai_session"
SESSION_TTL = 60 * 60 * 24 * 30
SYSTEM_PROMPT = "You are My AI — a sharp, calm, helpful assistant. Answer clearly. Use markdown when useful. Be concise unless the user asks for depth."

def db():
    if not DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL is not configured in Vercel environment variables.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, sslmode="require", connect_timeout=10)

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS chats (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), messages JSONB NOT NULL DEFAULT '[]'::jsonb
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS chats_user_updated_idx ON chats(user_id, updated_at DESC)")

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()
    return salt, digest

def user_from_request(request):
    token = request.cookies.get(COOKIE_NAME)
    if not token: return None
    with db() as conn:
        return conn.execute("""SELECT u.id, u.name, u.email FROM sessions s
          JOIN users u ON u.id=s.user_id WHERE s.token=%s AND s.created_at > NOW() - INTERVAL '30 days'""",
          (token,)).fetchone()

def require_user(request):
    user = user_from_request(request)
    if not user: raise HTTPException(401, "Not authenticated")
    return user

def set_cookie(response, token):
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_TTL, httponly=True,
                        secure=True, samesite="lax", path="/")

def create_session(user_id):
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO sessions(token,user_id) VALUES(%s,%s)", (token,user_id))
    return token

def groq(messages):
    if not GROQ_API_KEY: raise HTTPException(503, "GROQ_API_KEY is not configured.")
    payload=json.dumps({"model":GROQ_MODEL,"messages":messages,"temperature":0.7,"max_tokens":4096}).encode()
    req=URLRequest("https://api.groq.com/openai/v1/chat/completions", data=payload,
        headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json","User-Agent":"MY-AI/1.0"})
    try:
        with urlopen(req,timeout=90) as r: data=json.loads(r.read().decode())
    except HTTPError as e:
        detail=e.read().decode(errors="replace")
        raise HTTPException(502, f"Groq API error ({e.code}): {detail[:500]}")
    except URLError as e: raise HTTPException(502, f"Cannot reach Groq: {e.reason}")
    choices=data.get("choices") or []
    if not choices: raise HTTPException(502,"Groq returned an empty response.")
    return choices[0]["message"]["content"]

@app.get("/api/health")
def health():
    return {"ok":True,"databaseConfigured":bool(DATABASE_URL),"groqConfigured":bool(GROQ_API_KEY)}

@app.get("/api/auth/me")
def auth_me(request: Request):
    return {"user":user_from_request(request),"demoAvailable":False,"groqConfigured":bool(GROQ_API_KEY)}

@app.post("/api/auth/register")
def register(payload: dict, response: Response):
    email=str(payload.get("email","")).strip().lower()
    password=str(payload.get("password",""))
    name=str(payload.get("name","")).strip() or email.split("@")[0]
    if not email or "@" not in email or len(password)<8: raise HTTPException(400,"Enter a valid email and a password of at least 8 characters.")
    uid=str(uuid.uuid4()); salt,pwh=password_hash(password)
    try:
        with db() as conn:
            conn.execute("INSERT INTO users(id,email,name,salt,password_hash) VALUES(%s,%s,%s,%s,%s)",(uid,email,name,salt,pwh))
    except psycopg.errors.UniqueViolation: raise HTTPException(409,"Account already exists — please sign in.")
    token=create_session(uid); set_cookie(response,token)
    return JSONResponse({"ok":True,"user":{"id":uid,"name":name,"email":email}},status_code=201,headers={"Set-Cookie":response.headers.get("set-cookie","")})

@app.post("/api/auth/login")
def login(payload: dict, response: Response):
    email=str(payload.get("email","")).strip().lower(); password=str(payload.get("password",""))
    with db() as conn: user=conn.execute("SELECT * FROM users WHERE email=%s",(email,)).fetchone()
    if not user: raise HTTPException(401,"Invalid email or password.")
    _, check=password_hash(password,user["salt"])
    if not hmac.compare_digest(check,user["password_hash"]): raise HTTPException(401,"Invalid email or password.")
    token=create_session(user["id"])
    out=JSONResponse({"ok":True,"user":{"id":user["id"],"name":user["name"],"email":user["email"]}})
    set_cookie(out,token); return out

@app.post("/api/auth/demo-login")
def demo_disabled():
    raise HTTPException(403,"Demo login is disabled on the public deployment.")

@app.post("/api/auth/logout")
def logout(request: Request):
    token=request.cookies.get(COOKIE_NAME)
    if token:
        with db() as conn: conn.execute("DELETE FROM sessions WHERE token=%s",(token,))
    out=JSONResponse({"ok":True}); out.delete_cookie(COOKIE_NAME,path="/"); return out

@app.get("/api/chats")
def list_chats(request: Request):
    user=require_user(request)
    with db() as conn:
        rows=conn.execute("SELECT id,title,created_at,updated_at FROM chats WHERE user_id=%s ORDER BY updated_at DESC",(user["id"],)).fetchall()
    return {"chats":[{"id":r["id"],"title":r["title"],"createdAt":r["created_at"].isoformat(),"updatedAt":r["updated_at"].isoformat()} for r in rows]}

@app.post("/api/chats")
def create_chat(payload: dict, request: Request):
    user=require_user(request); cid=str(uuid.uuid4()); title=str(payload.get("title","New chat"))[:80] or "New chat"
    with db() as conn:
        row=conn.execute("INSERT INTO chats(id,user_id,title) VALUES(%s,%s,%s) RETURNING id,title,created_at,updated_at",(cid,user["id"],title)).fetchone()
    return JSONResponse({"chat":{"id":row["id"],"title":row["title"],"createdAt":row["created_at"].isoformat(),"updatedAt":row["updated_at"].isoformat()}},status_code=201)

@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    user=require_user(request)
    with db() as conn: row=conn.execute("SELECT * FROM chats WHERE id=%s AND user_id=%s",(chat_id,user["id"])).fetchone()
    if not row: raise HTTPException(404,"Chat not found")
    chat={"id":row["id"],"title":row["title"],"createdAt":row["created_at"].isoformat(),"updatedAt":row["updated_at"].isoformat(),"messages":row["messages"]}
    return {"chat":chat,"messages":row["messages"]}

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    user=require_user(request)
    with db() as conn: cur=conn.execute("DELETE FROM chats WHERE id=%s AND user_id=%s",(chat_id,user["id"]))
    if cur.rowcount==0: raise HTTPException(404,"Chat not found")
    return {"ok":True}

@app.delete("/api/chats")
def clear_chats(request: Request):
    user=require_user(request)
    with db() as conn: conn.execute("DELETE FROM chats WHERE user_id=%s",(user["id"],))
    return {"ok":True}

@app.post("/chat")
def chat(payload: dict, request: Request):
    user=require_user(request); cid=str(payload.get("chat_id","")); message=str(payload.get("message","")).strip(); regen=bool(payload.get("regenerate"))
    with db() as conn: row=conn.execute("SELECT * FROM chats WHERE id=%s AND user_id=%s",(cid,user["id"])).fetchone()
    if not row: raise HTTPException(404,"Chat not found")
    messages=list(row["messages"] or [])
    if regen:
        while messages and messages[-1].get("role")=="assistant": messages.pop()
        if not messages or messages[-1].get("role")!="user": raise HTTPException(400,"Nothing to regenerate")
    else:
        if not message: raise HTTPException(400,"message required")
        messages.append({"id":str(uuid.uuid4()),"role":"user","content":message,"createdAt":datetime.now(timezone.utc).isoformat()})
    history=[{"role":"system","content":SYSTEM_PROMPT}]+[{"role":m["role"],"content":m.get("content","")} for m in messages if m.get("role") in ("user","assistant")]
    answer=groq(history)
    assistant={"id":str(uuid.uuid4()),"role":"assistant","content":answer,"createdAt":datetime.now(timezone.utc).isoformat()}
    messages.append(assistant)
    title=row["title"]
    if title in ("New chat","New conversation") and messages:
        first=next((m for m in messages if m["role"]=="user"),None)
        if first: title=first["content"][:56]
    with db() as conn:
        conn.execute("UPDATE chats SET messages=%s,title=%s,updated_at=NOW() WHERE id=%s AND user_id=%s",(json.dumps(messages),title,cid,user["id"]))
    return {"message":assistant,"chat":{"id":cid,"title":title}}
