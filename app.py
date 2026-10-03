from flask import Flask, render_template, request, jsonify, session
from groq import Groq
import os
import json
import secrets
import urllib.request
import urllib.error


# ============================================================
# APP CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path="/static"
)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise ValueError(
        "FLASK_SECRET_KEY is not set."
    )


# ============================================================
# GROQ
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is not set."
    )

client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME = "openai/gpt-oss-120b"


# ============================================================
# UPSTASH REDIS
# ============================================================

UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

if not UPSTASH_URL or not UPSTASH_TOKEN:
    raise ValueError(
        "UPSTASH_REDIS_REST_URL and "
        "UPSTASH_REDIS_REST_TOKEN are not set."
    )


# ============================================================
# AI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are Hani AI, a friendly, intelligent and multilingual AI assistant.

LANGUAGE:
- Automatically detect the language used by the user.
- Reply in the same language whenever possible.
- Support English, Urdu, Roman Urdu, Hindi, Arabic and other
  languages supported by the model.
- If the user mixes languages, understand the mixed language naturally.
- If the user specifically requests a language, use that language.
- If the user writes Roman Urdu, respond naturally in Roman Urdu
  unless they request another language.
- Never translate a question unless the user asks for translation.

CONVERSATION MEMORY:
- Use previous messages from the current conversation.
- Understand follow-up questions.
- Maintain context naturally.
- Do not unnecessarily ask the user to repeat information.
- Do not claim to remember information that is not available.

ANSWER STYLE:
- Be friendly, respectful and helpful.
- Keep simple questions concise.
- Give detailed answers when requested.
- Use headings, bullet points and numbered steps when useful.
- Explain difficult concepts simply.
- Give examples when useful.
- For programming questions, provide working and readable code.
- Explain important code clearly.
- If the user is confused, explain the topic more simply.
- Avoid unnecessary repetition.

GENERAL:
- Be natural and conversational.
- Be honest about limitations.
- Ask a clarification only when genuinely necessary.
- Never claim to have performed an action you did not perform.
"""


# ============================================================
# REDIS COMMAND
# ============================================================

def redis_command(command):

    url = UPSTASH_URL.rstrip("/")

    data = json.dumps(command).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {UPSTASH_TOKEN}",
            "Content-Type": "application/json"
        }
    )

    try:

        with urllib.request.urlopen(req, timeout=15) as response:

            result = json.loads(
                response.read().decode("utf-8")
            )

        return result.get("result")

    except urllib.error.HTTPError as error:

        print(
            "Redis HTTP error:",
            error.code
        )

        raise RuntimeError(
            "Database request failed."
        )

    except Exception as error:

        print(
            "Redis error:",
            str(error)
        )

        raise RuntimeError(
            "Database connection failed."
        )


# ============================================================
# USER ID
# ============================================================

def get_user_id():

    if "user_id" not in session:

        session["user_id"] = secrets.token_urlsafe(24)
        session.modified = True

    return session["user_id"]


# ============================================================
# REDIS KEYS
# ============================================================

def chats_key(user_id):

    return f"hani:user:{user_id}:chats"


def chat_key(user_id, chat_id):

    return f"hani:user:{user_id}:chat:{chat_id}"


# ============================================================
# CHAT LIST
# ============================================================

def get_user_chats(user_id):

    data = redis_command([
        "GET",
        chats_key(user_id)
    ])

    if not data:
        return []

    try:
        return json.loads(data)

    except Exception:
        return []


def save_user_chats(user_id, chats):

    redis_command([
        "SET",
        chats_key(user_id),
        json.dumps(chats),
        "EX",
        "2592000"
    ])


# ============================================================
# SINGLE CHAT
# ============================================================

def get_chat(user_id, chat_id):

    data = redis_command([
        "GET",
        chat_key(user_id, chat_id)
    ])

    if not data:
        return None

    try:
        return json.loads(data)

    except Exception:
        return None


def save_chat(user_id, chat):

    redis_command([
        "SET",
        chat_key(user_id, chat["id"]),
        json.dumps(chat),
        "EX",
        "2592000"
    ])


def delete_chat_from_database(user_id, chat_id):

    redis_command([
        "DEL",
        chat_key(user_id, chat_id)
    ])


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# GET CHAT LIST
# ============================================================

@app.route("/api/chats", methods=["GET"])
def get_chats():

    try:

        user_id = get_user_id()

        chats = get_user_chats(user_id)

        return jsonify({
            "success": True,
            "chats": chats
        })

    except Exception as error:

        print("Get chats error:", str(error))

        return jsonify({
            "success": False,
            "error": "Could not load chat history."
        }), 500


# ============================================================
# CREATE NEW CHAT
# ============================================================

@app.route("/api/chats", methods=["POST"])
def create_chat():

    try:

        user_id = get_user_id()

        chat_id = secrets.token_urlsafe(16)

        chat = {
            "id": chat_id,
            "title": "New Chat",
            "messages": []
        }

        save_chat(
            user_id,
            chat
        )

        chats = get_user_chats(user_id)

        chats.insert(
            0,
            {
                "id": chat_id,
                "title": "New Chat"
            }
        )

        save_user_chats(
            user_id,
            chats
        )

        return jsonify({
            "success": True,
            "chat": chat
        })

    except Exception as error:

        print("Create chat error:", str(error))

        return jsonify({
            "success": False,
            "error": "Could not create a new chat."
        }), 500


# ============================================================
# GET SINGLE CHAT
# ============================================================

@app.route("/api/chats/<chat_id>", methods=["GET"])
def get_single_chat(chat_id):

    try:

        user_id = get_user_id()

        chat = get_chat(
            user_id,
            chat_id
        )

        if not chat:

            return jsonify({
                "success": False,
                "error": "Chat not found."
            }), 404

        return jsonify({
            "success": True,
            "chat": chat
        })

    except Exception as error:

        print(
            "Get single chat error:",
            str(error)
        )

        return jsonify({
            "success": False,
            "error": "Could not load this chat."
        }), 500


# ============================================================
# DELETE ONE CHAT
# ============================================================

@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):

    try:

        user_id = get_user_id()

        delete_chat_from_database(
            user_id,
            chat_id
        )

        chats = get_user_chats(user_id)

        chats = [
            chat
            for chat in chats
            if chat.get("id") != chat_id
        ]

        save_user_chats(
            user_id,
            chats
        )

        return jsonify({
            "success": True,
            "message": "Chat deleted."
        })

    except Exception as error:

        print(
            "Delete chat error:",
            str(error)
        )

        return jsonify({
            "success": False,
            "error": "Could not delete chat."
        }), 500


# ============================================================
# CHAT WITH AI
# ============================================================

@app.route("/chat", methods=["POST"])
def chat():

    try:

        user_id = get_user_id()

        data = request.get_json(
            silent=True
        ) or {}

        user_message = data.get(
            "message",
            ""
        ).strip()

        chat_id = data.get(
            "chat_id"
        )

        # ----------------------------------------------------
        # Validate message
        # ----------------------------------------------------

        if not user_message:

            return jsonify({
                "success": False,
                "reply": "Please enter a message."
            }), 400

        if len(user_message) > 10000:

            return jsonify({
                "success": False,
                "reply": (
                    "Your message is too long. "
                    "Please shorten it."
                )
            }), 400

        # ----------------------------------------------------
        # Create chat automatically if needed
        # ----------------------------------------------------

        if not chat_id:

            chat_id = secrets.token_urlsafe(16)

            chat = {
                "id": chat_id,
                "title": "New Chat",
                "messages": []
            }

            save_chat(
                user_id,
                chat
            )

            chats = get_user_chats(
                user_id
            )

            chats.insert(
                0,
                {
                    "id": chat_id,
                    "title": "New Chat"
                }
            )

            save_user_chats(
                user_id,
                chats
            )

        else:

            chat = get_chat(
                user_id,
                chat_id
            )

            if not chat:

                return jsonify({
                    "success": False,
                    "reply": "Chat not found."
                }), 404

        # ----------------------------------------------------
        # Add user message
        # ----------------------------------------------------

        chat["messages"].append({
            "role": "user",
            "content": user_message
        })

        # ----------------------------------------------------
        # Prepare AI context
        # ----------------------------------------------------

        recent_messages = chat[
            "messages"
        ][-30:]

        messages_for_ai = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]

        messages_for_ai.extend(
            recent_messages
        )

        # ----------------------------------------------------
        # Groq request
        # ----------------------------------------------------

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_for_ai,
            temperature=0.7,
            max_tokens=2000
        )

        reply = response.choices[
            0
        ].message.content

        if not reply:

            reply = (
                "Sorry, I couldn't generate "
                "a response."
            )

        # ----------------------------------------------------
        # Save AI response
        # ----------------------------------------------------

        chat["messages"].append({
            "role": "assistant",
            "content": reply
        })

        # ----------------------------------------------------
        # Generate title
        # ----------------------------------------------------

        if chat["title"] == "New Chat":

            title = user_message[:40].strip()

            if len(user_message) > 40:

                title += "..."

            chat["title"] = title

        # ----------------------------------------------------
        # Save chat
        # ----------------------------------------------------

        save_chat(
            user_id,
            chat
        )

        # ----------------------------------------------------
        # Update chat list
        # ----------------------------------------------------

        chats = get_user_chats(
            user_id
        )

        found = False

        for item in chats:

            if item.get("id") == chat_id:

                item["title"] = chat["title"]

                found = True

                break

        if not found:

            chats.insert(
                0,
                {
                    "id": chat_id,
                    "title": chat["title"]
                }
            )

        # Move current chat to top
        chats = (
            [
                item
                for item in chats
                if item.get("id") == chat_id
            ]
            +
            [
                item
                for item in chats
                if item.get("id") != chat_id
            ]
        )

        save_user_chats(
            user_id,
            chats
        )

        # ----------------------------------------------------
        # Return response
        # ----------------------------------------------------

        return jsonify({
            "success": True,
            "reply": reply,
            "chat_id": chat_id,
            "title": chat["title"]
        })

    except Exception as error:

        print(
            "Chat error:",
            str(error)
        )

        return jsonify({
            "success": False,
            "reply": (
                "Sorry, something went wrong. "
                "Please try again."
            )
        }), 500


# ============================================================
# CLEAR ALL HISTORY
# ============================================================

@app.route("/api/chats", methods=["DELETE"])
def clear_all_chats():

    try:

        user_id = get_user_id()

        chats = get_user_chats(
            user_id
        )

        for chat in chats:

            chat_id = chat.get("id")

            if chat_id:

                delete_chat_from_database(
                    user_id,
                    chat_id
                )

        save_user_chats(
            user_id,
            []
        )

        return jsonify({
            "success": True,
            "message": "All chat history cleared."
        })

    except Exception as error:

        print(
            "Clear history error:",
            str(error)
        )

        return jsonify({
            "success": False,
            "error": "Could not clear history."
        }), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "online",
        "assistant": "Hani AI",
        "model": MODEL_NAME
    })


# ============================================================
# LOCAL SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
