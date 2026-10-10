"""Cuanin - MVP platform ekonomi sirkular hiper-lokal & micro-affiliate.
Jalankan: pip install flask && python app.py  -> buka http://127.0.0.1:5000
Database: in-memory (dict/list), data hilang saat server restart."""
import math, os, re, itertools
from flask import Flask, jsonify, request, session, render_template

# File statis ada di public/static: Vercel menyajikannya dari CDN, dan Flask menyajikan folder yang sama saat lokal.
app = Flask(__name__, static_folder="public/static", static_url_path="/static")
# Di Vercel isi lewat Environment Variable SECRET_KEY (string acak panjang); nilai default hanya untuk lokal.
app.secret_key = os.environ.get("SECRET_KEY", "cuanin-dev-secret")

# ---------------- IN-MEMORY DATABASE ----------------
USERS = {  # saldo = dompet simulasi
    "p1": {"id": "p1", "name": "Warung Bu Siti", "role": "pelapak", "lat": -7.5666, "lng": 110.8167, "balance": 0},
    "p2": {"id": "p2", "name": "Keripik Pak Joko", "role": "pelapak", "lat": -7.5750, "lng": 110.8300, "balance": 0},
    "p3": {"id": "p3", "name": "Batik Jakarta (jauh)", "role": "pelapak", "lat": -6.2088, "lng": 106.8456, "balance": 0},
    "m1": {"id": "m1", "name": "Rina (Warga)", "role": "mitra", "balance": 0},
    "m2": {"id": "m2", "name": "Budi (Warga)", "role": "mitra", "balance": 0},
}
# Username & password mock (plain text, HANYA untuk demo; produksi wajib memakai hash)
for _u, _name in zip(USERS.values(), ["bu_siti", "pak_joko", "batik_jkt", "rina", "budi"]):
    _u["username"], _u["password"] = _name, "demo123"

PRODUCTS = {
    1: {"id": 1, "pelapak_id": "p1", "name": "Nasi Liwet Solo", "price": 25000, "commission": 5000},
    2: {"id": 2, "pelapak_id": "p2", "name": "Keripik Singkong Pedas", "price": 18000, "commission": 3000},
    3: {"id": 3, "pelapak_id": "p3", "name": "Kain Batik Tulis", "price": 350000, "commission": 50000},
}
TRANSACTIONS = []
_pid = itertools.count(4)
_tid = itertools.count(1)
_uid = itertools.count(100)
DEFAULT_RADIUS_KM = 5
DEFAULT_COORDS = (-7.5666, 110.8167)  # pusat Surakarta

# ---------------- HELPER ----------------
def haversine_km(lat1, lng1, lat2, lng2):
    """Jarak 2 koordinat (km) dengan rumus Haversine (lingkaran besar bumi)."""
    r = 6371
    dlat, dlng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def current_user():
    return USERS.get(session.get("user_id"))

def public_product(p, dist=None):
    seller = USERS[p["pelapak_id"]]
    d = {**p, "pelapak_name": seller["name"]}
    if dist is not None:
        d["distance_km"] = round(dist, 2)
    return d

def err(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

# ---------------- HALAMAN ----------------
@app.route("/")
@app.route("/buy/<int:product_id>")  # link afiliasi memakai SPA yang sama
def index(product_id=None):
    return render_template("index.html")

# ---------------- AUTH MOCK ----------------
@app.route("/api/accounts")
def accounts():
    """Akun demo (untuk tombol 'coba akun demo' di halaman login)."""
    return jsonify([{"username": u["username"], "name": u["name"], "role": u["role"]}
                    for u in list(USERS.values())[:5]])

@app.route("/api/register", methods=["POST"])
def register():
    d = request.get_json(force=True)
    name = str(d.get("name", "")).strip()
    username = str(d.get("username", "")).strip().lower()
    password, role = str(d.get("password", "")), d.get("role")
    if not name or role not in ("pelapak", "mitra"):
        return err("Nama dan peran wajib diisi.")
    if not re.fullmatch(r"[a-z0-9_]{3,20}", username):
        return err("Username 3-20 karakter: huruf kecil, angka, atau garis bawah.")
    if len(password) < 4:
        return err("Kata sandi minimal 4 karakter.")
    if any(u["username"] == username for u in USERS.values()):
        return err("Username sudah dipakai.", 409)
    uid = f"{role[0]}{next(_uid)}"
    user = {"id": uid, "name": name, "role": role, "username": username, "password": password, "balance": 0}
    if role == "pelapak":  # lokasi usaha dipakai untuk filter jarak katalog
        try:
            user["lat"], user["lng"] = float(d["lat"]), float(d["lng"])
        except (KeyError, ValueError, TypeError):
            user["lat"], user["lng"] = DEFAULT_COORDS
    USERS[uid] = user
    session["user_id"] = uid
    return jsonify({"ok": True})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(force=True)
    username = str(d.get("username", "")).strip().lower()
    user = next((u for u in USERS.values() if u["username"] == username), None)
    if not user or user["password"] != d.get("password"):
        return err("Username atau kata sandi salah.", 401)
    session["user_id"] = user["id"]
    return jsonify({"ok": True})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/me")
def me():
    u = current_user()
    if not u:
        return jsonify({"user": None})
    return jsonify({"user": {"id": u["id"], "name": u["name"], "role": u["role"], "balance": u["balance"]}})

# ---------------- PELAPAK ----------------
@app.route("/api/my-products", methods=["GET", "POST"])
def my_products():
    u = current_user()
    if not u or u["role"] != "pelapak":
        return err("Khusus Pelapak.", 403)
    if request.method == "POST":
        data = request.get_json(force=True)
        try:
            name = str(data["name"]).strip()
            price, commission = int(data["price"]), int(data["commission"])
        except (KeyError, ValueError, TypeError):
            return err("Data produk tidak valid.")
        if not name or price <= 0 or commission < 0 or commission >= price:
            return err("Nama wajib diisi, harga > 0, dan komisi harus lebih kecil dari harga.")
        pid = next(_pid)
        PRODUCTS[pid] = {"id": pid, "pelapak_id": u["id"], "name": name, "price": price, "commission": commission}
        return jsonify({"ok": True, "product": PRODUCTS[pid]})
    return jsonify([p for p in PRODUCTS.values() if p["pelapak_id"] == u["id"]])

@app.route("/api/my-products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    """Hapus produk milik Pelapak yang sedang login (tidak boleh menghapus milik orang lain)."""
    u = current_user()
    p = PRODUCTS.get(product_id)
    if not u or u["role"] != "pelapak":
        return err("Khusus Pelapak.", 403)
    if not p or p["pelapak_id"] != u["id"]:
        return err("Produk tidak ditemukan.", 404)
    del PRODUCTS[product_id]
    return jsonify({"ok": True})

# ---------------- MITRA ----------------
@app.route("/api/products")
def catalog():
    """Katalog hanya berisi produk Pelapak dalam radius (km) dari lokasi pengguna."""
    try:
        lat, lng = float(request.args["lat"]), float(request.args["lng"])
    except (KeyError, ValueError):
        return err("Parameter lat & lng wajib diisi.")
    radius = float(request.args.get("radius", DEFAULT_RADIUS_KM))
    result = []
    for p in PRODUCTS.values():
        s = USERS[p["pelapak_id"]]
        dist = haversine_km(lat, lng, s["lat"], s["lng"])
        if dist <= radius:  # filter jarak sederhana
            result.append(public_product(p, dist))
    result.sort(key=lambda x: x["distance_km"])
    return jsonify({"radius_km": radius, "products": result})

@app.route("/api/affiliate/<int:product_id>", methods=["POST"])
def affiliate(product_id):
    u = current_user()
    if not u or u["role"] != "mitra":
        return err("Khusus Mitra.", 403)
    if product_id not in PRODUCTS:
        return err("Produk tidak ditemukan.", 404)
    link = f"{request.host_url.rstrip('/')}/buy/{product_id}?ref={u['id']}"
    return jsonify({"ok": True, "link": link})

# ---------------- CHECKOUT & SPLIT PAYMENT ----------------
@app.route("/api/product/<int:product_id>")
def product_detail(product_id):
    p = PRODUCTS.get(product_id)
    if not p:
        return err("Produk tidak ditemukan.", 404)
    return jsonify(public_product(p))

@app.route("/api/checkout", methods=["POST"])
def checkout():
    data = request.get_json(force=True)
    p = PRODUCTS.get(int(data.get("product_id", 0)))
    if not p:
        return err("Produk tidak ditemukan.", 404)
    pelapak = USERS[p["pelapak_id"]]
    mitra = USERS.get(data.get("ref"))
    if mitra and mitra["role"] != "mitra":
        mitra = None

    # ===== SPLIT PAYMENT =====
    # Komisi hanya berlaku jika ada Mitra valid (ref). Tanpa ref, seluruh harga ke Pelapak.
    commission = p["commission"] if mitra else 0
    pelapak_share = p["price"] - commission  # Harga Jual - Komisi -> Pelapak
    pelapak["balance"] += pelapak_share
    if mitra:
        mitra["balance"] += commission       # Komisi -> Mitra
    # ==========================

    trx = {
        "id": f"TRX-{next(_tid):04d}", "product": p["name"], "total": p["price"],
        "split": {"pelapak": {"id": pelapak["id"], "name": pelapak["name"], "amount": pelapak_share},
                  "mitra": {"id": mitra["id"], "name": mitra["name"], "amount": commission} if mitra else None},
    }
    TRANSACTIONS.append(trx)  # catatan internal lengkap (berisi ID para pihak)

    # Bukti bayar untuk PEMBELI: nama lapak + nominal saja, identitas Mitra tidak dikirim ke browser.
    receipt = {
        "id": trx["id"], "product": p["name"], "total": p["price"],
        "pelapak": {"name": pelapak["name"], "amount": pelapak_share},
        "mitra": {"amount": commission} if mitra else None,
    }
    return jsonify({"ok": True, "receipt": receipt})

@app.route("/api/wallet")
def wallet():
    u = current_user()
    if not u:
        return err("Belum login.", 401)
    # Riwayat hanya berisi bagian milik pengguna sendiri; identitas pihak lain tidak dikirim.
    history = []
    for t in TRANSACTIONS[::-1]:
        sp = t["split"]
        if u["role"] == "pelapak" and sp["pelapak"]["id"] == u["id"]:
            history.append({"id": t["id"], "product": t["product"], "total": t["total"], "amount": sp["pelapak"]["amount"]})
        elif u["role"] == "mitra" and sp["mitra"] and sp["mitra"]["id"] == u["id"]:
            history.append({"id": t["id"], "product": t["product"], "total": t["total"], "amount": sp["mitra"]["amount"]})
    return jsonify({"balance": u["balance"], "transactions": history})

if __name__ == "__main__":
    app.run(debug=True)