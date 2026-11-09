import os
import shutil
import zipfile
from uuid import uuid4
from pathlib import Path
from flask import Flask, request, render_template, send_file, jsonify

# Import logika utama Anda
from backend import proses

app = Flask(__name__, template_folder='../templates')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Maksimal upload 50MB

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_files():
    if 'files[]' not in request.files:
        return jsonify({"error": "Tidak ada file yang diunggah"}), 400

    files = request.files.getlist('files[]')
    if not files or files[0].filename == '':
        return jsonify({"error": "Tidak ada file yang dipilih"}), 400

    # Buat folder sementara (temporary) yang unik di Vercel
    sesi_id = str(uuid4())
    folder_input = Path(f"/tmp/{sesi_id}/input")
    folder_input.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Simpan semua file yang diupload
        for file in files:
            if file and file.filename.endswith('.pdf'):
                # Amankan nama file agar tidak ada path traversal
                filename = os.path.basename(file.filename) 
                file.save(folder_input / filename)

        # 2. Jalankan proses penggabungan dari backend.py Anda
        # Kita buat fungsi log kosong karena kita tidak menampilkan log real-time di web
        def log_dummy(teks, level="info"):
            print(f"[{level.upper()}] {teks}")

        # Proses gabung (Cek OCR dinonaktifkan dengan mengirim status_cek=None)
        berhasil, dilewati, tidak_dikenali, folder_output = proses(folder_input, log_dummy, status_cek=None)

        # 3. Zip folder hasil (HASIL_COMPILE)
        zip_path = Path(f"/tmp/{sesi_id}/Hasil_Compile.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files_in_dir in os.walk(folder_output):
                for file in files_in_dir:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, folder_output)
                    zipf.write(filepath, arcname)

        # 4. Kirim file ZIP ke pengguna
        return send_file(
            zip_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name='Hasil_Compile_PDF.zip'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # Hapus file sementara setelah diproses bukan di sini (Flask send_file butuh file tetap ada)
    # Di Vercel, folder /tmp akan otomatis dibersihkan secara berkala oleh sistem.

if __name__ == '__main__':
    app.run(debug=True)