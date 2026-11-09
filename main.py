import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from config import APP_NAME, W, baca_folder_terakhir, simpan_folder_terakhir
from backend import proses, cek_semua

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.geometry("880x700")
        root.minsize(740, 580)
        try:                                   
            root.state("zoomed")               
        except tk.TclError:
            try:
                root.attributes("-zoomed", True)   
            except tk.TclError:
                pass
        root.configure(bg=W["bg"])
        self.antrian = queue.Queue()
        self.folder_hasil = None
        self.hasil_cek = {}          
        self.folder_cek = None

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Biru.Horizontal.TProgressbar", troughcolor="#E5E9F0",
                        background=W["biru"], bordercolor=W["bg"],
                        lightcolor=W["biru"], darkcolor=W["biru"], thickness=6)

        # --- header ---
        head = tk.Frame(root, bg=W["header"])
        head.pack(fill="x")
        tk.Label(head, text=APP_NAME, bg=W["header"], fg="white",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=24, pady=(16, 0))
        tk.Label(head, text="Gabungkan Invoice → Report → Email → Sirkuler untuk setiap dealer",
                 bg=W["header"], fg="#B8C7DD", font=("Segoe UI", 10)).pack(
                     anchor="w", padx=24, pady=(2, 16))

        body = tk.Frame(root, bg=W["bg"])
        body.pack(fill="both", expand=True, padx=24, pady=18)

        # --- kartu folder ---
        k1 = self.kartu(body)
        k1.pack(fill="x")
        tk.Label(k1, text="Folder berisi PDF", bg=W["kartu"], fg=W["teks"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        baris = tk.Frame(k1, bg=W["kartu"])
        baris.pack(fill="x", pady=(8, 0))
        self.var_folder = tk.StringVar(value=baca_folder_terakhir())
        tk.Entry(baris, textvariable=self.var_folder, font=("Segoe UI", 10), relief="flat",
                 highlightthickness=1, highlightbackground=W["garis"],
                 highlightcolor=W["biru"], bg="white", fg=W["teks"]).pack(
                     side="left", fill="x", expand=True, ipady=7)
        self.tombol(baris, "Pilih Folder...", self.pilih_folder, "abu").pack(
            side="left", padx=(10, 0))

        # --- tombol aksi ---
        aksi = tk.Frame(body, bg=W["bg"])
        aksi.pack(fill="x", pady=(14, 0))
        self.btn_proses = self.tombol(aksi, "PROSES GABUNG", self.mulai_proses, "biru",
                                      padx=30, pady=11)
        self.btn_proses.pack(side="left")
        self.btn_buka = self.tombol(aksi, "Buka Folder Hasil", self.buka_hasil, "abu",
                                    pady=11)
        self.btn_buka.config(state="disabled")
        self.btn_buka.pack(side="left", padx=(10, 0))
        self.btn_cek = self.tombol(aksi, "Cek Invoice", self.mulai_cek, "abu", pady=11)
        self.btn_cek.pack(side="left", padx=(10, 0))
        self.btn_bersih = self.tombol(aksi, "Bersihkan", self.bersihkan, "abu", pady=11)
        self.btn_bersih.pack(side="left", padx=(10, 0))

        self.var_abaikan_cek = tk.BooleanVar(value=True)     
        tk.Checkbutton(body, text="Abaikan cek invoice saat menggabung",
                       variable=self.var_abaikan_cek, bg=W["bg"], fg=W["teks"],
                       activebackground=W["bg"], activeforeground=W["teks"],
                       selectcolor="white", cursor="hand2", font=("Segoe UI", 10)
                       ).pack(anchor="w", pady=(10, 0))

        # --- kartu angka ---
        ring = tk.Frame(body, bg=W["bg"])
        ring.pack(fill="x", pady=(14, 0))
        ring.columnconfigure((0, 1), weight=1, uniform="k")
        self.lbl_ok = self.kartu_angka(ring, 0, "Berhasil digabung", W["hijau"], W["hijau_muda"])
        self.lbl_skip = self.kartu_angka(ring, 1, "Dilewati", W["merah"], W["merah_muda"])

        # --- status + progress ---
        self.var_status = tk.StringVar(value="Siap. Pilih folder lalu klik PROSES GABUNG.")
        self.lbl_status = tk.Label(body, textvariable=self.var_status, bg=W["bg"],
                                   fg=W["abu"], anchor="w", font=("Segoe UI", 10))
        self.lbl_status.pack(fill="x", pady=(12, 4))
        self.bar = ttk.Progressbar(body, mode="indeterminate",
                                   style="Biru.Horizontal.TProgressbar")
        self.bar.pack(fill="x")

        # --- rincian ---
        k2 = self.kartu(body)
        k2.pack(fill="both", expand=True, pady=(12, 0))
        tk.Label(k2, text="Rincian proses", bg=W["kartu"], fg=W["teks"],
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        isi = tk.Frame(k2, bg=W["kartu"])
        isi.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(isi)
        sb.pack(side="right", fill="y")
        self.kotak = tk.Text(isi, font=("Consolas", 10), wrap="word", state="disabled",
                             relief="flat", bg="white", fg=W["teks"], height=8,
                             highlightthickness=0, yscrollcommand=sb.set)
        self.kotak.pack(side="left", fill="both", expand=True)
        sb.config(command=self.kotak.yview)
        bold = ("Consolas", 10, "bold")
        self.kotak.tag_config("info", foreground=W["teks"])
        self.kotak.tag_config("head", foreground=W["biru"], font=bold)
        self.kotak.tag_config("ok", foreground=W["hijau"])
        self.kotak.tag_config("ok_b", foreground=W["hijau"], font=bold)
        self.kotak.tag_config("skip", foreground=W["merah"])
        self.kotak.tag_config("skip_b", foreground=W["merah"], font=bold)
        self.kotak.tag_config("warn", foreground=W["oranye"])
        self.kotak.tag_config("warn_b", foreground=W["oranye"], font=bold)

        self.root.after(100, self.cek_antrian)

    # --- komponen kecil ---
    def kartu(self, parent):
        return tk.Frame(parent, bg=W["kartu"], highlightthickness=1,
                        highlightbackground=W["garis"], padx=16, pady=14)

    def tombol(self, parent, teks, perintah, gaya="abu", padx=16, pady=8):
        bg, hover, fg = {"biru": (W["biru"], W["biru_hover"], "white"),
                         "abu": ("#E5E9F0", "#D5DBE5", W["teks"])}[gaya]
        b = tk.Button(parent, text=teks, command=perintah, bg=bg, fg=fg,
                      activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                      cursor="hand2", disabledforeground="#9CA3AF", padx=padx, pady=pady,
                      font=("Segoe UI", 10, "bold" if gaya == "biru" else "normal"))
        b.bind("<Enter>", lambda e: b.config(bg=hover) if str(b["state"]) == "normal" else None)
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    def kartu_angka(self, parent, kolom, judul, warna, muda):
        f = tk.Frame(parent, bg=muda, padx=18, pady=10)
        f.grid(row=0, column=kolom, sticky="ew", padx=(0, 8) if kolom == 0 else (8, 0))
        angka = tk.Label(f, text="–", bg=muda, fg=warna, font=("Segoe UI", 28, "bold"))
        angka.pack(anchor="w")
        tk.Label(f, text=judul, bg=muda, fg=warna, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        return angka

    # --- aksi ---
    def pilih_folder(self):
        awal = self.var_folder.get() or str(Path.home())
        f = filedialog.askdirectory(title="Pilih folder berisi PDF", initialdir=awal)
        if f:
            self.var_folder.set(os.path.normpath(f))

    def tulis_log(self, teks, level="info"):
        self.kotak.config(state="normal")
        self.kotak.insert("end", teks + "\n", level)
        self.kotak.see("end")
        self.kotak.config(state="disabled")

    def mulai_proses(self):
        folder = self.var_folder.get().strip().strip('"')
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning("Folder belum benar",
                                   "Pilih folder yang berisi PDF terlebih dahulu.")
            return
        simpan_folder_terakhir(folder)
        self.kotak.config(state="normal")
        self.kotak.delete("1.0", "end")
        self.kotak.config(state="disabled")
        self.lbl_ok.config(text="–")
        self.lbl_skip.config(text="–")
        self.folder_hasil = None
        self.set_tombol(True)
        self.lbl_status.config(fg=W["abu"])
        self.var_status.set("Sedang memproses, mohon tunggu...")
        self.bar.start(12)
        if self.var_abaikan_cek.get():
            status_cek = None          
        else:
            status_cek = self.hasil_cek if self.folder_cek == folder else None
        threading.Thread(target=self.kerja, args=(folder, status_cek), daemon=True).start()

    def kerja(self, folder, status_cek=None):
        try:
            hasil = proses(folder, lambda s, level="info": self.antrian.put(("log", (s, level))),
                           status_cek)
            self.antrian.put(("selesai", hasil))
        except Exception as e:
            self.antrian.put(("error", str(e)))

    def set_tombol(self, sibuk):
        s = "disabled" if sibuk else "normal"
        self.btn_proses.config(state=s)
        self.btn_cek.config(state=s)
        self.btn_bersih.config(state=s)
        self.btn_buka.config(state="disabled" if sibuk or not self.folder_hasil else "normal")

    def bersihkan(self):
        self.kotak.config(state="normal")
        self.kotak.delete("1.0", "end")
        self.kotak.config(state="disabled")
        self.lbl_ok.config(text="–")
        self.lbl_skip.config(text="–")
        self.lbl_status.config(fg=W["abu"])
        self.var_status.set("Siap. Pilih folder lalu klik PROSES GABUNG.")

    # --- Cek Invoice ---
    def mulai_cek(self):
        folder = self.var_folder.get().strip().strip('"')
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning("Folder belum benar",
                                   "Pilih folder yang berisi PDF terlebih dahulu.")
            return
        simpan_folder_terakhir(folder)
        self.kotak.config(state="normal")
        self.kotak.delete("1.0", "end")
        self.kotak.config(state="disabled")
        self.set_tombol(True)
        self.lbl_status.config(fg=W["abu"])
        self.var_status.set("Menyiapkan mesin OCR, mohon tunggu...")
        self.bar.start(12)
        threading.Thread(target=self.kerja_cek, args=(folder,), daemon=True).start()

    def kerja_cek(self, folder):
        try:
            hasil = cek_semua(
                folder,
                lambda s, level="info": self.antrian.put(("log", (s, level))),
                lambda t: self.antrian.put(("progres", t)))
            self.antrian.put(("selesai_cek", (folder, *hasil)))
        except Exception as e:
            self.antrian.put(("error", str(e)))

    def selesai_cek(self, folder, hasil, ok, manual, salah):
        self.bar.stop()
        self.hasil_cek, self.folder_cek = hasil, folder
        self.set_tombol(False)
        ringkas = f"Cek selesai: {ok} OK, {manual} cek manual, {salah} salah."
        self.lbl_status.config(fg=W["merah"] if salah else (W["oranye"] if manual else W["hijau"]))
        self.var_status.set(ringkas)
        if salah or manual:
            messagebox.showwarning(
                "Cek Invoice selesai",
                f"✓ OK: {ok}\n⚠ CEK MANUAL: {manual} (tetap digabung)\n"
                f"✕ SALAH: {salah} (akan dilewati saat PROSES GABUNG)\n\n"
                "Rincian ada di kotak 'Rincian proses'.")
        else:
            messagebox.showinfo("Cek Invoice selesai", f"Semua {ok} invoice lolos pengecekan.")

    def cek_antrian(self):
        try:
            while True:
                jenis, isi = self.antrian.get_nowait()
                if jenis == "log":
                    self.tulis_log(*isi)
                elif jenis == "selesai":
                    self.selesai(*isi)
                elif jenis == "progres":
                    self.var_status.set(isi)
                elif jenis == "selesai_cek":
                    self.selesai_cek(*isi)
                elif jenis == "error":
                    self.bar.stop()
                    self.set_tombol(False)
                    self.lbl_status.config(fg=W["merah"])
                    self.var_status.set("Gagal diproses.")
                    messagebox.showerror("Terjadi kesalahan", isi)
        except queue.Empty:
            pass
        self.root.after(100, self.cek_antrian)

    def selesai(self, ok, lewat, tidak_sesuai, hasil):
        self.bar.stop()
        n = len(lewat)
        self.folder_hasil = hasil
        self.set_tombol(False)
        self.btn_buka.config(state="normal" if ok else "disabled")
        self.lbl_ok.config(text=str(ok))
        self.lbl_skip.config(text=str(n))

        tambahan = (f"\nFile nama tidak sesuai pola: {tidak_sesuai}" if tidak_sesuai else "")
        if ok + n == 0:
            self.lbl_status.config(fg=W["merah"])
            self.var_status.set("Tidak ada dealer yang bisa diproses. Cek penamaan file.")
            messagebox.showwarning("Tidak ada yang diproses",
                                   "Tidak ada file Invoice/Report/Email dengan penamaan yang sesuai." + tambahan)
        elif n:
            self.lbl_status.config(fg=W["merah"])
            self.var_status.set(f"Selesai dengan peringatan: {ok} berhasil, {n} dilewati (tulisan merah).")
            messagebox.showwarning(
                "Selesai, ada yang dilewati",
                f"Berhasil digabung: {ok} dealer\nDilewati: {n} dealer\n\n"
                "Dealer yang dilewati ditandai MERAH di rincian proses." + tambahan)
        else:
            self.lbl_status.config(fg=W["hijau"])
            self.var_status.set(f"Selesai: semua {ok} dealer berhasil digabung.")
            messagebox.showinfo("Selesai", f"Berhasil digabung: {ok} dealer" + tambahan)

    def buka_hasil(self):
        if self.folder_hasil and Path(self.folder_hasil).is_dir():
            if sys.platform.startswith("win"):
                os.startfile(self.folder_hasil)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(self.folder_hasil)])

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()