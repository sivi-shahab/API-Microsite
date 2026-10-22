# microsite_ocr

Service HTTP (dan CLI) untuk mengambil dokumen **KTP/NPWP** dari DMS-Cardsys berdasarkan nomor tiket (`NomorDokumen`), lalu mengekstrak datanya lewat OCR API (Qwen2.5-VL). Hasilnya dikembalikan sebagai JSON per tiket.

```
 client ──► microsite_ocr :8090 ──► DMS-Cardsys :8688 ──► OCR API :8070
 (HTTP)     /tickets/{id}/ocr[/ktp|/npwp]   search + download     /extract/ktp
            /tickets/ocr[/ktp|/npwp]                              /extract/npwp
```

Setiap dokumen yang diproses (KTP, NPWP, dan SELFIE) juga disimpan ke PostgreSQL bersama skor kemiripan wajah KTP vs SELFIE dari Face Verification Service (CompreFace), lihat [Database](#database) dan [Face similarity](#face-similarity).

Logika yang sama tersedia sebagai CLI (`python3 -m microsite_ocr --file tickets.txt`, tambah `--type ktp|npwp` untuk satu jenis saja) untuk proses batch.

## Daftar isi

- [Service HTTP](#service-http)
  - [Endpoint](#endpoint)
    - [Contoh curl](#contoh-curl)
    - [Contoh response](#contoh-response)
  - [Postman / Insomnia](#postman--insomnia)
  - [Deploy dengan Docker](#deploy-dengan-docker)
- [Database](#database)
  - [Face similarity](#face-similarity)
  - [Backfill similarity data lama](#backfill-similarity-data-lama)
- [Quick start (CLI)](#quick-start-cli)
- [Alur](#alur)
- [Konfigurasi](#konfigurasi)
- [Output](#output)
  - [Penanda kualitas (`warnings`)](#penanda-kualitas-warnings)
- [Download dokumen (tanpa OCR)](#download-dokumen-tanpa-ocr)
- [Struktur kode](#struktur-kode)
- [Hasil uji](#hasil-uji)
  - [Catatan NPWP](#catatan-npwp)
- [Troubleshooting](#troubleshooting)

## Service HTTP

```bash
cd /data/api_microsite
python3 -m venv venv && venv/bin/pip install -r requirements.txt
SERVICE_API_KEY=<kunci> venv/bin/python -m microsite_ocr.service   # listen di 0.0.0.0:8090

curl localhost:8090/health
curl -H "X-API-Key: <kunci>" localhost:8090/tickets/081156CqJu/ocr
curl -H "X-API-Key: <kunci>" localhost:8090/tickets/081156CqJu/ocr/ktp    # KTP saja
```

Swagger UI ada di `http://<host>:8090/docs` (aset Swagger disertakan, jadi jalan tanpa internet). Setiap endpoint punya contoh yang bisa dipilih dari dropdown **Examples**: nomor tiket (`081156CqJu` normal, `020803XGC9` foto buram, `TIDAKADA01` tidak ditemukan), body `POST`, dan response 200/401/422/502. Isi API key lewat tombol **Authorize** sebelum **Try it out**. Contohnya ada di `openapi_examples.py`; NIK dan data pribadi disamarkan, dan contoh NPWP masih ilustrasi.

### Postman / Insomnia

Collection siap pakai: `microsite_ocr.postman_collection.json` (format Postman Collection v2.1).

- **Postman:** *Import* → pilih file.
- **Insomnia:** *Import* → *From File* → pilih file yang sama (Insomnia membaca format Postman v2.1).

Setelah import, isi variabel collection `api_key` (ambil dengan `grep SERVICE_API_KEY .env`) dan, bila service diakses dari mesin lain, `base_url` (default `http://localhost:8090`). Variabel `ticket_id` (default `081156CqJu`) dipakai request di folder *Satu tiket*. Header `X-API-Key` dipasang otomatis lewat auth collection; `Health` dan `401 tanpa API key` sengaja tanpa auth.

| Folder | Request |
|---|---|
| System | `GET /health` |
| Satu tiket | `GET /tickets/{{ticket_id}}/ocr`, `/ocr/ktp`, `/ocr/npwp` |
| Beberapa tiket | `POST /tickets/ocr`, `/ocr/ktp`, `/ocr/npwp` dengan body dua tiket |
| Contoh error | 401 tanpa API key, 422 jenis dokumen `sim`, 422 nomor tiket `tiket!` |

Setiap request punya contoh response tersimpan (tab *Examples* di Postman) yang sama dengan contoh di Swagger. Insomnia tidak mengimpor contoh response, jadi contoh pertama tiap request juga ditaruh di deskripsinya (tab *Docs*).

Collection dibuat dari `openapi_examples.py`. Setelah mengubah contoh atau menambah endpoint, buat ulang supaya tetap sama dengan Swagger:

```bash
venv/bin/python -m microsite_ocr.postman > microsite_ocr.postman_collection.json
```

### Endpoint

| Method & path | Keterangan |
|---|---|
| `GET /health` | `{"status":"ok"\|"degraded","dms_reachable":bool,"ocr_ready":bool}`. Tidak butuh API key. |
| `GET /tickets/{ticket_id}/ocr` | OCR semua KTP/NPWP dalam satu tiket. Body = satu objek tiket (format sama dengan [Output](#output)). |
| `GET /tickets/{ticket_id}/ocr/ktp`<br>`GET /tickets/{ticket_id}/ocr/npwp` | Sama, tetapi hanya KTP **atau** hanya NPWP yang di-download dan di-OCR. Dokumen jenis lain masuk `skipped`. |
| `POST /tickets/ocr` | OCR beberapa tiket. Body `{"ticket_ids": ["081156CqJu", "020803XGC9"]}`, response array objek tiket, urutan sesuai input, duplikat dibuang. |
| `POST /tickets/ocr/ktp`<br>`POST /tickets/ocr/npwp` | Sama dengan `POST /tickets/ocr`, tetapi hanya satu jenis dokumen. |

Di endpoint per jenis, dokumen yang `supports_ocr` tapi bukan jenis yang diminta tidak di-download dan dicatat di `skipped` dengan format yang sama dengan SELFIE. Tiket tanpa dokumen jenis itu tetap HTTP 200.

#### Contoh curl

Set dulu host dan API key (di server ini key ada di `.env`):

```bash
BASE=http://localhost:8090            # dari mesin lain: http://<ip-server>:8090
KEY=$(grep SERVICE_API_KEY /data/api_microsite/.env | cut -d= -f2-)
```

Health check (tanpa API key):

```bash
curl -s $BASE/health
```

Satu tiket:

```bash
# KTP + NPWP
curl -s -H "X-API-Key: $KEY" $BASE/tickets/081156CqJu/ocr

# KTP saja
curl -s -H "X-API-Key: $KEY" $BASE/tickets/081156CqJu/ocr/ktp

# NPWP saja
curl -s -H "X-API-Key: $KEY" $BASE/tickets/081156CqJu/ocr/npwp
```

Beberapa tiket:

```bash
# KTP + NPWP
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"ticket_ids":["081156CqJu","020803XGC9"]}' $BASE/tickets/ocr

# KTP saja
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"ticket_ids":["081156CqJu","020803XGC9"]}' $BASE/tickets/ocr/ktp

# NPWP saja
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"ticket_ids":["081156CqJu","020803XGC9"]}' $BASE/tickets/ocr/npwp
```

Semua tiket di `tickets.txt` (satu nomor per baris), hasil disimpan ke file. Batch besar bisa makan waktu lama, jadi beri `--max-time` yang cukup:

```bash
python3 -c 'import json,sys; print(json.dumps({"ticket_ids": sys.stdin.read().split()}))' < tickets.txt \
  | curl -s --max-time 600 -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
         -d @- $BASE/tickets/ocr/ktp -o hasil_ktp.json
```

Lihat status HTTP-nya saja, mis. untuk cek API key atau jenis dokumen yang salah:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $KEY" $BASE/tickets/081156CqJu/ocr/sim   # 422
curl -s -o /dev/null -w "%{http_code}\n" $BASE/tickets/081156CqJu/ocr/ktp                        # 401
```

Ringkas hasil, mis. NIK + kode `warnings` per dokumen (server ini tidak punya `jq`, jadi pakai `python3`):

```bash
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"ticket_ids":["081156CqJu","020803XGC9"]}' $BASE/tickets/ocr/ktp \
  | python3 -c '
import json, sys
for t in json.load(sys.stdin):
    for d in t["data"]:
        print(t["ticket_id"], (d["data"] or {}).get("NIK", ""), ",".join(w["code"] for w in d["warnings"]), sep="\t")'
```

#### Contoh response

Diambil dari service pada 21 Oktober 2026; NIK dan data pribadi disamarkan.

`curl -s -H "X-API-Key: $KEY" $BASE/tickets/081156CqJu/ocr/ktp` → 200:

```json
{
  "ticket_id": "081156CqJu",
  "data": [
    {
      "node_id": "71698764-05ff-45f5-9301-537faec89d96",
      "filename": "KTP_3172XXXXXXXX0012",
      "document_type": "ktp",
      "created_at": "2026-10-21 11:07:53",
      "data": {
        "NIK": "3172XXXXXXXX0012",
        "NAMA": "NAMA NASABAH",
        "TTL": "KOTA, 01-01-1981",
        "JENIS_KELAMIN": "PEREMPUAN",
        "GOL_DARAH": "O",
        "ALAMAT": "JL. CONTOH NO.15",
        "RT_RW": "005/006",
        "KEL_DESA": "KEBON PALA",
        "KECAMATAN": "MAKASAR",
        "AGAMA": "KRISTEN",
        "STATUS_PERKAWINAN": "KAWIN",
        "PEKERJAAN": "KARYAWAN SWASTA",
        "KEWARGANEGARAAN": "WNI",
        "BERLAKU_HINGGA": "SEUMUR HIDUP"
      },
      "warnings": [],
      "error": null
    }
  ],
  "skipped": ["selfie: d70e1b19-a316-4e08-9b36-1d9c127e18ae"],
  "error": null
}
```

`curl -s -H "X-API-Key: $KEY" $BASE/tickets/081156CqJu/ocr/npwp` → 200. Tiket ini tidak punya NPWP, jadi `data` kosong dan KTP-nya ikut masuk `skipped`:

```json
{
  "ticket_id": "081156CqJu",
  "data": [],
  "skipped": [
    "selfie: d70e1b19-a316-4e08-9b36-1d9c127e18ae",
    "ktp: 71698764-05ff-45f5-9301-537faec89d96"
  ],
  "error": null
}
```

Bila tiket punya NPWP, bentuk `data[]` sama dengan KTP, hanya isi `data` mengikuti field NPWP. Contoh di bawah **ilustrasi**, belum dari data DMS (lihat [Catatan NPWP](#catatan-npwp)):

```json
{
  "node_id": "<nodeId>",
  "filename": "NPWP_<...>",
  "document_type": "npwp",
  "created_at": "2026-10-21 11:07:53",
  "data": {
    "NPWP": "XX.XXX.XXX.X-XXX.XXX",
    "NAMA": "NAMA NASABAH",
    "NIK": "3172XXXXXXXX0012",
    "ALAMAT": "JL. CONTOH NO.15",
    "KPP": "KPP PRATAMA ...",
    "TANGGAL_TERDAFTAR": "01-01-2015"
  },
  "warnings": [],
  "error": null
}
```

```bash
curl -s -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
     -d '{"ticket_ids":["081156CqJu","TIDAKADA01"]}' $BASE/tickets/ocr/ktp
```

→ 200. Tiket yang tidak ditemukan di DMS tetap muncul dengan `data: []` dan `error: null`:

```json
[
  {
    "ticket_id": "081156CqJu",
    "data": [
      {
        "node_id": "71698764-05ff-45f5-9301-537faec89d96",
        "filename": "KTP_3172XXXXXXXX0012",
        "document_type": "ktp",
        "created_at": "2026-10-21 11:07:53",
        "data": {"NIK": "3172XXXXXXXX0012", "NAMA": "NAMA NASABAH", "...": "..."},
        "warnings": [],
        "error": null
      }
    ],
    "skipped": ["selfie: d70e1b19-a316-4e08-9b36-1d9c127e18ae"],
    "error": null
  },
  {
    "ticket_id": "TIDAKADA01",
    "data": [],
    "skipped": [],
    "error": null
  }
]
```

Response error:

```jsonc
// 422: GET /tickets/081156CqJu/ocr/sim
{"detail":[{"type":"literal_error","loc":["path","doc_type"],"msg":"Input should be 'ktp' or 'npwp'","input":"sim","ctx":{"expected":"'ktp' or 'npwp'"}}]}

// 401: header X-API-Key tidak dikirim / salah
{"detail":"X-API-Key tidak valid"}

// 502: GET /tickets/{id}/ocr/... saat search DMS gagal
{"detail":"Search DMS gagal: <pesan error>"}
```

Status HTTP:

| Status | Kapan |
|---|---|
| 200 | Request diproses. Tiket tidak ditemukan tetap 200 dengan `"data": []`. Dokumen yang gagal download/OCR ditandai di `data[].error`; di `POST /tickets/ocr` tiket yang gagal search ditandai di `error` tiket itu. |
| 401 | `SERVICE_API_KEY` diisi dan header `X-API-Key` tidak cocok/tidak ada. |
| 422 | Nomor tiket tidak sesuai pola `[A-Za-z0-9_-]{1,64}`, `ticket_ids` kosong, lebih dari `MAX_TICKETS_PER_REQUEST`, atau jenis dokumen selain `ktp`/`npwp`. |
| 502 | `GET /tickets/{id}/ocr` dan `GET /tickets/{id}/ocr/{ktp\|npwp}`: search ke DMS gagal (DMS mati, timeout, atau `code` ≠ `00`). |

Satu request batch 7 tiket (8 KTP) selesai ±14 detik. Request OCR serentak dari **semua** request masuk dibatasi `MAX_WORKERS` (satu thread pool bersama), jadi banyak client sekaligus tidak membanjiri vLLM; request berikutnya mengantre. Untuk batch besar, atur timeout di sisi client.

> **Keamanan.** Response berisi NIK, nama, dan alamat nasabah. Isi `SERVICE_API_KEY` di setiap deploy; bila kosong, service menulis `WARNING` di log dan menerima request tanpa autentikasi. Service tidak memakai HTTPS sendiri, jadi taruh di belakang reverse proxy TLS bila diakses dari luar jaringan internal.

### Deploy dengan Docker

```bash
cd /data/api_microsite
SERVICE_API_KEY=<kunci> docker compose up -d --build
curl localhost:8090/health
docker compose logs -f api
```

- Compose menjalankan dua container: `api` dan `db` (PostgreSQL 16, lihat [Database](#database)). `POSTGRES_PASSWORD` wajib diisi; di server ini ada di `.env`.
- Deploy di server ini menyimpan `SERVICE_API_KEY` di `/data/api_microsite/.env` (permission `600`), yang dibaca otomatis oleh `docker compose up -d`. Ambil key-nya dengan `grep SERVICE_API_KEY .env`; untuk mengganti key, ubah file itu lalu jalankan `docker compose up -d` lagi.
- `docker-compose.yml` meneruskan `DMS_BASE_URL`, `OCR_BASE_URL`, `MAX_WORKERS`, `SERVICE_API_KEY` dari shell/`.env`; port host diatur lewat `SERVICE_PORT` (default 8090).
- Zona waktu container (dan timestamp log) diatur lewat `TZ`, default `Asia/Jakarta`.
- Network compose memakai **MTU 1400** (`DOCKER_MTU`), sama dengan NIC server `enp1s0`. Dengan default Docker 1500, search ke DMS berhasil tapi download file gambar selalu `Read timed out`.
- `.dockerignore` hanya mengizinkan `requirements.txt` dan `microsite_ocr/`, jadi foto KTP/selfie, `downloads/`, dan `hasil_ocr.json` tidak ikut masuk image.
- `HEALTHCHECK` container memanggil `/health`; status container `unhealthy` bila DMS atau OCR API tidak siap.

## Database

Container `db` (`postgres:16-alpine`, database `microsite_ocr`, user `microsite`) menyimpan setiap dokumen dari setiap hit endpoint OCR ke tabel `ocr_document`. Schema ada di `db/init/01_ocr_document.sql` dan dijalankan otomatis **hanya saat volume `pgdata` masih kosong**; perubahan schema berikutnya harus dijalankan manual dengan `psql`.

| Kolom | Tipe | Isi |
|---|---|---|
| `id` | `uuid` | Primary key, `gen_random_uuid()` |
| `hit_at` | `timestamptz` | Waktu API di-hit. Semua dokumen dari satu request memakai nilai yang sama. |
| `nomor_dokumen` | `varchar(64)` | Nomor tiket (`NomorDokumen`) |
| `create_date` | `timestamp` | `createDate` dari search DMS (waktu lokal DMS); NULL bila formatnya tidak dikenali |
| `file_type` | `varchar(10)` | `ktp`, `npwp`, atau `selfie` |
| `node_id` | `varchar(64)` | `nodeId` dokumen di DMS |
| `file_base64` | `text` | Isi file dari DMS, base64; NULL bila download gagal |
| `ocr_result` | `jsonb` | Satu objek `data[]` dari response (node_id, filename, document_type, created_at, data, warnings, error). **NULL untuk SELFIE.** |
| `face_similarity` | `numeric(5,4)` | Skor kemiripan wajah KTP vs SELFIE (0–1), lihat [Face similarity](#face-similarity). Sama untuk semua KTP dan SELFIE satu nomor dokumen, di semua hit. **Selalu NULL untuk NPWP.** |

Aturan yang dijaga database (check constraint): `file_type` hanya tiga nilai di atas, SELFIE tidak punya `ocr_result`, NPWP tidak punya `face_similarity`, dan skor di rentang 0–1.

Kapan baris ditulis:

- Satu baris per dokumen per hit. Tiket yang di-hit dua kali menghasilkan dua set baris; ambil yang terbaru dengan `ORDER BY hit_at DESC`.
- KTP/NPWP ditulis untuk jenis yang diminta endpoint, termasuk yang gagal OCR (`ocr_result.error` terisi).
- SELFIE di-download (tanpa OCR) dan ditulis setiap kali KTP diminta (`/ocr`, `/ocr/ktp`), supaya pasangan KTP–SELFIE siap untuk face matching. Di `/ocr/npwp` SELFIE tidak di-download. Response API tidak berubah: SELFIE tetap tercatat di `skipped`.
- Tiket tidak ditemukan atau gagal search tidak menghasilkan baris. Dokumen jenis `unknown` tidak disimpan.
- Bila database tidak bisa diakses, request **tetap** mengembalikan hasil OCR; kegagalan hanya ditulis ke log (`Simpan N dokumen ke database gagal`).

**Mengubah skor manual.** KTP dan SELFIE dengan nomor dokumen yang sama harus punya skor yang sama, jadi bila perlu mengisi/mengoreksi skor di luar service, pakai fungsi `set_face_similarity`, bukan `UPDATE` per baris. Fungsi ini mengisi semua baris KTP dan SELFIE nomor dokumen itu (NPWP tidak disentuh) dan mengembalikan jumlah baris yang diubah:

```sql
SELECT set_face_similarity('081156CqJu', 0.8731);
```

Akses dari host (port hanya dibuka di `127.0.0.1:5432`, atur lewat `POSTGRES_PORT`):

```bash
docker compose exec db psql -U microsite -d microsite_ocr
# atau dari host / proses lain:
psql "postgresql://microsite:$(grep POSTGRES_PASSWORD .env | cut -d= -f2-)@127.0.0.1:5432/microsite_ocr"
```

```sql
-- Ringkasan hit terakhir, tanpa kolom base64 yang besar
SELECT hit_at, nomor_dokumen, file_type, node_id, ocr_result->'data'->>'NIK' AS nik, face_similarity
FROM ocr_document ORDER BY hit_at DESC LIMIT 20;

-- Simpan kembali foto dari base64
psql ... -Atc "SELECT file_base64 FROM ocr_document WHERE id = '<uuid>'" | base64 -d > foto.jpg
```

CLI juga menyimpan ke database bila `DATABASE_URL` diisi; tanpa `DATABASE_URL` tidak ada yang disimpan.

### Face similarity

Bila `DATABASE_URL` **dan** `FACE_API_KEY` diisi, setelah OCR selesai setiap tiket yang punya KTP dan SELFIE (keduanya berhasil di-download) dikirim ke Face Verification Service:

```
POST {FACE_BASE_URL}/api/v1/verification/verify     header x-api-key: {FACE_API_KEY}
  source_image = SELFIE    target_image = KTP        (multipart)
```

- Skor = `similarity` tertinggi di `result[].face_matches[]` (wajah di KTP yang paling mirip dengan selfie).
- Tiket dengan lebih dari satu KTP atau SELFIE: setiap pasangan dibandingkan, yang disimpan skor tertinggi.
- Skor NULL bila tiket tidak punya pasangan KTP–SELFIE (mis. `/ocr/npwp`, atau tiket tanpa selfie), atau verify gagal (service mati, API key salah, wajah tidak terdeteksi: `HTTP 400 ... "code": 28`). Kegagalan ditulis ke log `Tiket <id>: face verify gagal: ...` dan tidak menggagalkan request.
- Skor ditulis lewat `set_face_similarity`, jadi ikut mengisi/menimpa baris KTP dan SELFIE nomor dokumen itu dari hit sebelumnya (skor terbaru yang berlaku). Hit yang verify-nya gagal tidak mengubah skor lama.
- Skor hanya disimpan ke database; response API tidak berubah.
- Verify berjalan setelah semua OCR request itu selesai, di thread pool sendiri (`MAX_WORKERS` request serentak, terpisah dari pool OCR), jadi menambah waktu response kira-kira satu panggilan verify.

Di Docker, `FACE_BASE_URL` default `http://host.docker.internal:8000` (CompreFace di host yang sama; `localhost` di dalam container menunjuk ke container itu sendiri). Isi `FACE_API_KEY` di `.env` lalu `docker compose up -d`. Tanpa `FACE_API_KEY` service menulis `WARNING FACE_API_KEY kosong` dan kolom `face_similarity` tetap NULL.

### Backfill similarity data lama

Baris yang tersimpan sebelum `FACE_API_KEY` diisi, atau yang verify-nya gagal, punya `face_similarity` NULL. `backfill_similarity` menghitungnya dari foto base64 yang sudah ada di tabel, tanpa memanggil DMS atau OCR, dengan aturan skor yang sama seperti saat hit API:

```bash
# Lihat nomor dokumen yang akan diproses (tidak butuh FACE_API_KEY)
docker compose exec api python -m microsite_ocr.backfill_similarity --dry-run

# Proses semua nomor dokumen yang masih punya skor NULL
docker compose exec api python -m microsite_ocr.backfill_similarity

# Nomor dokumen tertentu, termasuk yang sudah punya skor (hitung ulang)
docker compose exec api python -m microsite_ocr.backfill_similarity 081156CqJu --rescore
```

- Yang diproses: nomor dokumen yang punya foto KTP **dan** SELFIE (`file_base64` tidak NULL) dan masih ada baris KTP/SELFIE dengan skor NULL (atau semua, dengan `--rescore`). Urut dari hit paling lama.
- Foto yang dibandingkan: setiap `node_id` KTP dan SELFIE nomor dokumen itu (satu foto per `node_id`, dari hit terbaru), semua pasangan, skor tertinggi.
- Opsi: `--limit N` (maksimal N nomor dokumen), `--batch-size N` (jumlah nomor dokumen yang fotonya dimuat ke memori sekaligus, default 20), `--file tickets.txt`.
- Aman dijalankan berulang: run kedua tanpa `--rescore` hanya memproses yang masih NULL.
- Exit code: `0` semua berhasil (termasuk bila tidak ada yang perlu diproses), `1` ada nomor dokumen yang semua verify-nya gagal (skornya tidak diubah, nomornya ditulis di log), `2` `DATABASE_URL` atau `FACE_API_KEY` kosong.

Dari host (di luar container), set dulu `DATABASE_URL=postgresql://microsite:<sandi>@127.0.0.1:5432/microsite_ocr`, `FACE_BASE_URL=http://localhost:8000`, dan `FACE_API_KEY`, lalu `venv/bin/python -m microsite_ocr.backfill_similarity`.

> **Data pribadi.** Tabel ini berisi foto KTP, foto wajah, dan NIK nasabah. Data tersimpan di volume Docker `api_microsite_pgdata`; `docker compose down -v` menghapusnya permanen. Perlakukan sesuai UU PDP.

## Quick start (CLI)

```bash
cd /data/api_microsite
pip install -r requirements.txt

# Dari file (satu nomor tiket per baris)
python3 -m microsite_ocr --file tickets.txt --output hasil_ocr.json

# Langsung dari argumen, hasil ke stdout
python3 -m microsite_ocr 081156CqJu 020803XGC9

# Hanya KTP atau hanya NPWP (jenis lain masuk `skipped`)
python3 -m microsite_ocr --type ktp --file tickets.txt
python3 -m microsite_ocr --type npwp --file tickets.txt
```

Log proses ditulis ke stderr, hasil JSON ke stdout atau file `--output`.

| Exit code | Arti |
|---|---|
| 0 | Semua tiket dan dokumen berhasil |
| 1 | Ada tiket yang gagal di-search atau dokumen yang gagal di-download/OCR (tiket tidak ditemukan **tidak** dihitung gagal) |
| 2 | Tidak ada nomor tiket |

## Alur

```mermaid
sequenceDiagram
    autonumber
    participant S as microsite_ocr
    participant D as DMS-Cardsys :8688
    participant O as OCR API :8070

    S->>D: POST /api/v2/search {"metadata":{"NomorDokumen":"<tiket>"},"mode":"any"}
    D-->>S: documents[] (nodeId, metadata.filename)
    S->>S: Klasifikasi dari filename: KTP / NPWP / SELFIE
    loop setiap KTP/NPWP (paralel, MAX_WORKERS)
        S->>D: GET /api/v2/download?id=<nodeId>
        D-->>S: file gambar
        S->>S: Deteksi format dari signature file
        S->>O: POST /extract/ktp atau /extract/npwp (multipart "file")
        O-->>S: {"success":true,"data":{...}}
    end
```

Poin penting:

- **Jenis dokumen dari nama file.** DMS memakai dua pola, `KTP_<NIK>` dan `<prefix>_KTP_<NIK>`, jadi `KTP`/`NPWP`/`SELFIE` dicari di setiap segmen yang dipisah `_`. SELFIE dan jenis lain dilewati dan dicatat di `skipped`.
- **Format gambar dari isi file**, bukan dari ekstensi atau `content-type` DMS (contoh di koleksi Insomnia memakai `extension: jpg` untuk file PNG). Yang didukung OCR API: JPEG, PNG, WebP.
- **Search berjalan berurutan, OCR paralel.** vLLM di belakang OCR API mem-batch request bersamaan, jadi 4 request sekaligus selesai hampir secepat satu (±7 detik).
- **Error tidak menghentikan batch.** Tiket atau dokumen yang gagal diberi `error` di hasilnya; sisanya tetap diproses. Tiket yang tidak ditemukan di DMS bukan error: hasilnya `"data": []` dan `"error": null`.

## Konfigurasi

Semua lewat environment variable:

| Variabel | Default | Keterangan |
|---|---|---|
| `DMS_BASE_URL` | `http://10.191.22.16:8688` | Host DMS-Cardsys (UAT) |
| `OCR_BASE_URL` | `http://10.168.105.11:8070` | Host OCR API |
| `DMS_TIMEOUT` | `30` | Timeout request DMS (detik) |
| `OCR_TIMEOUT` | `120` | Timeout request OCR (detik) |
| `MAX_WORKERS` | `4` | Jumlah request OCR paralel (di service: total untuk semua request masuk) |
| `HOST` | `0.0.0.0` | Service: alamat listen |
| `PORT` | `8090` | Service: port listen |
| `SERVICE_API_KEY` | kosong | Service: nilai header `X-API-Key` yang wajib dikirim. Kosong = tanpa autentikasi. |
| `MAX_TICKETS_PER_REQUEST` | `50` | Service: batas jumlah tiket di `POST /tickets/ocr` |
| `FACE_BASE_URL` | `http://localhost:8000` | Face Verification Service (CompreFace). Di Docker default `http://host.docker.internal:8000`. |
| `FACE_API_KEY` | kosong | API key service verification CompreFace (header `x-api-key`). Kosong = similarity tidak dihitung. |
| `FACE_TIMEOUT` | `30` | Timeout request face verify (detik) |
| `DATABASE_URL` | kosong | PostgreSQL penyimpan hasil, mis. `postgresql://user:pass@host:5432/db`. Kosong = tidak disimpan. Di Docker diisi otomatis dari `POSTGRES_PASSWORD`. |

Contoh:

```bash
OCR_BASE_URL=http://localhost:8070 MAX_WORKERS=8 python3 -m microsite_ocr --file tickets.txt
```

## Output

Array JSON, satu objek per tiket, urutannya sama dengan input:

```json
[
  {
    "ticket_id": "081156CqJu",
    "data": [
      {
        "node_id": "71698764-05ff-45f5-9301-537faec89d96",
        "filename": "KTP_3172XXXXXXXX0012",
        "document_type": "ktp",
        "created_at": "2026-10-21 11:07:53",
        "data": {
          "NIK": "3172XXXXXXXX0012",
          "NAMA": "...",
          "TTL": "...",
          "...": "..."
        },
        "warnings": [],
        "error": null
      }
    ],
    "skipped": ["selfie: d70e1b19-a316-4e08-9b36-1d9c127e18ae"],
    "error": null
  }
]
```

Field `data` mengikuti response OCR API:

| Dokumen | Field |
|---|---|
| KTP | NIK, NAMA, TTL, JENIS_KELAMIN, GOL_DARAH, ALAMAT, RT_RW, KEL_DESA, KECAMATAN, AGAMA, STATUS_PERKAWINAN, PEKERJAAN, KEWARGANEGARAAN, BERLAKU_HINGGA |
| NPWP | NPWP, NAMA, NIK, ALAMAT, KPP, TANGGAL_TERDAFTAR |

Field yang tidak terbaca berisi string kosong `""`.

### Penanda kualitas (`warnings`)

OCR API tetap mengembalikan `success: true` walaupun foto buram dan field-nya hampir kosong. Karena itu setiap hasil OCR dicek dan diberi `warnings` bila perlu dicek manual. Penanda **tidak** membuat dokumen gagal dan tidak mengubah exit code; ia juga ditulis ke log sebagai `WARNING`.

```json
"warnings": [
  {"code": "mostly_empty", "message": "9 dari 14 field kosong; kemungkinan foto buram atau terpotong"},
  {"code": "nik_mismatch", "message": "NIK hasil OCR berbeda dari NIK di nama file (beda di digit ke-1, 10, 11)"}
]
```

| `code` | Berlaku untuk | Kapan muncul |
|---|---|---|
| `required_field_empty` | KTP, NPWP | Field wajib kosong. KTP: NIK, NAMA, TTL, ALAMAT. NPWP: NPWP, NAMA. |
| `mostly_empty` | KTP, NPWP | Lebih dari separuh field kosong (`MAX_EMPTY_RATIO = 0.5`). |
| `nik_mismatch` | KTP | NIK hasil OCR berbeda dari NIK di nama file DMS; pesan menyebut posisi digit yang beda. |
| `filename_nik_invalid` | KTP | NIK di nama file bukan 16 digit, jadi tidak bisa dibandingkan. |

NIK di nama file diambil dari deretan ≥ 12 digit di segmen terakhir (`KTP_<NIK>` atau `<prefix>_KTP_<NIK>`). Nama file tanpa NIK tidak dicek. Pesan penanda sengaja tidak memuat nilai NIK supaya aman ditulis ke log. Aturan dan ambang ada di `quality.py`.

Memfilter dokumen yang perlu dicek:

```bash
python3 -c "
import json
for t in json.load(open('hasil_ocr.json')):
    for d in t['data']:
        for w in d['warnings']:
            print(t['ticket_id'], d['node_id'], w['code'], w['message'])"
```

> **Data pribadi.** `hasil_ocr.json` berisi NIK, nama, dan alamat nasabah. Perlakukan sesuai UU PDP: jangan di-commit, jangan dibagikan di luar tim, hapus bila sudah tidak dipakai.

## Download dokumen (tanpa OCR)

Untuk mengunduh semua dokumen tiket apa adanya (KTP, NPWP, SELFIE, dan jenis lain), tanpa OCR:

```bash
python3 -m microsite_ocr.download --file tickets.txt                    # ke ./downloads
python3 -m microsite_ocr.download 020803XGC9 --output-dir /tmp/cek_ktp   # satu tiket, folder lain
```

Alurnya: `POST /api/v2/search` per tiket, lalu `GET /api/v2/download?id=<nodeId>` untuk setiap dokumen yang ditemukan. File disimpan sebagai `<JENIS>_<tiket>.<ext>`:

- `<JENIS>` dari nama file DMS: `KTP`, `NPWP`, `SELFIE`, atau `UNKNOWN`.
- `<ext>` dari isi file (`jpg`, `png`, `webp`); file yang bukan gambar disimpan sebagai `.bin`.
- Dokumen kedua dengan jenis yang sama di tiket yang sama diberi akhiran `_2`, `_3`, dst. (mis. `KTP_101245vNrq_2.png`).
- File dengan nama yang sama ditimpa.

Exit code sama dengan perintah OCR: `0` semua berhasil (tiket tidak ditemukan tetap `0`, hanya dicatat sebagai warning), `1` ada search/download yang gagal, `2` tidak ada nomor tiket. Hanya `DMS_BASE_URL` dan `DMS_TIMEOUT` yang dipakai.

Hasil run 21 Oktober 2026 untuk 7 tiket di `tickets.txt`: 11 file (8 KTP PNG 640–731 piksel lebar, 3 SELFIE JPEG 480×480). Dua KTP `101245vNrq` identik (SHA-256 sama), jadi tiket itu sebenarnya mengunggah file yang sama dua kali.

> Folder `downloads/` berisi foto KTP dan wajah nasabah. Perlakukan sesuai UU PDP: jangan di-commit, hapus bila sudah tidak dipakai.

## Struktur kode

```
microsite_ocr/
├── service.py      # Service HTTP (FastAPI): /health, /tickets/{id}/ocr[/{jenis}], /tickets/ocr[/{jenis}]
├── openapi_examples.py  # Contoh request/response di Swagger UI (/docs) dan collection Postman
├── postman.py      # Buat microsite_ocr.postman_collection.json dari openapi_examples.py
├── static/         # Aset Swagger UI untuk /docs (offline)
├── __main__.py     # CLI OCR: parsing argumen, tulis JSON, exit code
├── download.py     # CLI download: TicketDownloader, simpan file per tiket
├── config.py       # Settings dari env var
├── cli.py          # Bagian bersama kedua CLI: logging, argumen tiket, load_ticket_ids
├── documents.py    # DocumentType, classify_filename, DmsDocument, DownloadedFile, ProcessedDocument
├── images.py       # detect_image_type dari signature file
├── dms_client.py   # DmsClient: search_by_ticket, download
├── ocr_client.py   # OcrClient.extract
├── quality.py      # check_quality: penanda field kosong & NIK tidak cocok
├── face_client.py  # FaceClient.verify: HTTP ke CompreFace, similarity SELFIE vs KTP
├── face_matching.py     # FaceMatcher, group_faces: aturan skor per nomor dokumen (pasangan, skor tertinggi)
├── store.py        # OcrStore: semua SQL tabel ocr_document (simpan hit, set skor, query backfill)
├── recorder.py     # HitRecorder: dokumen satu hit → face matching → store
├── backfill_similarity.py  # CLI backfill: skor untuk data lama, pakai face_matching + store
└── pipeline.py     # TicketOcrPipeline: search → download → OCR → cek kualitas → serahkan ke DocumentRecorder
```

File deploy di root: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `db/init/01_ocr_document.sql` (schema database). Collection Postman/Insomnia: `microsite_ocr.postman_collection.json`.

```mermaid
flowchart TD
    service["service.py<br/>FastAPI"] --> pipeline["pipeline.py<br/>TicketOcrPipeline"]
    service --> config
    service --> cli
    main["__main__.py"] --> pipeline
    main --> config["config.py"]
    pipeline --> dms["dms_client.py<br/>DmsClient"]
    pipeline --> ocr["ocr_client.py<br/>OcrClient"]
    main --> cli["cli.py"]
    download["download.py<br/>TicketDownloader"] --> dms
    download --> config
    download --> cli
    download --> images["images.py"]
    dms --> docs["documents.py"]
    ocr --> docs
    ocr --> images
    pipeline --> docs
    pipeline --> quality["quality.py"]
    service --> recorder["recorder.py<br/>HitRecorder"]
    main --> recorder
    pipeline -. "DocumentRecorder (Protocol)" .-> recorder
    recorder --> matching["face_matching.py<br/>FaceMatcher"]
    recorder --> store["store.py<br/>OcrStore"]
    backfill["backfill_similarity.py"] --> matching
    backfill --> store
    backfill --> cli
    matching --> face["face_client.py<br/>FaceClient"]
    face --> images
    store --> docs
    matching --> docs
    quality --> docs
```

Client DMS dan OCR tidak saling tahu; pipeline yang menyambungkan keduanya. Pipeline juga tidak tahu soal database maupun CompreFace: ia hanya menyerahkan `ProcessedDocument` satu hit ke `DocumentRecorder` (garis putus-putus). Penyimpanan dan face matching dirangkai di `recorder.py`; `service.py` dan `__main__.py` yang memasangnya. Aturan skor (`face_matching.py`) dan SQL (`store.py`) masing-masing ada di satu tempat, dipakai bersama oleh recorder dan backfill. Menambah jenis dokumen baru (mis. SIM) cukup:

1. Tambah anggota di `DocumentType` (nilainya = path `/extract/<nilai>` di OCR API).
2. Masukkan ke `supports_ocr` dan ke urutan pengecekan di `classify_filename`.
3. Tambah nilainya ke `OcrDocType` di `service.py` supaya ada endpoint `/ocr/<nilai>`; `--type` di CLI otomatis ikut.
4. Tambah contoh response jenis baru di `openapi_examples.py`, lalu buat ulang collection Postman (`python -m microsite_ocr.postman`).

## Hasil uji

Run 21 Oktober 2026 untuk 7 tiket di `tickets.txt` (`DMS_BASE_URL` dan `OCR_BASE_URL` default). CLI dan service (`POST /tickets/ocr`, baik lewat `venv` maupun container Docker) memberi hasil yang sama: exit code 0 / HTTP 200, 8 KTP berhasil di-OCR, 3 SELFIE dilewati, tidak ada NPWP. 3 dari 8 KTP bersih, 5 diberi penanda.

| Tiket | KTP di-OCR | SELFIE dilewati | `warnings` | Catatan |
|---|---|---|---|---|
| `081156CqJu` | 1 | 1 | - | Semua field terisi |
| `020803XGC9` | 1 | 0 | `required_field_empty`, `mostly_empty`, `nik_mismatch` | 9 dari 14 field kosong (NAMA, ALAMAT dll.); NIK beda di digit ke-1, 10, 11. Foto sudah dicek: buram, 731×411 px, teks data tidak terbaca. NIK di nama file (kode 3578 = Kota Surabaya, sesuai kartu) yang benar. |
| `071247bL4i` | 1 | 1 | `required_field_empty`, `nik_mismatch` | ALAMAT kosong; NIK beda di digit ke-6 |
| `020313wa3H` | 1 | 1 | - | Semua field terisi |
| `0102253on9` | 1 | 0 | - | Semua field terisi |
| `101245vNrq` | 2 | 0 | `filename_nik_invalid` (×2) | Semua field terisi; NIK di nama file hanya 15 digit. Kedua file identik (SHA-256 sama). |
| `0203106ktH` | 1 | 0 | `nik_mismatch` | Semua field terisi; NIK beda di digit ke-11, 12 |

Tindak lanjut:

- [ ] `020803XGC9`: minta nasabah unggah ulang foto KTP yang tajam; hasil OCR tidak bisa dipakai.
- [ ] `071247bL4i` dan `0203106ktH`: cek foto KTP asli untuk menentukan mana yang salah, hasil OCR atau NIK di nama file.
- [ ] `101245vNrq`: tanyakan ke tim pengunggah kenapa NIK di nama file kurang satu digit dan kenapa file yang sama diunggah dua kali.
- [ ] Cari tiket yang berisi NPWP untuk menguji jalur `/extract/npwp` dari DMS (lihat [Catatan NPWP](#catatan-npwp)).

### Catatan NPWP

Belum ada dokumen NPWP di tiket uji, jadi jalur NPWP (`classify_filename` → `/extract/npwp`) baru teruji sampai level kode, belum dengan data DMS.

- Ketujuh tiket di `tickets.txt` hanya berisi KTP dan SELFIE; tidak ada `metadata.filename` yang mengandung segmen `NPWP`.
- Search tanpa nomor tiket, `{"metadata":{"filename":"NPWP"},"mode":"any"}` dan `{"metadata":{"Channel":"NPWP"},"mode":"any"}`, sama-sama mengembalikan `code: 00` dengan `found: 0`. Belum diketahui apakah search mendukung pencocokan sebagian (partial match), jadi ini **bukan** bukti bahwa DMS tidak menyimpan NPWP.
- Asumsi kode: file NPWP di DMS bernama `NPWP_<...>` atau `<prefix>_NPWP_<...>`, mengikuti pola KTP. Bila ternyata polanya lain, sesuaikan `classify_filename` di `documents.py`.
- Begitu ada tiket NPWP, cukup tambahkan nomornya ke `tickets.txt` lalu jalankan `python3 -m microsite_ocr --file tickets.txt`; tidak perlu perubahan kode.

## Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| Service: `401 X-API-Key tidak valid` | Header `X-API-Key` tidak dikirim atau beda dengan `SERVICE_API_KEY`. |
| Log `face verify gagal: ... Connection refused` | Face Verification Service tidak jalan di `FACE_BASE_URL`. Cek `curl -X POST localhost:8000/api/v1/verification/verify` dari host (harus dijawab, walau 4xx). |
| Log `face verify gagal: HTTP 401` / `HTTP 400 ... "code": 28` | API key salah / wajah tidak terdeteksi di selfie atau KTP. Skor disimpan NULL. |
| Backfill: `Nomor dokumen gagal (skor tidak diubah)` | Semua verify untuk nomor dokumen itu gagal; lihat baris `face verify gagal` di atasnya untuk penyebabnya. Jalankan ulang setelah diperbaiki. |
| Log `Simpan N dokumen ke database gagal` | Container `db` mati atau `DATABASE_URL` salah. Cek `docker compose ps db`; hasil OCR tetap dikembalikan, hanya tidak tersimpan. |
| `docker compose up`: `isi POSTGRES_PASSWORD di .env` | Tambahkan `POSTGRES_PASSWORD=<sandi>` ke `.env`. |
| Service: `/health` → `degraded` | Lihat `dms_reachable` / `ocr_ready` untuk tahu mana yang bermasalah, lalu cek baris `:8688` / `:8070` di bawah. |
| Service di Docker: `Read timed out` saat download DMS, padahal dari host lancar | MTU network Docker lebih besar dari NIC server. Pastikan `DOCKER_MTU` = MTU NIC (`ip link show enp1s0`), lalu `docker compose down && docker compose up -d`. |
| `ConnectionError` ke `:8688` | DMS tidak terjangkau dari server ini. Cek `curl http://10.191.22.16:8688/api/v2/search` dan `DMS_BASE_URL`. |
| `ConnectionError` ke `:8070` | OCR API mati. Cek `curl http://10.168.105.11:8070/health`; di server OCR jalankan `docker compose ps` di `/data/ocr-qwen`. |
| `OCR ktp gagal: HTTP 500` | vLLM tidak siap. `/health` akan menunjukkan `"status":"degraded"`. |
| `OCR ... HTTP 413` | Gambar lebih dari 10 MB. |
| `File bukan JPEG, PNG, atau WebP` | File di DMS bukan gambar (mis. PDF) atau rusak. |
| `Search tiket ... gagal: <code>` | DMS mengembalikan `code` selain `00`. |
| `data: []` dan log `tidak ada dokumen di DMS` | Nomor tiket tidak ditemukan di DMS (bukan error). Cek ejaan tiket: huruf besar/kecil berpengaruh. |
| `warnings` berisi `mostly_empty` / `required_field_empty` | Kualitas foto KTP rendah (buram, miring, terpotong). Cek gambarnya dengan `python3 -m microsite_ocr.download <tiket>`. |
| `warnings` berisi `nik_mismatch` | OCR salah baca digit, atau NIK di nama file yang salah. Bandingkan dengan foto aslinya. |
| `warnings` berisi `filename_nik_invalid` | NIK di nama file DMS bukan 16 digit; masalah di sistem pengunggah, bukan OCR. |

Dokumentasi API DMS: `Dokumentasi API DMS-Cardsys (UAT).pdf`. Dokumentasi OCR API: `/data/ocr-qwen/README.md` atau Swagger di `http://10.168.105.11:8070/docs`.
