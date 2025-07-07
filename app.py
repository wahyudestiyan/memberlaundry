import streamlit as st
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A6
from reportlab.lib.utils import ImageReader
from datetime import datetime, timedelta
import os
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ========== KONFIGURASI ==========
SPREADSHEET_ID = "1yD7FOMO8VMTYwmEKsNJBv34etuWntHRLW8QACbukTyU"
WORKSHEET_NAME = "member"
OUTPUT_FOLDER = "output"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ========== UTILITAS ==========
def format_tanggal_indo(tanggal):
    bulan = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{tanggal.day} {bulan[tanggal.month]} {tanggal.year}"

def normalisasi_nomor(nomor):
    nomor = str(nomor).strip().replace(" ", "").replace("-", "")
    if nomor.startswith("08"):
        return "62" + nomor[1:]
    elif nomor.startswith("620"):
        return "62" + nomor[3:]
    return nomor

def get_worksheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["google_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

def upload_pdf_to_drive(file_path, filename):
    scope = ["https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["google_service_account"], scopes=scope)
    drive_service = build("drive", "v3", credentials=creds)

    file_metadata = {
        "name": filename,
        "parents": [st.secrets["drive_folder_id"]]
    }
    media = MediaFileUpload(file_path, mimetype="application/pdf")
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()

    drive_service.permissions().create(
        fileId=file.get("id"),
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return f"https://drive.google.com/file/d/{file.get('id')}/view?usp=sharing"

# ========== GENERATE KARTU ==========
def generate_kartu_pdf(nama, nomor, jenis, urutan):
    kode = f"{'wangi-s' if jenis == 'Silver' else 'wangi-g'}-{urutan + 1:02d}"
    mulai = datetime.today().date()
    selesai = mulai + timedelta(days=90 if jenis == 'Silver' else 180)
    pdf_path = os.path.join(OUTPUT_FOLDER, f"{kode}.pdf")

    background = {
        "Silver": "silver.png",
        "Gold": "gold.png"
    }
    bg_file = background.get(jenis, "")
    bg_path = os.path.join(os.path.dirname(__file__), bg_file)

    c = canvas.Canvas(pdf_path, pagesize=landscape(A6))
    if os.path.exists(bg_path):
        c.drawImage(ImageReader(bg_path), 0, 0, width=landscape(A6)[0], height=landscape(A6)[1])

    labels = ["Nama", "Nomor WA", "Jenis Member", "Kode Member", "Berlaku Dari", "Sampai Tanggal"]
    values = [nama, nomor, jenis, kode, format_tanggal_indo(mulai), format_tanggal_indo(selesai)]

    x_label, x_value, y_start, line_spacing = 150, 255, 180, 22

    for i, (label, value) in enumerate(zip(labels, values)):
        y = y_start - i * line_spacing
        c.setFont("Helvetica", 12)
        c.drawString(x_label, y, f"{label}")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_value, y, f": {value}")

    c.save()
    return pdf_path, mulai, selesai, kode

def simpan_ke_spreadsheet(nama, nomor, jenis, mulai, selesai, kode, link):
    sheet = get_worksheet()
    status = "Aktif" if selesai >= datetime.today().date() else "Tidak Aktif"
    sheet.append_row([
        nama, nomor, jenis,
        mulai.strftime('%Y-%m-%d'),
        selesai.strftime('%Y-%m-%d'),
        status, kode, link
    ])

# ========== STREAMLIT ==========
st.title("🧼 Form Pendaftaran Member Laundry")

with st.form("form_pendaftaran"):
    nama = st.text_input("Nama Lengkap")
    nomor = st.text_input("Nomor WhatsApp (08xxxx)")
    jenis = st.selectbox("Jenis Member", ["Silver", "Gold"])
    submit = st.form_submit_button("✅ Daftar & Unduh Kartu")

if submit and nama and nomor:
    nomor_norm = normalisasi_nomor(nomor)
    sheet = get_worksheet()
    data = sheet.get_all_values()
    jumlah_jenis = sum(1 for row in data[1:] if row[2].lower() == jenis.lower())

    pdf_path, mulai, selesai, kode = generate_kartu_pdf(nama, nomor_norm, jenis, jumlah_jenis)

    if pdf_path:
        link_pdf = upload_pdf_to_drive(pdf_path, f"Kartu_{kode}.pdf")
        simpan_ke_spreadsheet(nama, nomor_norm, jenis, mulai, selesai, kode, link_pdf)
        st.success(f"🎉 Kartu berhasil dibuat dengan kode: {kode}")
        with open(pdf_path, "rb") as f:
            st.download_button("📅 Unduh Kartu PDF", f, file_name=f"Kartu_{kode}.pdf")
    else:
        st.error("❌ Gagal membuat kartu.")
elif submit:
    st.warning("Harap isi semua kolom.")

st.markdown("---")
st.subheader("🔍 Cek & Unduh Kembali Kartu")

with st.form("cek_kartu"):
    no_cek = st.text_input("Masukkan Nomor WhatsApp (08xxxx / 628xxxx)")
    cek_submit = st.form_submit_button("🔎 Cari")

if cek_submit:
    if not no_cek:
        st.warning("Silakan masukkan nomor WhatsApp.")
    else:
        norm = normalisasi_nomor(no_cek)
        sheet = get_worksheet()
        data = sheet.get_all_values()
        ditemukan = False

        for row in data:
            if len(row) < 8:
                continue
            nomor_db = normalisasi_nomor(row[1])
            if nomor_db == norm:
                ditemukan = True
                st.success(f"✅ Ditemukan: {row[0]} ({row[2]}) - {row[5]}")
                file_url = row[7]
                st.markdown(f"[📄 Unduh Kartu PDF]({file_url})")
                break

        if not ditemukan:
            st.error("❌ Nomor tidak ditemukan.")
