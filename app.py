from flask import Flask, render_template, request, jsonify
from groq import Groq
import os

# =========================================================
# PROJECT PATH
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# =========================================================
# FLASK APP
# =========================================================

app = Flask(
    __name__,
    template_folder=BASE_DIR,
    static_folder=BASE_DIR,
    static_url_path="/static"
)

# =========================================================
# GROQ API
# =========================================================

API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError("GROQ_API_KEY is not set.")

client = Groq(api_key=API_KEY)

# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# CHAT
# =========================================================

@app.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json(silent=True) or {}

        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({
                "reply": "Please enter a message."
            }), 400

        response = client.chat.completions.create(

            model="openai/gpt-oss-120b",

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Hani's helpful AI assistant. "
                        "Be friendly, clear, concise, and helpful. "
                        "Use simple explanations when appropriate."
                    )
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        reply = response.choices[0].message.content

        return jsonify({
            "reply": reply
        })

    except Exception as e:

        print("Chat error:", str(e))

        return jsonify({
            "reply": "Sorry, something went wrong. Please try again."
        }), 500


# =========================================================
# RUN LOCALLY
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
