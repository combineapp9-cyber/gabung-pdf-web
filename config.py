import os
import re
import json
from pathlib import Path

# ======================== PENGATURAN ========================
APP_NAME = "Combine PDF Dealer"
KATA_KUNCI_SIRKULER = "sirkuler"
URUTAN = ["INVOICE", "REPORT", "EMAIL"]
NAMA_FOLDER_HASIL = "HASIL_COMPILE"

# ---------- pengaturan CEK INVOICE ----------
MAX_HALAMAN_DICEK = 4      
ZOOM_RENDER = 2.5          
PEMBACAAN_ULANG = True     
ZOOM_ULANG = 3.0           
TEXT_SCORE = 0.4           
AMBANG_YAKIN = 0.90        
NAMA_FILE_DEBUG = "DEBUG_BACA_INVOICE.txt"
AMBANG_SKOR = 4            
MIN_NOMINAL = 1000         

KW_TOTAL = ("grand total", "total tagihan", "total pembayaran", "total bayar",
            "jumlah tagihan", "jumlah pembayaran", "jumlah bayar", "yang harus dibayar",
            "total invoice", "total amount", "amount due", "nominal", "total", "jumlah")
KW_TERBILANG = r"(?:terbilang|dibilang|dengan huruf|in words|say)"
KW_ABAIKAN_TANGGAL = ("jatuh tempo", "due date", "paling lambat", "batas", "periode")
KW_TANGGAL_TTD = ("tanggal", "tgl", "date", "ditandatangani", "dibuat")
KW_NO_INVOICE = (r"(?:no\.?\s*invoice|nomor\s*invoice|invoice\s*no\.?|no\.?\s*faktur|"
                 r"nomor\s*faktur|no\.?\s*inv\b|\binv[/.\-]|[/.\-]inv\b)")
KW_BUKAN_NO_INVOICE = ("perjanjian", "kontrak", "spk", "faktur pajak", "npwp", "rekening")

W = dict(
    bg="#F3F5F9", kartu="#FFFFFF", header="#0F2A4A", teks="#1F2937",
    abu="#6B7280", garis="#D9DEE7", biru="#1F6FEB", biru_hover="#1A5FCC",
    hijau="#1E8E3E", hijau_muda="#E6F4EA",
    merah="#D93025", merah_muda="#FCE8E6", oranye="#B45309",
)

MAP_JENIS = {
    "INVOICE": "INVOICE", "INV": "INVOICE", "INVOCE": "INVOICE", "INVO": "INVOICE", "INVOICEE": "INVOICE",
    "REPORT": "REPORT",   "LAP": "REPORT", "LAPORAN": "REPORT", "REPORTT": "REPORT", "REP": "REPORT",
    "EMAIL": "EMAIL",     "MAIL": "EMAIL", "EMAILL": "EMAIL"
}

POLA = re.compile(
    r"^(?:(?P<kode>\d+)\s*-\s*)?"                      # [Kode Dealer] - (SEKARANG OPSIONAL)
    r"(?P<nama>.+?)\s+"                                # Nama dealer
    r"(?P<jenis>INVOICE|INV|INVOCE|INVO|INVOICEE|"     # Jenis dokumen (termasuk toleransi typo)
    r"REPORT|REP|REPORTT|LAP|LAPORAN|"
    r"EMAIL|MAIL|EMAILL)\b"
    r"(?P<sisa>.*)\.pdf$",
    re.IGNORECASE,
)

def file_config():
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / "GabungPDF"
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"

def baca_folder_terakhir():
    try:
        return json.loads(file_config().read_text(encoding="utf-8")).get("folder", "")
    except Exception:
        return ""

def simpan_folder_terakhir(folder):
    try:
        file_config().write_text(json.dumps({"folder": folder}), encoding="utf-8")
    except Exception:
        pass