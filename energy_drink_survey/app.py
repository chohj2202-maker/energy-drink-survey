import os
import io
import sqlite3
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, send_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_DATABASE = "survey.db"

QUESTIONS = [
    {
        "id": "q1",
        "title": "시험 기간에 에너지 음료(핫식스, 몬스터 등)를 얼마나 자주 마시나요?",
        "options": ["마시지 않는다", "시험 기간 중 1~2회", "이틀에 1캔 정도", "매일 1캔 이상"],
    },
    {
        "id": "q2",
        "title": "시험 기간에 에너지 음료를 마시는 가장 주된 이유는 무엇인가요?",
        "options": ["잠을 깨고 밤샘 공부를 하기 위해", "집중력을 높이기 위해", "친구들이 마시니까 따라서", "맛이 있어서/단순 음료용"],
    },
    {
        "id": "q3",
        "title": "시험 기간에 가장 자주 마시는 에너지 음료의 종류(브랜드)는 무엇인가요?",
        "options": ["몬스터 에너지 시리즈", "핫식스 (오리지널/더킹 등)", "레드불", "박카스 (F/D 등)", "기타 (비타500, 이온 음료, 커피류 등)"],
    },
]

def using_postgres():
    return bool(DATABASE_URL)

def get_db():
    if using_postgres():
        import psycopg
        return psycopg.connect(DATABASE_URL)
    conn = sqlite3.connect(SQLITE_DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            q1 INTEGER NOT NULL,
            q2 INTEGER NOT NULL,
            q3 INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def fetch_rows():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT q1, q2, q3 FROM responses")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def row_value(row, index):
    # SQLite Row supports both names and indexes; PostgreSQL returns tuples.
    return row[index]

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)
    return wrapper

@app.route("/")
def survey():
    return render_template("survey.html", questions=QUESTIONS)

@app.route("/submit", methods=["POST"])
def submit():
    answers = []
    for q in QUESTIONS:
        value = request.form.get(q["id"])
        if value is None:
            return render_template("survey.html", questions=QUESTIONS, error="모든 문항에 답해주세요.")
        try:
            value = int(value)
        except ValueError:
            return render_template("survey.html", questions=QUESTIONS, error="잘못된 응답입니다.")
        if value < 1 or value > len(q["options"]):
            return render_template("survey.html", questions=QUESTIONS, error="잘못된 응답입니다.")
        answers.append(value)

    conn = get_db()
    cur = conn.cursor()
    placeholder = "%s" if using_postgres() else "?"
    cur.execute(
        f"INSERT INTO responses (q1, q2, q3) VALUES ({placeholder}, {placeholder}, {placeholder})",
        answers
    )
    conn.commit()
    cur.close()
    conn.close()
    return render_template("thanks.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "비밀번호가 맞지 않습니다."
    return render_template("login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("survey"))

@app.route("/admin")
@admin_required
def admin():
    rows = fetch_rows()
    total = len(rows)
    results = []

    for q_index, q in enumerate(QUESTIONS):
        counts = []
        for option_index, option in enumerate(q["options"], start=1):
            count = sum(row_value(row, q_index) == option_index for row in rows)
            percent = round(count / total * 100, 1) if total else 0
            counts.append({"label": option, "count": count, "percent": percent})
        results.append({"title": q["title"], "items": counts})

    return render_template("admin.html", total=total, results=results)

@app.route("/admin/delete_all", methods=["POST"])
@admin_required
def delete_all():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM responses")
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/qr")
def qr():
    try:
        import qrcode
    except ImportError:
        return "QR 기능을 사용하려면 qrcode 패키지가 필요합니다.", 500

    public_url = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")
    survey_url = public_url or url_for("survey", _external=True)

    img = qrcode.make(survey_url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
