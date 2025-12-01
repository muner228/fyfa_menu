from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import sqlite3, os
from PIL import Image, ImageDraw, ImageFont

"""
Flask application entry point for the backend API.

This version of the application is configured to live inside the ``backend``
folder of a split frontend/backend project structure.  It explicitly
specifies the location of the static assets and templates so that Flask
can still render the existing Jinja2 templates that now reside in
``../frontend/templates`` and serve uploaded files from
``backend/static/uploads``.  The database and upload directories are
computed relative to the location of this file to avoid dependence on
the current working directory.
"""

# Determine absolute paths for the various resources.  ``base_dir`` is the
# directory that contains this file (i.e. ``backend``).
base_dir = os.path.dirname(os.path.abspath(__file__))
# Static assets live in ``backend/static``.  These include the uploads
# directory.  Flask will serve files in this folder via ``url_for('static', ...)``.
static_dir = os.path.join(base_dir, "static")
# Templates now live in ``../frontend/templates`` relative to ``backend``.
template_dir = os.path.join(base_dir, "..", "frontend", "templates")

# Create the Flask application specifying explicit template and static
# directories.  Without these parameters Flask defaults to ``templates`` and
# ``static`` subfolders alongside this file, which no longer applies.
app = Flask(__name__, static_folder=static_dir, template_folder=template_dir)
app.secret_key = "viva_secret_key"

# Uploads are stored inside ``backend/static/uploads``.  Compute the
# absolute path and ensure the directory exists.  Expose this through
# ``app.config`` for use elsewhere in the code.
upload_folder = os.path.join(static_dir, "uploads")
os.makedirs(upload_folder, exist_ok=True)
app.config["UPLOAD_FOLDER"] = upload_folder

# Path to the SQLite database.  Keeping an absolute path avoids accidental
# creation of databases in unexpected working directories when the app is
# launched from outside ``backend``.
database_path = os.path.join(base_dir, "database.db")

# ========== 🧱 قاعدة البيانات ==========
def init_db():
    # Use the absolute ``database_path`` for SQLite connections.  Without this
    # change the default working directory could cause a new database to
    # appear in an unexpected location when running the app from another
    # directory.
    conn = sqlite3.connect(database_path)
    c = conn.cursor()
    # جدول المنتجات مع الفئة
    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    image TEXT,
                    available INTEGER DEFAULT 1,
                    category TEXT DEFAULT 'factory'
                )''')

    # جدول المستخدمين مع الدور
    c.execute('''CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    role TEXT DEFAULT 'factory'
                )''')

    # المستخدمين الافتراضيين
    users = [
        ('admin', '1234', 'admin'),
        ('factory', '1111', 'factory'),
        ('warehouse', '2222', 'warehouse'),
        ('purchases', '3333', 'purchases')
    ]
    for u in users:
        c.execute("INSERT OR IGNORE INTO admin (username, password, role) VALUES (?, ?, ?)", u)

    # إعدادات الشعار
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logo TEXT
                )''')
    c.execute("INSERT OR IGNORE INTO settings (id, logo) VALUES (1, NULL)")

    conn.commit()
    conn.close()

init_db()

# ========== 🖋️ دالة العلامة المائية ==========
def add_watermark(image_path):
    img = Image.open(image_path).convert("RGBA")
    watermark = Image.new("RGBA", img.size, (255,255,255,0))
    draw = ImageDraw.Draw(watermark)
    text = "غير متوفر"
    font_size = int(img.size[0] / 10)

    try:
        font = ImageFont.truetype("DG-Rafah-Bold.ttf", font_size)
    except:
        try:
            font = ImageFont.truetype("Tajawal-Bold.ttf", font_size)
        except:
            font = ImageFont.truetype("arial.ttf", font_size)

    text_width, text_height = draw.textsize(text, font=font)
    x = (img.size[0] - text_width) / 2
    y = (img.size[1] - text_height) / 2
    rotated = Image.new("RGBA", img.size, (255,255,255,0))
    temp_draw = ImageDraw.Draw(rotated)
    temp_draw.text((x, y), text, font=font, fill=(180, 0, 0, 90))
    rotated = rotated.rotate(25, expand=1)
    combined = Image.alpha_composite(img, rotated)
    combined = combined.convert("RGB")
    combined.save(image_path)

# ========== 🔐 تسجيل الدخول ==========
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect(database_path)
        c = conn.cursor()
        c.execute("SELECT username, role FROM admin WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = user[0]
            session["role"] = user[1]
            flash(f"مرحباً {user[0]} 👋", "info")
            return redirect("/dashboard")
        else:
            flash("اسم المستخدم أو كلمة المرور غير صحيحة ❌", "error")
    return render_template("login.html")

# ========== 🧭 لوحة التحكم ==========
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    conn = sqlite3.connect(database_path)
    c = conn.cursor()

    role = session["role"]

    # المدير يشاهد كل المنتجات
    if role == "admin":
        c.execute("SELECT * FROM products")
    else:
        c.execute("SELECT * FROM products WHERE category=?", (role,))
    products = c.fetchall()

    c.execute("SELECT logo FROM settings WHERE id=1")
    logo = c.fetchone()
    conn.close()

    return render_template("dashboard.html", products=products, logo=logo[0] if logo else None, role=role)

# ========== ➕ إضافة منتج ==========
@app.route("/add", methods=["POST"])
def add_product():
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    name = request.form["name"]
    available = 1 if request.form.get("available") == "on" else 0
    category = request.form["category"] if role == "admin" else role
    image_file = request.files["image"]

    image_filename = None
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(image_path)
        if not available:
            add_watermark(image_path)
        image_filename = filename

    conn = sqlite3.connect(database_path)
    c = conn.cursor()
    c.execute("INSERT INTO products (name, image, available, category) VALUES (?, ?, ?, ?)",
              (name, image_filename, available, category))
    conn.commit()
    conn.close()

    flash("✅ تمت إضافة المنتج بنجاح")
    return redirect("/dashboard")

# ========== ✏️ تعديل منتج ==========
@app.route("/edit/<int:id>", methods=["POST"])
def edit_product(id):
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    name = request.form["name"]
    available = 1 if request.form.get("available") == "on" else 0
    image_file = request.files["image"]

    conn = sqlite3.connect(database_path)
    c = conn.cursor()

    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        image_file.save(image_path)
        if not available:
            add_watermark(image_path)
        c.execute("UPDATE products SET name=?, image=?, available=? WHERE id=? AND (category=? OR ?='admin')",
                  (name, filename, available, id, role, role))
    else:
        c.execute("UPDATE products SET name=?, available=? WHERE id=? AND (category=? OR ?='admin')",
                  (name, available, id, role, role))

    conn.commit()
    conn.close()
    flash("تم تعديل المنتج ✅")
    return redirect("/dashboard")

# ========== 🗑️ حذف منتج ==========
@app.route("/delete/<int:id>")
def delete_product(id):
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    conn = sqlite3.connect(database_path)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=? AND (category=? OR ?='admin')", (id, role, role))
    conn.commit()
    conn.close()
    flash("تم حذف المنتج 🗑️")
    return redirect("/dashboard")

# ========== 🖼️ رفع شعار المتجر ==========
@app.route("/upload_logo", methods=["POST"])
def upload_logo():
    if "user" not in session or session["role"] != "admin":

        flash("❌ ليس لديك صلاحية لرفع الشعار")
        return redirect("/dashboard")

    logo_file = request.files["logo"]
    if logo_file and logo_file.filename:
        filename = secure_filename(logo_file.filename)
        logo_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        logo_file.save(logo_path)

        conn = sqlite3.connect(database_path)
        c = conn.cursor()
        c.execute("UPDATE settings SET logo=? WHERE id=1", (filename,))
        conn.commit()
        conn.close()

        flash("تم رفع شعار المتجر بنجاح ✅")

    return redirect("/dashboard")

# ========== 🚪 تسجيل خروج ==========
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ========== 🍽️ صفحة المنيو العامة ==========
@app.route("/menu")
def menu():
    category = request.args.get("category")
    conn = sqlite3.connect(database_path)
    c = conn.cursor()

    if category:
        c.execute("SELECT * FROM products WHERE category=?", (category,))
    else:
        c.execute("SELECT * FROM products")
    products = c.fetchall()

    c.execute("SELECT logo FROM settings WHERE id=1")
    logo = c.fetchone()
    conn.close()

    return render_template("menu.html", products=products, logo=logo[0] if logo else None, category=category)

# ========== 🚀 تشغيل السيرفر ==========
if __name__ == "__main__":
    app.run(debug=True)
