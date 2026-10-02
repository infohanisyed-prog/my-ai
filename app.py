from flask import Flask, render_template, request, jsonify
from groq import Groq
import os

app = Flask(__name__)

API_KEY = os.getenv("GROQ_API_KEY")

if not API_KEY:
    raise ValueError("GROQ_API_KEY is not set.")

client = Groq(api_key=API_KEY)

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are Hani's helpful AI assistant. "
        "Be friendly, clear, concise, and helpful. "
        "Use simple explanations when the user asks beginner questions."
    )
}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get("message", "").strip()
        history = data.get("history", [])

        if not user_message:
            return jsonify({"reply": "Please enter a message."}), 400

        # Keep only valid chat messages and limit the amount sent to the model.
        safe_history = []
        for item in history[-20:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                safe_history.append({
                    "role": role,
                    "content": content[:8000]
                })

        messages = [SYSTEM_MESSAGE] + safe_history
        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
        )

        reply = response.choices[0].message.content or "I couldn't generate a response."
        return jsonify({"reply": reply})

    except Exception as e:
        print("Chat error:", e)
        return jsonify({
            "reply": "Sorry, something went wrong. Please try again."
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
