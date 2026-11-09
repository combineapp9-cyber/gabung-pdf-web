import difflib
import os
import re
import statistics
import sys
from collections import defaultdict, namedtuple
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from config import *

# ----------------------- LOGIKA UTAMA -----------------------
def bersihkan_nama(teks):
    teks = re.sub(r'[<>:"/\\|?*]', "", teks)
    return re.sub(r"\s+", " ", teks).strip()

def norm(teks):
    return re.sub(r"\s+", " ", teks).strip().upper()

def norm_nominal(teks):
    return teks.replace(" ", "")

def beda(items, kunci, normal):
    grup = {}
    for it in items:
        g = grup.setdefault(normal(it[kunci]), {"asli": it[kunci], "jenis": []})
        g["jenis"].append(it["jenis"])
    if len(grup) <= 1:
        return None
    return " vs ".join(
        f"{g['asli']} ({', '.join(sorted(set(g['jenis']), key=URUTAN.index))})"
        for g in grup.values()
    )

def proses(folder_input, log, status_cek=None):
    folder_input = Path(folder_input)
    folder_output = folder_input / NAMA_FOLDER_HASIL
    folder_output.mkdir(parents=True, exist_ok=True)

    semua_pdf = [p for p in folder_input.rglob("*.pdf") if folder_output not in p.parents]
    if not semua_pdf:
        raise RuntimeError("Tidak ada file PDF di folder ini.")

    sirkuler = [p for p in semua_pdf if KATA_KUNCI_SIRKULER in p.name.lower()]
    if not sirkuler:
        raise RuntimeError("File Sirkuler tidak ditemukan.\n"
                           "Pastikan nama file mengandung kata 'Sirkuler'.")
    if len(sirkuler) > 1:
        log("Ada lebih dari satu file Sirkuler:", "warn")
        for p in sirkuler:
            log(f"    - {p.name}", "warn")
        log(f"    yang dipakai: {sirkuler[0].name}\n", "warn")
    file_sirkuler = sirkuler[0]
    log(f"Sirkuler : {file_sirkuler.name}\n", "head")

    data = defaultdict(list)
    tidak_dikenali = []
    for p in semua_pdf:
        if p == file_sirkuler:
            continue
        m = POLA.match(p.name)
        if not m:
            tidak_dikenali.append(p.name)
            continue
            
        # Standarisasi jenis dokumen (misal: "INV" menjadi "INVOICE")
        jenis_raw = m.group("jenis").upper()
        jenis_standar = MAP_JENIS.get(jenis_raw, jenis_raw)
        
        # Ekstrak periode & nominal secara opsional dari sisa string (untuk fitur OCR)
        sisa = m.group("sisa")
        periode = ""
        nominal = ""
        m_per = re.search(r"([A-Za-z]+\s*20\d{2})", sisa)
        if m_per: periode = m_per.group(1)
        
        m_nom = re.search(r"\(([\d.,]+)\)", sisa)
        if m_nom: nominal = m_nom.group(1)

        kode_raw = m.group("kode")
        nama_raw = m.group("nama").strip()
        
        # Kunci grup: kalau kode tidak ada, kelompokkan berdasarkan nama dealernya
        kunci_grup = kode_raw if kode_raw else norm(nama_raw)

        data[kunci_grup].append(dict(
            kode=kode_raw,       # Simpan kode asli (bisa bernilai None)
            jenis=jenis_standar, 
            nama=nama_raw,
            periode=periode, 
            nominal=nominal,
            sisa=sisa.strip(),
            path=p
        ))

    berhasil, dilewati = 0, []
    for kode in sorted(data):
        items = data[kode]
        files = defaultdict(list)
        for it in items:
            files[it["jenis"]].append(it["path"])

        alasan = None
        kd = items[0]["kode"]
        nm = items[0]["nama"]
        label = f"{kd} - {nm}" if kd else nm
        
        # SEKARANG HANYA MEMVALIDASI NAMA DEALER
        # Periode dan nominal diabaikan jika berbeda antar file report/invoice/email
        txt_nama = beda(items, "nama", norm)
        if txt_nama:
            alasan = f"nama dealer tidak sama: {txt_nama}"
            label = kode
            
        if not alasan:
            kurang = [j for j in URUTAN if j not in files]
            dobel = [j for j in URUTAN if len(files.get(j, [])) > 1]
            if kurang:
                ada = ", ".join(j for j in URUTAN if j in files)
                alasan = f"dokumen belum ada: {', '.join(kurang)} (yang ada: {ada})"
            elif dobel:
                alasan = f"file dobel: {', '.join(dobel)}"

        # ... (kode cek OCR dan pembuatan PDF tetap sama) ...
        if not alasan and status_cek:
            for p in files.get("INVOICE", []):
                st = status_cek.get(str(p))
                if st and st["mtime"] == p.stat().st_mtime and st["status"] == "SALAH":
                    alasan = f"invoice salah: {st['alasan']}"
        if alasan:
            dilewati.append(f"{label}: {alasan}")
            log(f"[DILEWATI] {dilewati[-1]}", "skip")
            continue


        try:
            writer = PdfWriter()
            for f in [files[j][0] for j in URUTAN] + [file_sirkuler]:
                reader = PdfReader(str(f))
                if reader.is_encrypted:
                    reader.decrypt("")
                for halaman in reader.pages:
                    writer.add_page(halaman)

            ref = next(i for i in items if i["jenis"] == "INVOICE")
            
            kd_ref = ref["kode"]
            prefix = f"{kd_ref} - " if kd_ref else ""
            sisa_teks = f" {ref['sisa']}" if ref['sisa'].strip() else ""
            
            nama_output = bersihkan_nama(
                f"{prefix}{ref['nama']} COMPILE{sisa_teks}"
            ).strip() + ".pdf"
            
            with open(folder_output / nama_output, "wb") as out:
                writer.write(out)

            berhasil += 1
            log(f"[OK]       {nama_output}  ({len(writer.pages)} halaman)", "ok")
        except PermissionError:
            dilewati.append(f"{label}: file hasil sedang dibuka di program lain, tutup dulu lalu ulangi")
            log(f"[DILEWATI] {dilewati[-1]}", "skip")
        except Exception as e:
            dilewati.append(f"{label}: gagal diproses ({e})")
            log(f"[DILEWATI] {dilewati[-1]}", "skip")

    log("\n" + "=" * 60, "info")
    log(f"Berhasil digabung : {berhasil} dealer", "ok_b")
    log(f"Dilewati          : {len(dilewati)} dealer", "skip_b")
    for d in dilewati:
        log(f"    - {d}", "skip")
    if tidak_dikenali:
        log(f"\nFile dengan nama tidak sesuai pola ({len(tidak_dikenali)}), tidak diproses:", "warn")
        for n in tidak_dikenali:
            log(f"    - {n}", "warn")
    return berhasil, dilewati, len(tidak_dikenali), folder_output

# ----------------------- CEK INVOICE (OCR offline) -----------------------
Baris = namedtuple("Baris", "teks conf")

BULAN = {"JANUARI": 1, "FEBRUARI": 2, "MARET": 3, "APRIL": 4, "MEI": 5, "JUNI": 6,
         "JULI": 7, "AGUSTUS": 8, "SEPTEMBER": 9, "OKTOBER": 10, "NOVEMBER": 11,
         "DESEMBER": 12, "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "JUN": 6, "JUL": 7, 
         "AGU": 8, "AGT": 8, "AGS": 8, "SEP": 9, "SEPT": 9, "OKT": 10, "NOP": 11, 
         "NOV": 11, "DES": 12, "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "MAY": 5, 
         "JUNE": 6, "JULY": 7, "AUGUST": 8, "OCTOBER": 10, "DECEMBER": 12, "AUG": 8, 
         "OCT": 10, "DEC": 12}
NAMA_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
              "Agustus", "September", "Oktober", "November", "Desember"]

KATA_PENTING = set("""invoice faktur tagihan total jumlah terbilang rupiah rp tanggal
    pembayaran periode dealer kode bank hormat""".split()) | {b.lower() for b in BULAN}

SATUAN = {"nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
          "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9}
SKALA = {"ribu": 1_000, "juta": 1_000_000, "miliar": 1_000_000_000,
         "milyar": 1_000_000_000, "triliun": 1_000_000_000_000}
SKALA_SE = {"puluh", "belas", "ratus"} | set(SKALA)
VOCAB = set(SATUAN) | {"belas", "puluh", "ratus"} | set(SKALA) | \
    {"se" + k for k in SKALA_SE}
STOP_TERBILANG = {"rupiah", "rp", "idr", "dan", "sebesar", "sejumlah", "adalah",
                  "terbilang", "dengan", "huruf", "say", "in", "words"}

POLA_RP = re.compile(r"(?<![A-Za-z])(?:rp|idr)\.?\s*(\d[\d.,]*)", re.I)
POLA_GRUP = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?)(?![\d])")
POLA_TANGGAL = re.compile(r"(?<!\d)(\d{1,2})\s*[-/ .]?\s*([A-Za-z0]{3,10})\s*[-/ ,.]?\s*(20\d{2})(?!\d)")
POLA_TANGGAL_ANGKA = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](20\d{2})(?!\d)")

_MESIN_OCR = {}
_CACHE_CEK = {}

def format_rupiah(n):
    return f"{n:,}".replace(",", ".")

def parse_rupiah(s):
    if s is None:
        return None
    s = s.strip().rstrip(".,-").strip()
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+[.,]\d{1,2}", s):
        s = re.sub(r"[.,]\d{1,2}$", "", s)
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})*", s) or re.fullmatch(r"\d+", s):
        return int(re.sub(r"[.,]", "", s))
    return None

def cari_nominal(teks):
    hasil = []
    for pola in (POLA_RP, POLA_GRUP):
        for m in pola.finditer(teks):
            n = parse_rupiah(m.group(1))
            if n is not None and n >= MIN_NOMINAL and n not in hasil:
                hasil.append(n)
    return hasil

def bulan_dari_teks(tok):
    t = tok.upper().replace("0", "O")
    if t in BULAN:
        return BULAN[t]
    mirip = difflib.get_close_matches(t, list(BULAN), n=1, cutoff=0.8)
    return BULAN[mirip[0]] if mirip else None

def cari_tanggal(teks):
    hasil = []
    for m in POLA_TANGGAL.finditer(teks):
        b = bulan_dari_teks(m.group(2))
        if b and 1 <= int(m.group(1)) <= 31:
            hasil.append((int(m.group(3)), b, int(m.group(1)), m.start()))
    for m in POLA_TANGGAL_ANGKA.finditer(teks):
        d, b = int(m.group(1)), int(m.group(2))
        if 1 <= d <= 31 and 1 <= b <= 12:
            hasil.append((int(m.group(3)), b, d, m.start()))
    return hasil

def terbilang_ke_angka(teks):
    kata = re.findall(r"[a-z]+", teks.lower())
    if "rupiah" in kata:
        i = kata.index("rupiah")
        kata = kata[:i] if i > 0 else kata[1:]
    urut, asing = [], []
    for w in kata:
        if w in STOP_TERBILANG:
            continue
        if w not in VOCAB:
            mirip = difflib.get_close_matches(w, VOCAB, n=1, cutoff=0.75)
            if not mirip:
                asing.append(w)
                continue
            w = mirip[0]
        if w.startswith("se") and w[2:] in SKALA_SE:
            urut += ["satu", w[2:]]
        else:
            urut.append(w)
    total = blok = cur = 0
    for w in urut:
        if w in SATUAN:
            cur = SATUAN[w]
        elif w == "belas":
            blok += cur + 10
            cur = 0
        elif w == "puluh":
            blok += cur * 10
            cur = 0
        elif w == "ratus":
            blok += cur * 100
            cur = 0
        elif w in SKALA:
            blok += cur
            cur = 0
            total += (blok or 1) * SKALA[w]
            blok = 0
    total += blok + cur
    return (total if urut else 0), asing

def bulan_berikutnya(tahun, bulan):
    return (tahun + 1, 1) if bulan == 12 else (tahun, bulan + 1)

def label_bulan(tahun, bulan):
    return f"{NAMA_BULAN[bulan]} {tahun}"

def periode_dari_nama(teks):
    if teks is None:
        return None
    m = re.search(r"([A-Za-z]+)\s*(20\d{2})", teks)
    if m:
        b = bulan_dari_teks(m.group(1))
        if b:
            return int(m.group(2)), b
    return None

def impor_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz

def siapkan_ocr():
    if "mesin" in _MESIN_OCR:
        return _MESIN_OCR["mesin"]
    versi = f"{sys.version_info.major}.{sys.version_info.minor}"
    try:
        impor_pymupdf()
        import numpy  # noqa: F401
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        masalah = (f"Library untuk Cek Invoice belum terpasang ({e.name}).\n\n"
                   "Buka Command Prompt lalu jalankan:\n"
                   "    pip install pymupdf rapidocr_onnxruntime\n\n")
        if sys.version_info >= (3, 13):
            masalah += (f"Perhatian: Python Anda {versi}. rapidocr_onnxruntime baru "
                        "mendukung Python 3.12 ke bawah, jadi pasang Python 3.12 dulu.")
        raise RuntimeError(masalah)
    _MESIN_OCR["mesin"] = RapidOCR(max_side_len=3300)
    return _MESIN_OCR["mesin"]

def susun_baris(hasil):
    item = []
    for box, teks, conf in hasil:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        item.append(dict(x=min(xs), yc=(min(ys) + max(ys)) / 2, h=max(ys) - min(ys),
                         t=str(teks).strip(), c=float(conf)))
    if not item:
        return []
    item.sort(key=lambda i: i["yc"])
    tinggi = statistics.median(i["h"] for i in item) or 10
    kelompok = []
    for it in item:
        if kelompok and abs(it["yc"] - kelompok[-1]["yc"]) <= tinggi * 0.6:
            k = kelompok[-1]
            k["items"].append(it)
            k["yc"] = sum(i["yc"] for i in k["items"]) / len(k["items"])
        else:
            kelompok.append(dict(yc=it["yc"], items=[it]))
    baris = []
    for k in kelompok:
        k["items"].sort(key=lambda i: i["x"])
        teks = " ".join(i["t"] for i in k["items"] if i["t"])
        if teks:
            baris.append(Baris(teks, statistics.median(i["c"] for i in k["items"])))
    return baris

def skor_baris(baris):
    kata = set(re.findall(r"[a-z]+", " ".join(b.teks for b in baris).lower()))
    return len(kata & KATA_PENTING)

def porsi_mendatar(hasil):
    n = mendatar = 0
    for box, teks, _ in hasil:
        if len(str(teks).strip()) < 3:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        n += 1
        mendatar += (max(xs) - min(xs)) >= (max(ys) - min(ys))
    return mendatar / n if n else 0.0

def siapkan_gambar(img_rgb, mode):
    import numpy as np
    if mode == "hitam":
        v = img_rgb.max(axis=2).astype(np.float32)
        lo, hi = np.percentile(v[::4, ::4], (0.5, 99))
        if hi - lo > 30:
            v = np.clip((v - lo) * 255.0 / (hi - lo), 0, 255)
        g = v.astype(np.uint8)
        return np.ascontiguousarray(np.dstack([g, g, g]))
    return np.ascontiguousarray(img_rgb[:, :, ::-1])

def halaman_hasil_scan(hal):
    pymupdf = impor_pymupdf()
    luas = hal.rect.width * hal.rect.height
    try:
        for info in hal.get_image_info():
            r = pymupdf.Rect(info["bbox"])
            if r.width * r.height > 0.6 * luas:
                return True
    except Exception:
        pass
    return False

def baca_halaman(hal, mesin, zoom=ZOOM_RENDER, mode="normal"):
    import numpy as np
    pymupdf = impor_pymupdf()

    kata = hal.get_text("words") or []
    if len(kata) >= 15 and not halaman_hasil_scan(hal):
        hasil = [([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], w, 1.0)
                 for x0, y0, x1, y1, w, *_ in kata if w.strip()]
        baris = susun_baris(hasil)
        if skor_baris(baris) >= AMBANG_SKOR and porsi_mendatar(hasil) >= 0.6:
            return baris, False

    pix = hal.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    img = siapkan_gambar(img[:, :, :3], mode)

    def coba(k):
        gambar = np.ascontiguousarray(np.rot90(img, k))
        hasil, _ = mesin(gambar, use_cls=False, text_score=TEXT_SCORE,
                         box_thresh=0.5, unclip_ratio=1.6)
        hasil = hasil or []
        baris = susun_baris(hasil)
        mendatar = porsi_mendatar(hasil)
        skor = skor_baris(baris)
        baik = skor >= AMBANG_SKOR and mendatar >= 0.6
        rata = sum(b.conf for b in baris) / len(baris) if baris else 0
        return (baik, skor, rata), baris, mendatar

    nilai, baris, mendatar = coba(0)
    terbaik = (nilai, baris)
    if not nilai[0]:
        urutan = (1, 3, 2) if mendatar < 0.5 else (2, 1, 3)
        for k in urutan:
            nilai, baris, _ = coba(k)
            if nilai > terbaik[0]:
                terbaik = (nilai, baris)
            if nilai[0]:
                break
    return terbaik[1], True

_KELAS = {}

def kelas_kata(w):
    if w not in _KELAS:
        mirip = lambda a, b: difflib.SequenceMatcher(None, a, b).ratio()
        if w in VOCAB:
            r = ("angka", w)
        elif w == "rupiah" or (len(w) >= 5 and mirip(w, "rupiah") >= 0.75):
            r = ("rupiah", w)
        elif w == "terbilang" or (len(w) >= 7 and mirip(w, "terbilang") >= 0.75):
            r = ("kunci", w)
        else:
            dekat = difflib.get_close_matches(w, VOCAB, n=1, cutoff=0.8) if len(w) >= 4 else []
            r = ("angka", dekat[0]) if dekat else ("lain", w)
        _KELAS[w] = r
    return _KELAS[w]

def cari_terbilang(baris):
    urut = []
    for i, b in enumerate(baris):
        for w in re.findall(r"[A-Za-z]+", b.teks):
            k, kata = kelas_kata(w.lower())
            urut.append((k, kata, i))

    def jalan(mulai, arah):
        kata, asing, idx, j = [], [], [], mulai
        while 0 <= j < len(urut):
            k, w, li = urut[j]
            sebelah = urut[j + arah][0] if 0 <= j + arah < len(urut) else None
            if k == "angka":
                kata.append(w)
                idx.append(li)
            elif k == "lain" and kata and sebelah == "angka":
                asing.append(w)
                idx.append(li)
            else:
                break
            j += arah
        if arah < 0:
            kata.reverse()
        return kata, asing, idx

    kandidat = []
    for j, (k, _, _) in enumerate(urut):
        if k == "rupiah":
            kandidat.append(jalan(j - 1, -1))
        elif k == "kunci":
            kandidat.append(jalan(j + 1, +1))
    kandidat = [c for c in kandidat if c[0]]
    if not kandidat:
        return None
    kata, asing, idx = max(kandidat, key=lambda c: len(c[0]))
    nilai, _ = terbilang_ke_angka(" ".join(kata))
    return dict(nilai=nilai, asing=asing, conf=min(baris[i].conf for i in idx),
                teks=" ".join(kata))

def ekstrak(baris):
    baris = [b for b in baris if not re.match(r"^\s*kode\b", b.teks, re.I)]

    angka_kw, angka_semua = {}, {}
    for i, b in enumerate(baris):
        nilai = cari_nominal(b.teks)
        for n in nilai:
            angka_semua[n] = max(angka_semua.get(n, 0), b.conf)
        if any(k in b.teks.lower() for k in KW_TOTAL):
            kandidat, conf = nilai, b.conf
            if not kandidat and i + 1 < len(baris):
                kandidat, conf = cari_nominal(baris[i + 1].teks), baris[i + 1].conf
            for n in kandidat:
                angka_kw[n] = max(angka_kw.get(n, 0), conf)

    terbilang = cari_terbilang(baris)

    kandidat = []
    for b in baris:
        rendah = b.teks.lower()
        if any(k in rendah for k in KW_ABAIKAN_TANGGAL):
            continue
        for y, m, d, awal in cari_tanggal(b.teks):
            if re.search(r"[A-Za-z]{3,}\s*,\s*$", b.teks[:awal]):
                jenis = 3
            elif any(k in rendah for k in KW_TANGGAL_TTD):
                jenis = 2
            else:
                jenis = 1
            kandidat.append(dict(jenis=jenis, y=y, m=m, d=d, conf=b.conf))
    tanggal = None
    if kandidat:
        terbaik = max(k["jenis"] for k in kandidat)
        grup = [k for k in kandidat if k["jenis"] == terbaik]
        tanggal = dict(grup[-1], ambigu=len({(k["y"], k["m"]) for k in grup}) > 1)

    tahun_no = None
    for b in baris:
        rendah = b.teks.lower()
        if any(k in rendah for k in KW_BUKAN_NO_INVOICE):
            continue
        m = re.search(KW_NO_INVOICE, b.teks, re.I)
        if m:
            t = re.search(r"(?<!\d)(20\d{2})(?!\d)", b.teks[m.start():])
            if t:
                tahun_no = dict(tahun=int(t.group(1)), conf=b.conf)
                break
    return dict(angka_kw=angka_kw, angka_semua=angka_semua, terbilang=terbilang,
                tanggal=tanggal, tahun_no=tahun_no)

def baca_invoice(path, mesin, zoom=ZOOM_RENDER, mode="normal"):
    pymupdf = impor_pymupdf()
    doc = pymupdf.open(str(path))
    try:
        if doc.needs_pass and not doc.authenticate(""):
            raise RuntimeError("PDF terkunci password")
        semua, pakai_ocr = [], False
        for i in range(min(len(doc), MAX_HALAMAN_DICEK)):
            baris, ocr = baca_halaman(doc[i], mesin, zoom, mode)
            pakai_ocr = pakai_ocr or ocr
            semua += baris
            e = ekstrak(semua)
            if (e["angka_kw"] or e["angka_semua"]) and e["terbilang"] and e["tanggal"]:
                break
        return semua, pakai_ocr
    finally:
        doc.close()

def analisis(baris, periode_nama, nominal_nama):
    salah, ragu = [], []
    if not baris or skor_baris(baris) < 2:
        return dict(salah=[], ragu=["teks tidak terbaca / format tidak dikenali "
                                    "(halaman buram atau kosong)"], ringkas="", baris=baris)
    e = ekstrak(baris)
    f_nom = parse_rupiah(nominal_nama)
    periode = periode_dari_nama(periode_nama)
    if f_nom is None:
        ragu.append(f"nominal pada nama file ({nominal_nama}) tidak bisa dibaca")
    if periode is None:
        ragu.append(f"periode pada nama file ({periode_nama}) tidak dikenali")

    if f_nom is not None:
        kw, semua = e["angka_kw"], e["angka_semua"]
        if kw:
            if f_nom not in kw:
                a = max(kw)
                pesan = (f"nominal angka di invoice {format_rupiah(a)} "
                         f"≠ nama file {format_rupiah(f_nom)}")
                if kw[a] >= AMBANG_YAKIN:
                    salah.append(("angka", pesan))
                else:
                    ragu.append(pesan)
        elif semua:
            if f_nom not in semua:
                terbaca = ", ".join(format_rupiah(n) for n in sorted(semua)[-3:])
                ragu.append(f"nominal nama file {format_rupiah(f_nom)} tidak ditemukan "
                            f"di invoice (angka terbaca: {terbaca})")
        else:
            ragu.append("nominal angka di invoice tidak ditemukan")

        t = e["terbilang"]
        if not t or t["nilai"] == 0:
            ragu.append("tulisan terbilang tidak ditemukan / tidak terbaca")
        elif t["nilai"] != f_nom:
            pesan = (f"terbilang bernilai {format_rupiah(t['nilai'])} "
                     f"≠ nama file {format_rupiah(f_nom)}")
            if t["asing"] or t["conf"] < AMBANG_YAKIN:
                ragu.append(pesan + " (tulisan kurang jelas)")
            else:
                salah.append(("terbilang", pesan))

    tgl = e["tanggal"]
    if periode:
        harus = bulan_berikutnya(*periode)
        if not tgl:
            ragu.append("tanggal tanda tangan tidak ditemukan (tertutup stempel / buram?)")
        elif (tgl["y"], tgl["m"]) != harus:
            pesan = (f"tanggal tanda tangan {tgl['d']:02d} {label_bulan(tgl['y'], tgl['m'])} "
                     f"seharusnya {label_bulan(*harus)} (periode {label_bulan(*periode)})")
            if tgl["jenis"] == 3 and not tgl["ambigu"] and tgl["conf"] >= AMBANG_YAKIN:
                salah.append(("tanggal", pesan))
            elif tgl["jenis"] == 3:
                ragu.append(pesan + " (tulisan kurang jelas)")
            else:
                ragu.append("tanggal di blok tanda tangan tidak terbaca (tertutup stempel / "
                            f"buram?); tanggal lain yang terbaca: {tgl['d']:02d} "
                            f"{label_bulan(tgl['y'], tgl['m'])}")

        tn = e["tahun_no"]
        if tn:
            boleh = {periode[0]} | ({tgl["y"]} if tgl else set())
            if tn["tahun"] not in boleh:
                pesan = (f"tahun pada nomor invoice ({tn['tahun']}) tidak cocok "
                         f"dengan periode {periode[0]}")
                if tn["conf"] >= AMBANG_YAKIN:
                    salah.append(("tahun", pesan))
                else:
                    ragu.append(pesan)

    ringkas = ""
    if not salah and not ragu:
        ringkas = (f"nominal {format_rupiah(f_nom)} cocok (angka = terbilang = nama file); "
                   f"tanda tangan {tgl['d']:02d} {label_bulan(tgl['y'], tgl['m'])} "
                   f"(periode {label_bulan(*periode)})")
    return dict(salah=salah, ragu=ragu, ringkas=ringkas, baris=baris)

def periksa_invoice(path, periode_nama, nominal_nama, mesin):
    baris1, pakai_ocr = baca_invoice(path, mesin)
    r1 = analisis(baris1, periode_nama, nominal_nama)
    final = r1
    if (r1["salah"] or r1["ragu"]) and pakai_ocr and PEMBACAAN_ULANG:
        baris2, _ = baca_invoice(path, mesin, ZOOM_ULANG, "hitam")
        r2 = analisis(baris2, periode_nama, nominal_nama)
        if not r2["salah"] and not r2["ragu"]:
            final = r2
        else:
            set2 = set(r2["salah"])
            pasti = [v for v in r1["salah"] if v in set2]
            tak_pasti = [v[1] + " (hasil baca tidak konsisten)"
                         for v in r1["salah"] + r2["salah"] if v not in pasti]
            terbaik = min((r1, r2), key=lambda r: len(r["salah"]) + len(r["ragu"]))
            ragu = list(dict.fromkeys(terbaik["ragu"] + tak_pasti))
            final = dict(salah=pasti, ragu=ragu, ringkas="", baris=terbaik["baris"])

    teks = [f"{b.conf:.2f} | {b.teks}" for b in final["baris"]]
    if final["salah"]:
        status = "SALAH"
        alasan = [v[1] for v in final["salah"]] + final["ragu"]
    elif final["ragu"]:
        status, alasan = "CEK MANUAL", final["ragu"]
    else:
        status, alasan = "OK", []
    return dict(status=status, alasan=alasan, ringkas=final["ringkas"], teks=teks)

def tulis_debug(folder_output, masalah):
    try:
        folder_output.mkdir(parents=True, exist_ok=True)
        isi = []
        for nama, r in masalah:
            isi.append("=" * 70)
            isi.append(f"{nama}\nSTATUS: {r['status']}\nALASAN: {'; '.join(r['alasan'])}")
            isi.append("-" * 70 + "\n(keyakinan | teks yang terbaca, per baris)")
            isi += r["teks"][:150]
            isi.append("")
        p = folder_output / NAMA_FILE_DEBUG
        p.write_text("\n".join(isi), encoding="utf-8")
        return p
    except Exception:
        return None

def cek_semua(folder_input, log, progres=lambda teks: None):
    mesin = siapkan_ocr()
    folder_input = Path(folder_input)
    folder_output = folder_input / NAMA_FOLDER_HASIL
    daftar = []
    for p in sorted(folder_input.rglob("*.pdf")):
        if folder_output in p.parents:
            continue
        m = POLA.match(p.name)
        if m and m["jenis"].upper() in ("INVOICE", "INV"):
            daftar.append((p, m))
    if not daftar:
        raise RuntimeError("Tidak ada file INVOICE (sesuai pola nama) di folder ini.")

    log(f"Memeriksa {len(daftar)} invoice (sekitar 4-10 detik per invoice)...\n", "head")
    hasil, hitung, masalah = {}, {"OK": 0, "CEK MANUAL": 0, "SALAH": 0}, []
    for n, (p, m) in enumerate(daftar, 1):
        progres(f"Memeriksa invoice {n}/{len(daftar)}: {p.name}")
        mtime = p.stat().st_mtime
        kunci = (str(p), mtime)
        
        # Ekstrak periode & nominal secara opsional dari sisa string (untuk fitur OCR)
        sisa = m.group("sisa")
        periode = ""
        nominal = ""
        m_per = re.search(r"([A-Za-z]+\s*20\d{2})", sisa)
        if m_per: periode = m_per.group(1)
        m_nom = re.search(r"\(([\d.,]+)\)", sisa)
        if m_nom: nominal = m_nom.group(1)

        try:
            if kunci not in _CACHE_CEK:
                _CACHE_CEK[kunci] = periksa_invoice(p, periode, nominal, mesin)
            r = _CACHE_CEK[kunci]
        except Exception as ex:
            r = dict(status="CEK MANUAL", ringkas="", alasan=[f"gagal dibaca ({ex})"], teks=[])
        hasil[str(p)] = dict(status=r["status"], alasan="; ".join(r["alasan"]), mtime=mtime)
        hitung[r["status"]] += 1

        kd = m.group("kode")
        nm = m.group("nama").strip()
        label = f"{kd} - {nm}" if kd else nm
        if r["status"] == "OK":
            log(f"[✓ OK]          {label} : {r['ringkas']}", "ok")
        elif r["status"] == "CEK MANUAL":
            log(f"[⚠ CEK MANUAL]  {label} : {'; '.join(r['alasan'])}", "warn")
            masalah.append((p.name, r))
        else:
            log(f"[✕ SALAH]       {label} : {'; '.join(r['alasan'])}", "skip")
            masalah.append((p.name, r))

    log("\n" + "=" * 60, "info")
    log(f"✓ OK           : {hitung['OK']} invoice", "ok_b")
    log(f"⚠ CEK MANUAL   : {hitung['CEK MANUAL']} invoice (tetap digabung, mohon cek sendiri)", "warn_b")
    log(f"✕ SALAH        : {hitung['SALAH']} invoice (akan DILEWATI saat PROSES GABUNG)", "skip_b")
    if masalah:
        d = tulis_debug(folder_output, masalah)
        if d:
            log(f"\nTeks hasil baca invoice yang bermasalah disimpan di:\n    {d}", "info")
    return hasil, hitung["OK"], hitung["CEK MANUAL"], hitung["SALAH"]