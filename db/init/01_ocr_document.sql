-- Satu baris = satu dokumen (KTP/NPWP/SELFIE) dari satu hit API microsite_ocr.
-- Dijalankan otomatis oleh image postgres saat volume data masih kosong.

CREATE TABLE IF NOT EXISTS ocr_document (
    id              uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Waktu API di-hit; semua dokumen dari satu request memakai nilai yang sama.
    hit_at          timestamptz  NOT NULL DEFAULT now(),
    nomor_dokumen   varchar(64)  NOT NULL,
    -- `createDate` dari search DMS (waktu lokal DMS, tanpa zona waktu).
    create_date     timestamp,
    file_type       varchar(10)  NOT NULL,
    node_id         varchar(64)  NOT NULL,
    -- NULL bila download dari DMS gagal.
    file_base64     text,
    -- Hasil OCR satu dokumen apa adanya (node_id, filename, data, warnings, error).
    ocr_result      jsonb,
    -- Skor kemiripan wajah KTP vs SELFIE (0–1), diisi proses face matching.
    face_similarity numeric(5, 4),

    CONSTRAINT ocr_document_file_type_check
        CHECK (file_type IN ('selfie', 'ktp', 'npwp')),
    CONSTRAINT ocr_document_selfie_no_ocr
        CHECK (file_type <> 'selfie' OR ocr_result IS NULL),
    CONSTRAINT ocr_document_npwp_no_similarity
        CHECK (file_type <> 'npwp' OR face_similarity IS NULL),
    CONSTRAINT ocr_document_similarity_range
        CHECK (face_similarity BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS ocr_document_nomor_dokumen_idx ON ocr_document (nomor_dokumen);
CREATE INDEX IF NOT EXISTS ocr_document_hit_at_idx ON ocr_document (hit_at);

-- Similarity berlaku per nomor dokumen: KTP dan SELFIE dengan nomor dokumen yang sama
-- selalu diberi skor yang sama, NPWP tetap NULL. Kembalikan jumlah baris yang diubah.
CREATE OR REPLACE FUNCTION set_face_similarity(p_nomor_dokumen varchar, p_score numeric)
RETURNS integer
LANGUAGE sql
AS $$
    WITH updated AS (
        UPDATE ocr_document
           SET face_similarity = p_score
         WHERE nomor_dokumen = p_nomor_dokumen
           AND file_type IN ('ktp', 'selfie')
        RETURNING 1
    )
    SELECT count(*)::integer FROM updated;
$$;
