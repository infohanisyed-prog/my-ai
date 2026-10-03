import os
import json
import uuid
from datetime import datetime

import requests

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session
)

from groq import Groq


# =========================================================
# APP SETUP
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path="/static"
)


# =========================================================
# SECRET KEY
# =========================================================

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "change-this-secret-key"
)


# =========================================================
# API KEYS
# =========================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

UPSTASH_REDIS_REST_URL = os.getenv(
    "UPSTASH_REDIS_REST_URL"
)

UPSTASH_REDIS_REST_TOKEN = os.getenv(
    "UPSTASH_REDIS_REST_TOKEN"
)


# =========================================================
# GROQ CLIENT
# =========================================================

if not GROQ_API_KEY:

    print(
        "WARNING: GROQ_API_KEY is not set."
    )

    groq_client = None

else:

    groq_client = Groq(
        api_key=GROQ_API_KEY
    )


# =========================================================
# GROQ MODEL
# =========================================================

MODEL_NAME = "openai/gpt-oss-120b"


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
You are Hani AI, a friendly and helpful AI assistant.

Important rules:

1. Understand the user's language automatically.

2. Reply in the same language the user uses.

3. If the user writes in Urdu script, reply in Urdu script.

4. If the user writes in Roman Urdu, reply in Roman Urdu.

5. If the user writes in English, reply in English.

6. If the user asks in another language, try to reply in that language.

7. Do not unnecessarily switch languages.

8. For educational questions, explain step by step in simple language.

9. If the user asks for programming help, provide correct,
   complete and easy-to-understand code.

10. Keep responses natural and friendly.

11. Use headings, bullet points and examples when they make
    the answer easier to understand.

12. Do not claim to remember information that is not present
    in the current conversation history.

13. If the user asks for Roman Urdu, do not use Urdu/Arabic
    script unless they specifically request it.

14. If the user asks for Urdu, use proper Urdu script.

15. For simple questions, do not make the response
    unnecessarily long.
"""


# =========================================================
# REDIS HELPERS
# =========================================================

def redis_headers():
    """
    Headers used for Upstash Redis REST API.
    """

    return {
        "Authorization":
            f"Bearer {UPSTASH_REDIS_REST_TOKEN}",

        "Content-Type":
            "application/json"
    }


def redis_available():
    """
    Check whether Redis environment variables
    are available.
    """

    return bool(
        UPSTASH_REDIS_REST_URL
        and
        UPSTASH_REDIS_REST_TOKEN
    )


def redis_command(
    command
):
    """
    Send a command to Upstash Redis.

    command should be a list, for example:
    ["GET", "some-key"]
    """

    if not redis_available():
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

    except Exception as error:

        print(
            "Redis error:",
            error
        )

        return None


# =========================================================
# USER ID
# =========================================================

def get_user_id():

    if "user_id" not in session:

        session["user_id"] = str(
            uuid.uuid4()
        )

    return session["user_id"]


# =========================================================
# REDIS KEY HELPERS
# =========================================================

def user_chats_key(
    user_id
):

    return (
        f"hani:user:{user_id}:chats"
    )


def chat_key(
    user_id,
    chat_id
):

    return (
        f"hani:user:{user_id}:chat:{chat_id}"
    )


# =========================================================
# GET USER CHAT LIST
# =========================================================

def get_user_chats(
    user_id
):

    result = redis_command(
        [
            "GET",
            user_chats_key(
                user_id
            )
        ]
    )


    if not result:
        return []


    try:

        chats = json.loads(
            result
        )

        if isinstance(
            chats,
            list
        ):

            return chats

    except Exception:
        pass


    return []


# =========================================================
# SAVE USER CHAT LIST
# =========================================================

def save_user_chats(
    user_id,
    chats
):

    redis_command(
        [
            "SET",

            user_chats_key(
                user_id
            ),

            json.dumps(
                chats,
                ensure_ascii=False
            )
        ]
    )


# =========================================================
# GET CHAT
# =========================================================

def get_chat(
    user_id,
    chat_id
):

    result = redis_command(
        [
            "GET",

            chat_key(
                user_id,
                chat_id
            )
        ]
    )


    if not result:
        return None


    try:

        return json.loads(
            result
        )

    except Exception:

        return None


# =========================================================
# SAVE CHAT
# =========================================================

def save_chat(
    user_id,
    chat
):

    redis_command(
        [
            "SET",

            chat_key(
                user_id,
                chat["id"]
            ),

            json.dumps(
                chat,
                ensure_ascii=False
            )
        ]
    )


# =========================================================
# DELETE CHAT
# =========================================================

def delete_chat_from_redis(
    user_id,
    chat_id
):

    redis_command(
        [
            "DEL",

            chat_key(
                user_id,
                chat_id
            )
        ]
    )


# =========================================================
# CREATE NEW CHAT OBJECT
# =========================================================

def create_chat_object():

    now = datetime.utcnow().isoformat()

    return {
        "id": str(
            uuid.uuid4()
        ),

        "title": "New Chat",

        "created_at": now,

        "updated_at": now,

        "messages": []
    }


# =========================================================
# UPDATE CHAT LIST
# =========================================================

def update_chat_list(
    user_id,
    chat
):

    chats = get_user_chats(
        user_id
    )


    found = False


    for item in chats:

        if item["id"] == chat["id"]:

            item["title"] = \
                chat["title"]

            item["updated_at"] = \
                chat["updated_at"]

            found = True

            break


    if not found:

        chats.append({

            "id":
                chat["id"],

            "title":
                chat["title"],

            "created_at":
                chat["created_at"],

            "updated_at":
                chat["updated_at"]

        })


    /*
       Newest chats first.
    */

    chats.sort(
        key=lambda item:
            item.get(
                "updated_at",
                ""
            ),
        reverse=True
    )


    save_user_chats(
        user_id,
        chats
    )


# =========================================================
# REMOVE CHAT FROM CHAT LIST
# =========================================================

def remove_chat_from_list(
    user_id,
    chat_id
):

    chats = get_user_chats(
        user_id
    )


    chats = [

        chat

        for chat in chats

        if chat["id"] != chat_id

    ]


    save_user_chats(
        user_id,
        chats
    )


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# GET ALL CHATS
# =========================================================

@app.route(
    "/api/chats",
    methods=["GET"]
)
def get_chats():

    user_id =
        get_user_id()

    chats =
        get_user_chats(
            user_id
        )


    chats.sort(
        key=lambda item:
            item.get(
                "updated_at",
                ""
            ),
        reverse=True
    )


    return jsonify({

        "success": True,

        "chats": chats

    })


# =========================================================
# CREATE CHAT
# =========================================================

@app.route(
    "/api/chats",
    methods=["POST"]
)
def create_chat():

    user_id =
        get_user_id()


    chat =
        create_chat_object()


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


# =========================================================
# DELETE ALL CHATS
# =========================================================

@app.route(
    "/api/chats",
    methods=["DELETE"]
)
def delete_all_chats():

    user_id =
        get_user_id()


    chats =
        get_user_chats(
            user_id
        )


    for chat in chats:

        delete_chat_from_redis(
            user_id,
            chat["id"]
        )


    save_user_chats(
        user_id,
        []
    )


    return jsonify({

        "success": True

    })


# =========================================================
# GET SINGLE CHAT
# =========================================================

@app.route(
    "/api/chats/<chat_id>",
    methods=["GET"]
)
def get_single_chat(
    chat_id
):

    user_id =
        get_user_id()


    chat =
        get_chat(
            user_id,
            chat_id
        )


    if not chat:

        return jsonify({

            "success": False,

            "error":
                "Chat not found."

        }), 404


    return jsonify({

        "success": True,

        "chat": chat

    })


# =========================================================
# DELETE SINGLE CHAT
# =========================================================

@app.route(
    "/api/chats/<chat_id>",
    methods=["DELETE"]
)
def delete_single_chat(
    chat_id
):

    user_id =
        get_user_id()


    chat =
        get_chat(
            user_id,
            chat_id
        )


    if not chat:

        return jsonify({

            "success": False,

            "error":
                "Chat not found."

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


# =========================================================
# CHAT WITH AI
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
def chat():

    user_id =
        get_user_id()


    data =
        request.get_json(
            silent=True
        )


    if not data:

        return jsonify({

            "success": False,

            "error":
                "Invalid request."

        }), 400


    user_message =
        str(
            data.get(
                "message",
                ""
            )
        ).strip()


    chat_id =
        data.get(
            "chat_id"
        )


    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if not user_message:

        return jsonify({

            "success": False,

            "error":
                "Message cannot be empty."

        }), 400


    if len(user_message) > 10000:

        return jsonify({

            "success": False,

            "error":
                "Message is too long."

        }), 400


    # -----------------------------------------------------
    # CHECK GROQ
    # -----------------------------------------------------

    if groq_client is None:

        return jsonify({

            "success": False,

            "error":
                "GROQ_API_KEY is not configured."

        }), 500


    # -----------------------------------------------------
    # GET OR CREATE CHAT
    # -----------------------------------------------------

    chat_object = None


    if chat_id:

        chat_object =
            get_chat(
                user_id,
                chat_id
            )


    if not chat_object:

        chat_object =
            create_chat_object()


    # -----------------------------------------------------
    # ADD USER MESSAGE
    # -----------------------------------------------------

    chat_object[
        "messages"
    ].append({

        "role":
            "user",

        "content":
            user_message

    })


    # -----------------------------------------------------
    # PREPARE RECENT MESSAGES
    # -----------------------------------------------------

    recent_messages =
        chat_object[
            "messages"
        ][-30:]


    groq_messages = [

        {
            "role":
                "system",

            "content":
                SYSTEM_PROMPT
        }

    ]


    for message in recent_messages:

        role =
            message.get(
                "role"
            )


        content =
            message.get(
                "content",
                ""
            )


        if role not in [
            "user",
            "assistant"
        ]:

            continue


        groq_messages.append({

            "role":
                role,

            "content":
                content

        })


    # -----------------------------------------------------
    # CALL GROQ
    # -----------------------------------------------------

    try:

        completion =
            groq_client.chat.completions.create(

                model=
                    MODEL_NAME,

                messages=
                    groq_messages,

                max_tokens=
                    2000,

                temperature=
                    0.7

            )


        assistant_message =
            completion.choices[
                0
            ].message.content


        if not assistant_message:

            assistant_message =
                "Sorry, I couldn't generate a response."

    except Exception as error:

        print(
            "Groq error:",
            error
        )


        # Remove the user message if
        # the AI request failed.

        if chat_object[
            "messages"
        ]:

            last_message =
                chat_object[
                    "messages"
                ][-1]


            if (
                last_message.get(
                    "role"
                )
                == "user"
            ):

                chat_object[
                    "messages"
                ].pop()


        return jsonify({

            "success": False,

            "error":
                "AI service is temporarily unavailable. Please try again."

        }), 500


    # -----------------------------------------------------
    # ADD AI RESPONSE
    # -----------------------------------------------------

    chat_object[
        "messages"
    ].append({

        "role":
            "assistant",

        "content":
            assistant_message

    })


    # -----------------------------------------------------
    # UPDATE TITLE
    # -----------------------------------------------------

    if chat_object[
        "title"
    ] == "New Chat":

        title =
            user_message[
                :40
            ].strip()


        if len(user_message) > 40:

            title += "..."


        chat_object[
            "title"
        ] = title


    # -----------------------------------------------------
    # UPDATE TIME
    # -----------------------------------------------------

    chat_object[
        "updated_at"
    ] = datetime.utcnow().isoformat()


    # -----------------------------------------------------
    # SAVE CHAT
    # -----------------------------------------------------

    save_chat(
        user_id,
        chat_object
    )


    update_chat_list(
        user_id,
        chat_object
    )


    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return jsonify({

        "success":
            True,

        "reply":
            assistant_message,

        "chat_id":
            chat_object["id"],

        "title":
            chat_object["title"]

    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "status":
            "ok",

        "groq":
            bool(GROQ_API_KEY),

        "redis":
            redis_available()

    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return jsonify({

        "success": False,

        "error":
            "Page not found."

    }), 404


@app.errorhandler(500)
def internal_server_error(error):

    return jsonify({

        "success": False,

        "error":
            "Internal server error."

    }), 500


# =========================================================
# RUN SERVER
# =========================================================

if __name__ == "__main__":

    print(
        "\n========================================"
    )

    print(
        "        HANI AI SERVER"
    )

    print(
        "========================================"
    )

    print(
        f"Groq configured: "
        f"{bool(GROQ_API_KEY)}"
    )

    print(
        f"Redis configured: "
        f"{redis_available()}"
    )

    print(
        "Server: http://127.0.0.1:5000"
    )

    print(
        "========================================\n"
    )


    app.run(
        host="0.0.0.0",

        port=5000,

        debug=True
    )
