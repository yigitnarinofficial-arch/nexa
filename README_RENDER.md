# Render.com Dağıtım Rehberi

## Genel Bakış

```
GitHub repo
    └── drive_to_html.py   ← Drive'dan HTML üreten asıl kod (Service Account ile)
    └── app.py             ← Flask sunucusu + gece 04:00 zamanlayıcı
    └── requirements.txt
    └── render.yaml
```

Web sitesi şu şekilde çalışır:
1. Render uygulamayı GitHub'dan çeker ve başlatır
2. `sunum.html` yoksa hemen Drive'dan üretir
3. Her gece saat 04:00'te Drive'daki değişiklikleri kontrol eder
4. Değişiklik varsa siteyi baştan üretir, yoksa dokunmaz

---

## ADIM 1 — Google Cloud Service Account Oluştur

> **Neden Service Account?**
> Render'da tarayıcı yoktur. OAuth akışı (`credentials.json` + `token.json`) yalnızca
> yerel bilgisayarda çalışır. Service Account tarayıcı gerektirmez, 7/24 çalışır.

### 1.1 Service Account Oluşturma

1. [Google Cloud Console](https://console.cloud.google.com/) → Projenize girin
2. **APIs & Services → Credentials → Create Credentials → Service Account**
3. İsim: `render-drive-reader` (istediğiniz herhangi bir isim)
4. Role: **Viewer** (yalnızca okuma yeterli)
5. **Done** → Oluşturulan hesaba tıklayın
6. **Keys** sekmesi → **Add Key → Create new key → JSON**
7. JSON dosyası indirilir (`render-drive-reader-xxxx.json` gibi)

### 1.2 Google Drive Klasörünü Paylaş

1. Google Drive'da proje klasörünüze sağ tıklayın → **Paylaş**
2. Service Account e-postasını ekleyin (JSON dosyasındaki `client_email` alanı)
   Örnek: `render-drive-reader@proje-adı.iam.gserviceaccount.com`
3. Yetki: **Görüntüleyici**

### 1.3 JSON İçeriğini Kopyala

İndirilen JSON dosyasını bir metin editörüyle açın, tüm içeriği kopyalayın.
Örnek görünüm:
```json
{
  "type": "service_account",
  "project_id": "proje-adınız",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
  "client_email": "render-drive-reader@proje-adı.iam.gserviceaccount.com",
  ...
}
```

---

## ADIM 2 — GitHub Repo Hazırla

Aşağıdaki dosyaları bir GitHub reposuna yükleyin:

```
my-sunum-repo/
├── drive_to_html.py    ← (bu paketteki, Service Account versiyonu)
├── app.py
├── requirements.txt
├── render.yaml
└── .gitignore          ← aşağıya bakın
```

### .gitignore (GİZLİ DOSYALARI ASLA GITHUB'A YÜKLEMEYİN)

```
# Credentials - ASLA commit etme
credentials.json
token.json
*.json

# Cache ve üretilen dosyalar
.drive_cache/
sunum_assets/
sunum.html
.drive_manifest
__pycache__/
*.pyc
.env
```

---

## ADIM 3 — Render'a Dağıt

### 3.1 Yeni Web Servisi Oluştur

1. [render.com](https://render.com) → **New → Web Service**
2. GitHub reponuzu bağlayın
3. Ayarlar:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300`

### 3.2 Kalıcı Disk Ekle (ÖNEMLİ)

Render'ın ücretsiz planında disk yoktur — her yeniden başlatmada tüm dosyalar silinir.
Ücretli plan (Starter, $7/ay) ile kalıcı disk ekleyin:

1. Servis ayarları → **Disks → Add Disk**
2. Mount Path: `/data`
3. Size: `5 GB`

Ardından `render.yaml` dosyasındaki yolları güncelleyin:
```yaml
OUTPUT_FILE: /data/sunum.html
ASSETS_DIR: /data/sunum_assets
```

### 3.3 Environment Variables Girin

Render Dashboard → Servisiniz → **Environment** sekmesi:

| Key | Value |
|-----|-------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON dosyasının TÜM içeriği (tırnak işareti olmadan yapıştırın) |
| `DRIVE_FOLDER_ID` | Google Drive klasör ID'si |
| `PROJE_ADI` | Proje Sunumu |
| `PROJE_ALT_BASLIK` | Google Drive Arşivi |
| `OUTPUT_FILE` | `/data/sunum.html` |
| `ASSETS_DIR` | `/data/sunum_assets` |
| `SECRET_REBUILD_TOKEN` | Güçlü rastgele bir şifre (manuel rebuild için) |

> **💡 İpucu:** `GOOGLE_SERVICE_ACCOUNT_JSON` değerini girerken JSON içindeki
> satır sonlarına dikkat edin. Render bu değeri olduğu gibi saklar.

---

## ADIM 4 — Deploy Et

1. Render otomatik olarak GitHub'dan çeker ve başlatır
2. **Logs** sekmesinden ilerlemeyi takip edin
3. İlk çalıştırmada `sunum.html` yoksa arka planda üretim başlar
4. `https://your-service.onrender.com/` adresinde "Yükleniyor..." sayfası görünür
5. Üretim tamamlandığında (genellikle 2-10 dakika) site açılır

---

## ADIM 5 — Kontrol & İzleme

### Durum Kontrolü
```
GET https://your-service.onrender.com/status
```
Örnek yanıt:
```json
{
  "ok": true,
  "html_exists": true,
  "html_size_kb": 4200,
  "asset_files": 152,
  "build_running": false,
  "last_run": "2024-03-27T04:00:01",
  "last_result": "Başarılı"
}
```

### Manuel Yeniden Üretim
```
GET https://your-service.onrender.com/rebuild?token=SECRET_REBUILD_TOKEN_degeri
```

---

## Zamanlayıcı Nasıl Çalışır?

```
Her gece 04:00 (İstanbul saati / Europe/Istanbul)
    ↓
Drive'daki tüm dosyaların ID + modifiedTime bilgisi çekilir
    ↓
SHA-256 hash hesaplanır ve .drive_manifest ile karşılaştırılır
    ↓
  [Değişiklik yoksa] → Hiçbir şey yapılmaz, log'a yazılır
  [Değişiklik varsa] → drive_to_html.main() çalışır
                        ↓
                       sunum.html + sunum_assets/ güncellenir
```

---

## Sık Sorulan Sorular

**S: Render ücretsiz planını kullanabilir miyim?**  
Ücretsiz planda kalıcı disk yoktur. Uygulama her yeniden başladığında
(inaktivite sonrası ~15 dakika) tüm üretilen dosyalar silinir.
Sürekli erişim için **Starter** ($7/ay) planı önerilir.

**S: Drive'daki değişiklik anında yansır mı?**  
Hayır, yalnızca gece 04:00'te kontrol yapılır. Acil güncellemek için
`/rebuild?token=...` endpoint'ini kullanın.

**S: Üretim ne kadar sürer?**  
Drive klasörünün büyüklüğüne göre değişir. 50 dosya ~2 dakika,
200+ dosya ~10 dakika sürebilir. `.drive_cache/` sayesinde değişmeyen
dosyalar yeniden indirilmez.

**S: credentials.json dosyasına hâlâ ihtiyaç var mı?**  
Hayır. Service Account kullandığınız için `credentials.json` ve `token.json`
dosyalarına artık gerek yoktur. Sadece `GOOGLE_SERVICE_ACCOUNT_JSON`
ortam değişkeni yeterlidir.
