// Cuanin - Vanilla JS: fetch async/await + Geolocation API
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rupiah = (n) => "Rp " + Number(n).toLocaleString("id-ID");
const DEFAULT_COORDS = { lat: -7.5666, lng: 110.8167 }; // fallback: pusat Surakarta
let role = null; // peran pengguna yang sedang login

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Terjadi kesalahan.");
  return data;
}

function toast(msg, isError = false) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 3000);
}

// ---------- DARK MODE ----------
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $("themeBtn").textContent = theme === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem("cuanin-theme", theme); } catch (e) {}
}
$("themeBtn").addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
applyTheme(document.documentElement.dataset.theme || "light");

// ---------- NAVIGASI ----------
const VIEWS = ["landing", "login", "register", "pelapak", "mitra", "checkout"];
function show(view) {
  VIEWS.forEach((v) => ($("view-" + v).hidden = v !== view));
  window.scrollTo(0, 0);
}
document.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => {
  show(b.dataset.go);
  if (b.dataset.go === "login") loadDemoAccounts();
}));

// ---------- LOGIN ----------
async function loadDemoAccounts() {
  const list = await api("/api/accounts");
  $("demoChips").innerHTML = list.map((a) =>
    `<button type="button" class="chip-btn" data-user="${esc(a.username)}">${esc(a.name)}</button>`).join("");
}
$("demoChips").addEventListener("click", async (e) => {
  const username = e.target.dataset.user;
  if (username) await doLogin(username, "demo123");
});
async function doLogin(username, password) {
  try {
    await api("/api/login", { method: "POST", body: { username, password } });
    await init();
  } catch (err) { toast(err.message, true); }
}
$("loginForm").addEventListener("submit", (e) => {
  e.preventDefault();
  doLogin(e.target.username.value, e.target.password.value);
});
$("logoutBtn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  location.href = "/";
});

// ---------- REGISTER ----------
let regRole = "pelapak";
document.querySelectorAll("#regSeg .seg-btn").forEach((b) => b.addEventListener("click", () => {
  regRole = b.dataset.role;
  document.querySelectorAll("#regSeg .seg-btn").forEach((x) => x.classList.toggle("active", x === b));
  $("regHint").hidden = regRole !== "pelapak"; // lokasi hanya relevan untuk Pelapak
}));
$("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = { name: f.name.value, username: f.username.value, password: f.password.value, role: regRole };
  try {
    if (regRole === "pelapak") { const loc = await getLocation(); body.lat = loc.lat; body.lng = loc.lng; }
    await api("/api/register", { method: "POST", body });
    toast("Akun berhasil dibuat");
    await init();
  } catch (err) { toast(err.message, true); }
});

// ---------- GEOLOCATION ----------
function getLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve({ ...DEFAULT_COORDS, fallback: true });
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude, fallback: false }),
      () => resolve({ ...DEFAULT_COORDS, fallback: true }), // izin ditolak -> lokasi contoh
      { timeout: 8000 }
    );
  });
}

// ---------- PELAPAK ----------
async function loadPelapak() {
  const products = await api("/api/my-products");
  $("statProducts").textContent = products.length;
  $("productTable").innerHTML = products.length
    ? products.map((p) => `<tr><td data-label="Nama" class="name">${esc(p.name)}</td><td data-label="Harga">${rupiah(p.price)}</td><td data-label="Komisi">${rupiah(p.commission)}</td><td data-label="Diterima">${rupiah(p.price - p.commission)}</td>
        <td class="act"><button class="btn danger sm" data-del="${p.id}" data-name="${esc(p.name)}">Hapus</button></td></tr>`).join("")
    : `<tr class="empty-row"><td colspan="5" class="muted">Belum ada produk. Tambahkan produk pertama Anda.</td></tr>`;
  await loadWallet("pelapakTrx");
}

$("productForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api("/api/my-products", { method: "POST", body: { name: f.name.value, price: f.price.value, commission: f.commission.value } });
    f.reset();
    toast("Produk disimpan");
    await loadPelapak();
  } catch (err) { toast(err.message, true); }
});

// Hapus produk (event delegation pada tabel)
$("productTable").addEventListener("click", async (e) => {
  const id = e.target.dataset.del;
  if (!id || !confirm(`Hapus produk "${e.target.dataset.name}"? Link afiliasinya juga tidak akan berfungsi lagi.`)) return;
  try {
    await api(`/api/my-products/${id}`, { method: "DELETE" });
    toast("Produk dihapus");
    await loadPelapak();
  } catch (err) { toast(err.message, true); }
});

// ---------- MITRA ----------
async function loadCatalog() {
  $("geoStatus").textContent = "Mencari lokasi...";
  $("catalog").innerHTML = '<div class="skeleton"></div>'.repeat(3);
  const loc = await getLocation();
  // Koordinat dikirim ke Flask; filter jarak (Haversine) dijalankan di Python
  const data = await api(`/api/products?lat=${loc.lat}&lng=${loc.lng}&radius=5`);
  $("geoStatus").textContent = (loc.fallback ? "Lokasi tidak tersedia, memakai lokasi contoh (Surakarta). " : "Lokasi terdeteksi. ")
    + `Menampilkan produk dalam radius ${data.radius_km} km.`;
  $("catalog").innerHTML = data.products.length
    ? data.products.map((p) => `
      <article class="card product">
        <div class="product-top">
          <div class="thumb">${esc(p.name[0].toUpperCase())}</div>
          <div><h3>${esc(p.name)}</h3><div class="meta">${esc(p.pelapak_name)}</div></div>
        </div>
        <div class="price-sm">${rupiah(p.price)}</div>
        <div class="chips"><span class="chip">${p.distance_km} km</span><span class="chip green">Komisi ${rupiah(p.commission)}</span></div>
        <button class="btn" data-id="${p.id}">Bantu jual</button>
        <div class="linkbox" id="link-${p.id}" hidden></div>
      </article>`).join("")
    : `<p class="empty">Belum ada produk dalam radius ini.</p>`;
  await loadWallet("mitraTrx");
}

$("catalog").addEventListener("click", async (e) => {
  const id = e.target.dataset.id;
  if (!id) return;
  try {
    const { link } = await api(`/api/affiliate/${id}`, { method: "POST" });
    const box = $("link-" + id);
    box.hidden = false;
    box.textContent = link;
    try { await navigator.clipboard.writeText(link); toast("Link disalin"); } catch { toast("Link siap dibagikan"); }
  } catch (err) { toast(err.message, true); }
});
$("refreshGeo").addEventListener("click", loadCatalog);

// ---------- RIWAYAT / SALDO ----------
async function loadWallet(listId) {
  const w = await api("/api/wallet");
  const isP = role === "pelapak";
  $(isP ? "statBalance" : "mStatBalance").textContent = rupiah(w.balance);
  $(isP ? "statSales" : "mStatSales").textContent = w.transactions.length;
  $(listId).innerHTML = w.transactions.length
    ? w.transactions.map((t) => {
        return `<li><span>${t.id} - ${esc(t.product)}</span><strong>+ ${rupiah(t.amount)}</strong></li>`;
      }).join("")
    : `<li class="muted">Belum ada transaksi.</li>`;
}

// ---------- CHECKOUT ----------
async function initCheckout(productId) {
  show("checkout");
  const ref = new URLSearchParams(location.search).get("ref");
  try {
    const p = await api(`/api/product/${productId}`);
    $("coSeller").textContent = "Dijual oleh " + p.pelapak_name;
    $("coName").textContent = p.name;
    $("coPrice").textContent = rupiah(p.price);
  } catch (e) { $("coName").textContent = "Produk tidak ditemukan"; $("coSeller").hidden = true; $("payBtn").hidden = true; return; }

  $("payBtn").addEventListener("click", async () => {
    $("payBtn").disabled = true;
    try {
      const { receipt } = await api("/api/checkout", { method: "POST", body: { product_id: productId, ref } });
      $("receipt").hidden = false;
      $("receipt").innerHTML = `
        <p class="ok">Pembayaran berhasil - ${receipt.id}</p>
        <div class="line"><span>Ke ${esc(receipt.pelapak.name)} (Pelapak)</span><span>${rupiah(receipt.pelapak.amount)}</span></div>
        <div class="line"><span>${receipt.mitra ? "Ke Mitra warga" : "Tanpa Mitra"}</span><span>${rupiah(receipt.mitra ? receipt.mitra.amount : 0)}</span></div>
        <div class="line total"><span>Total dibayar</span><span>${rupiah(receipt.total)}</span></div>`;
    } catch (e) { toast(e.message, true); $("payBtn").disabled = false; }
  });
}

// ---------- INIT ----------
async function init() {
  const match = location.pathname.match(/^\/buy\/(\d+)/);
  if (match) return initCheckout(Number(match[1]));

  const { user } = await api("/api/me");
  $("navAuth").hidden = !!user;
  $("userbox").hidden = !user;
  if (!user) return show("landing"); // pengunjung baru: landing page dengan tombol Daftar & Masuk

  role = user.role;
  $("userName").textContent = user.name;
  $("userAvatar").textContent = user.name[0].toUpperCase();
  if (role === "pelapak") { show("pelapak"); await loadPelapak(); }
  else { show("mitra"); await loadCatalog(); }
}
init();