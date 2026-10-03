import os
import json
import uuid
from datetime import datetime

import requests
from flask import Flask, render_template, request, jsonify, session
from groq import Groq


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path="/static"
)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "my-ai-development-secret-key"
)


# =========================
# ENVIRONMENT VARIABLES
# =========================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")


# =========================
# GROQ
# =========================

groq_client = None

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)


MODEL_NAME = "openai/gpt-oss-120b"


# =========================
# AI SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
You are My AI, a friendly and helpful multilingual AI assistant.

Important instructions:

1. Reply in the same language as the user whenever possible.
2. If the user writes in Roman Urdu, reply in simple Roman Urdu.
3. If the user writes Urdu script, reply in Urdu script.
4. If the user writes English, reply in English.
5. If the user mixes Urdu and English, naturally use the same style.
6. Explain educational topics clearly and step by step.
7. For programming questions, provide correct and practical code.
8. Be friendly, natural and concise unless the user asks for detailed information.
9. Do not claim to remember information that is not present in the current conversation.
10. Do not invent facts.
"""


# =========================
# REDIS FUNCTIONS
# =========================

def redis_is_available():
    return bool(
        UPSTASH_REDIS_REST_URL
        and UPSTASH_REDIS_REST_TOKEN
    )


def redis_headers():
    return {
        "Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}",
        "Content-Type": "application/json"
    }


def redis_command(command):
    if not redis_is_available():
        return None

    try:
        response = requests.post(
            UPSTASH_REDIS_REST_URL,
            headers=redis_headers(),
            json=command,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        return data.get("result")

    except requests.RequestException as error:
        print("Redis connection error:", error)
        return None

    except Exception as error:
        print("Redis error:", error)
        return None


# =========================
# USER ID
# =========================

def get_user_id():

    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

    return session["user_id"]


# =========================
# REDIS KEYS
# =========================

def user_chats_key(user_id):
    return f"myai:user:{user_id}:chats"


def chat_key(user_id, chat_id):
    return f"myai:user:{user_id}:chat:{chat_id}"


# =========================
# CHAT FUNCTIONS
# =========================

def get_user_chats(user_id):

    result = redis_command([
        "GET",
        user_chats_key(user_id)
    ])

    if not result:
        return []

    try:

        chats = json.loads(result)

        if isinstance(chats, list):
            return chats

        return []

    except (json.JSONDecodeError, TypeError):

        return []


def save_user_chats(user_id, chats):

    redis_command([
        "SET",
        user_chats_key(user_id),
        json.dumps(
            chats,
            ensure_ascii=False
        )
    ])


def get_chat(user_id, chat_id):

    if not chat_id:
        return None

    result = redis_command([
        "GET",
        chat_key(user_id, chat_id)
    ])

    if not result:
        return None

    try:

        return json.loads(result)

    except (json.JSONDecodeError, TypeError):

        return None


def save_chat(user_id, chat):

    redis_command([
        "SET",
        chat_key(
            user_id,
            chat["id"]
        ),
        json.dumps(
            chat,
            ensure_ascii=False
        )
    ])


def delete_chat_from_redis(user_id, chat_id):

    redis_command([
        "DEL",
        chat_key(
            user_id,
            chat_id
        )
    ])


# =========================
# CREATE CHAT
# =========================

def create_chat_object():

    now = datetime.utcnow().isoformat()

    return {
        "id": str(uuid.uuid4()),
        "title": "New Chat",
        "created_at": now,
        "updated_at": now,
        "messages": []
    }


# =========================
# CHAT LIST
# =========================

def update_chat_list(user_id, chat):

    chats = get_user_chats(user_id)

    found = False

    for item in chats:

        if item.get("id") == chat["id"]:

            item["title"] = chat["title"]
            item["updated_at"] = chat["updated_at"]

            found = True

            break

    if not found:

        chats.append({
            "id": chat["id"],
            "title": chat["title"],
            "created_at": chat["created_at"],
            "updated_at": chat["updated_at"]
        })

    chats.sort(
        key=lambda item: item.get(
            "updated_at",
            ""
        ),
        reverse=True
    )

    save_user_chats(
        user_id,
        chats
    )


def remove_chat_from_list(
    user_id,
    chat_id
):

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


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================
# GET ALL CHATS
# =========================

@app.route(
    "/api/chats",
    methods=["GET"]
)
def get_chats():

    user_id = get_user_id()

    chats = get_user_chats(
        user_id
    )

    chats.sort(
        key=lambda item: item.get(
            "updated_at",
            ""
        ),
        reverse=True
    )

    return jsonify({
        "success": True,
        "chats": chats
    })


# =========================
# CREATE CHAT
# =========================

@app.route(
    "/api/chats",
    methods=["POST"]
)
def create_chat():

    user_id = get_user_id()

    chat = create_chat_object()

    save_chat(
        user_id,
        chat
    )

    update_chat_list(
        user_id,
        chat
    )

    return jsonify({
        "success": True,
        "chat": chat
    })


# =========================
# DELETE ALL CHATS
# =========================

@app.route(
    "/api/chats",
    methods=["DELETE"]
)
def delete_all_chats():

    user_id = get_user_id()

    chats = get_user_chats(
        user_id
    )

    for chat in chats:

        chat_id = chat.get("id")

        if chat_id:

            delete_chat_from_redis(
                user_id,
                chat_id
            )

    save_user_chats(
        user_id,
        []
    )

    return jsonify({
        "success": True
    })


# =========================
# GET SINGLE CHAT
# =========================

@app.route(
    "/api/chats/<chat_id>",
    methods=["GET"]
)
def get_single_chat(chat_id):

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


# =========================
# DELETE SINGLE CHAT
# =========================

@app.route(
    "/api/chats/<chat_id>",
    methods=["DELETE"]
)
def delete_single_chat(chat_id):

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

    delete_chat_from_redis(
        user_id,
        chat_id
    )

    remove_chat_from_list(
        user_id,
        chat_id
    )

    return jsonify({
        "success": True
    })


# =========================
# AI CHAT
# =========================

@app.route(
    "/chat",
    methods=["POST"]
)
def chat():

    user_id = get_user_id()

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        data = {}

    user_message = str(
        data.get(
            "message",
            ""
        )
    ).strip()

    chat_id = data.get(
        "chat_id"
    )

    # Empty message
    if not user_message:

        return jsonify({
            "success": False,
            "error": "Message cannot be empty."
        }), 400

    # Message too long
    if len(user_message) > 10000:

        return jsonify({
            "success": False,
            "error": "Message is too long."
        }), 400

    # Groq key missing
    if groq_client is None:

        return jsonify({
            "success": False,
            "error": "GROQ_API_KEY is not configured."
        }), 500

    # Get existing chat
    chat_object = None

    if chat_id:

        chat_object = get_chat(
            user_id,
            chat_id
        )

    # Create new chat if needed
    if not chat_object:

        chat_object = create_chat_object()

    # Add user message
    chat_object["messages"].append({

        "role": "user",

        "content": user_message
    })

    # Last 30 messages
    recent_messages = (
        chat_object["messages"][-30:]
    )

    groq_messages = [

        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }

    ]

    for message in recent_messages:

        role = message.get(
            "role"
        )

        content = message.get(
            "content",
            ""
        )

        if role in (
            "user",
            "assistant"
        ):

            groq_messages.append({

                "role": role,

                "content": content

            })

    # =========================
    # CALL GROQ
    # =========================

    try:

        completion = (
            groq_client
            .chat
            .completions
            .create(

                model=MODEL_NAME,

                messages=groq_messages,

                max_tokens=2000,

                temperature=0.7
            )
        )

        assistant_message = (
            completion
            .choices[0]
            .message
            .content
            or ""
        ).strip()

        if not assistant_message:

            assistant_message = (
                "Sorry, I couldn't generate "
                "a response right now."
            )

    except Exception as error:

        print(
            "Groq API error:",
            repr(error)
        )

        if (
            chat_object["messages"]
            and
            chat_object["messages"][-1]
            .get("role") == "user"
        ):

            chat_object["messages"].pop()

        return jsonify({

            "success": False,

            "error":
                "AI service is temporarily "
                "unavailable. Please try again."

        }), 500

    # Add AI response
    chat_object["messages"].append({

        "role": "assistant",

        "content": assistant_message

    })

    # Create title
    if chat_object["title"] == "New Chat":

        title = (
            user_message[:40]
            .strip()
        )

        if len(user_message) > 40:

            title += "..."

        if not title:

            title = "New Chat"

        chat_object["title"] = title

    chat_object["updated_at"] = (
        datetime.utcnow()
        .isoformat()
    )

    # Save chat
    save_chat(
        user_id,
        chat_object
    )

    update_chat_list(
        user_id,
        chat_object
    )

    return jsonify({

        "success": True,

        "reply": assistant_message,

        "chat_id":
            chat_object["id"],

        "title":
            chat_object["title"]

    })


# =========================
# HEALTH CHECK
# =========================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status": "ok",

        "groq":
            bool(GROQ_API_KEY),

        "redis":
            redis_is_available()

    })


# =========================
# LOCAL SERVER
# =========================

if __name__ == "__main__":

    print()
    print("=" * 45)
    print("              MY AI SERVER")
    print("=" * 45)

    print(
        "Groq configured:",
        bool(GROQ_API_KEY)
    )

    print(
        "Redis configured:",
        redis_is_available()
    )

    print(
        "Server: http://127.0.0.1:5000"
    )

    print("=" * 45)
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
