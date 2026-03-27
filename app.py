"""
app.py — Render.com Web Sunucusu
─────────────────────────────────
• Flask ile sunum.html ve sunum_assets/ klasörünü serve eder
• APScheduler ile her gece saat 04:00 (İstanbul) Drive'ı kontrol eder
• Değişiklik varsa HTML'yi baştan üretir
• Uygulama ilk başladığında sunum.html yoksa otomatik üretir
"""

import os
import sys
import threading
import logging
from pathlib import Path
from datetime import datetime

from flask import Flask, send_file, send_from_directory, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

# ─────────────────────────────────────────────
# Logging ayarı
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Flask uygulaması
# ─────────────────────────────────────────────
app = Flask(__name__)

OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "sunum.html")
ASSETS_DIR  = os.environ.get("ASSETS_DIR", "sunum_assets")

# Üretim kilidi: aynı anda iki üretim başlamaması için
_build_lock = threading.Lock()
_build_status = {"running": False, "last_run": None, "last_result": "Henüz çalışmadı"}


# ─────────────────────────────────────────────
# HTML üretim fonksiyonu
# ─────────────────────────────────────────────
def run_build(force: bool = False):
    """
    drive_to_html.py'deki main() fonksiyonunu çağırır.
    force=True → manifest farkı olmasa bile yeniden üretir.
    Döndürür: True (üretildi) | False (değişiklik yok, atlandı)
    """
    global _build_status

    if _build_lock.locked():
        log.warning("⚠  Zaten bir üretim süreci çalışıyor, bu çalıştırma atlandı.")
        return False

    with _build_lock:
        _build_status["running"] = True
        _build_status["last_run"] = datetime.now().isoformat()
        try:
            log.info("🔄 Drive kontrolü başlatılıyor…")

            # drive_to_html.py'deki get_service ve list_files kullan
            import drive_to_html as dth

            service = dth.get_service()
            files   = dth.list_files(service, dth.FOLDER_ID)

            current_hash  = dth.compute_manifest(files)
            previous_hash = dth.load_manifest()

            if not force and current_hash == previous_hash and Path(OUTPUT_FILE).exists():
                log.info("✅ Drive'da değişiklik yok, HTML yeniden üretilmedi.")
                _build_status["last_result"] = "Değişiklik yok"
                return False

            log.info(f"🔨 Değişiklik algılandı (ya da force=True), HTML üretiliyor…")
            dth.main()
            log.info(f"✅ {OUTPUT_FILE} başarıyla üretildi.")
            _build_status["last_result"] = "Başarılı"
            return True

        except Exception as e:
            log.error(f"❌ Üretim hatası: {e}", exc_info=True)
            _build_status["last_result"] = f"Hata: {e}"
            return False
        finally:
            _build_status["running"] = False


def nightly_check():
    """Gece 04:00'te çalışan zamanlayıcı görevi."""
    log.info("🕓 Gece 04:00 kontrolü başlıyor…")
    run_build(force=False)


# ─────────────────────────────────────────────
# Flask Routes
# ─────────────────────────────────────────────
@app.route("/")
def index():
    """Ana sayfa: sunum.html'i serve et."""
    html_path = Path(OUTPUT_FILE)
    if not html_path.exists():
        # HTML henüz üretilmemişse: yükleniyor sayfası göster
        return (
            """<!DOCTYPE html><html lang="tr"><head><meta charset="UTF-8">
            <meta http-equiv="refresh" content="15">
            <title>Yükleniyor…</title>
            <style>
              body{background:#020209;color:#C8A55A;font-family:sans-serif;
                   display:flex;align-items:center;justify-content:center;
                   min-height:100vh;flex-direction:column;gap:24px}
              .spinner{width:40px;height:40px;border:3px solid #1A1A2E;
                       border-top-color:#C8A55A;border-radius:50%;
                       animation:spin 1s linear infinite}
              @keyframes spin{to{transform:rotate(360deg)}}
            </style></head><body>
            <div class="spinner"></div>
            <p>Sunum hazırlanıyor, lütfen bekleyin…</p>
            <p style="font-size:12px;color:#6A677A">Sayfa 15 saniyede yenilenir</p>
            </body></html>""",
            202,
        )
    return send_file(OUTPUT_FILE)


@app.route(f"/{ASSETS_DIR}/<path:filename>")
def assets(filename):
    """sunum_assets/ klasöründeki görselleri, PDF'leri ve videoları serve et."""
    return send_from_directory(ASSETS_DIR, filename)


@app.route("/status")
def status():
    """Sistem durumu endpoint'i (monitoring için)."""
    html_exists = Path(OUTPUT_FILE).exists()
    html_size   = Path(OUTPUT_FILE).stat().st_size // 1024 if html_exists else 0
    asset_count = len(list(Path(ASSETS_DIR).iterdir())) if Path(ASSETS_DIR).exists() else 0
    return jsonify({
        "ok": html_exists,
        "html_exists": html_exists,
        "html_size_kb": html_size,
        "asset_files": asset_count,
        "build_running": _build_status["running"],
        "last_run": _build_status["last_run"],
        "last_result": _build_status["last_result"],
        "server_time": datetime.now().isoformat(),
    })


@app.route("/rebuild")
def manual_rebuild():
    """
    Manuel yeniden üretim tetikleyicisi.
    Güvenlik için SECRET_REBUILD_TOKEN env var ile koruyun.
    Örnek: GET /rebuild?token=gizli_token
    """
    from flask import request
    secret = os.environ.get("SECRET_REBUILD_TOKEN")
    if secret and request.args.get("token") != secret:
        return jsonify({"error": "Yetkisiz"}), 403

    if _build_status["running"]:
        return jsonify({"message": "Zaten bir üretim çalışıyor"}), 409

    # Arka planda başlat, hemen cevap ver
    threading.Thread(target=lambda: run_build(force=True), daemon=True).start()
    return jsonify({"message": "Yeniden üretim başlatıldı. /status endpoint'ini takip edin."}), 202


# ─────────────────────────────────────────────
# Zamanlayıcı (APScheduler)
# ─────────────────────────────────────────────
def start_scheduler():
    tz = pytz.timezone("Europe/Istanbul")
    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        nightly_check,
        trigger="cron",
        hour=4,
        minute=0,
        id="nightly_check",
        name="Gece 04:00 Drive Kontrolü",
    )
    scheduler.start()
    log.info("⏰ Zamanlayıcı başlatıldı — her gece 04:00 (İstanbul) çalışacak.")
    return scheduler


# ─────────────────────────────────────────────
# Uygulama başlangıcı
# ─────────────────────────────────────────────
scheduler = start_scheduler()

# İlk başlatmada HTML yoksa arka planda üret
if not Path(OUTPUT_FILE).exists():
    log.info("📂 sunum.html bulunamadı, arka planda üretiliyor…")
    threading.Thread(target=lambda: run_build(force=True), daemon=True).start()
else:
    log.info(f"📄 {OUTPUT_FILE} mevcut, sunucu hazır.")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    log.info(f"🚀 Sunucu başlatılıyor: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
