"""
==========================================================================
 AUTOMATION SIGNALS SIMKOS - Helper Notifikasi Telegram
==========================================================================
 Fungsi helper untuk mengirim notifikasi Telegram secara otomatis saat
 terjadi transaksi di SIMKOS (Tagihan, Pembayaran, Biaya, Gaji).

 Setiap fungsi mengikuti pola:
 - Jika kirim_pdf aktif → kirim PDF+caption (1 pesan gabungan)
 - Jika tidak → kirim pesan teks saja

 Fungsi yang tersedia:
 ┌───────────────────────────────────┬──────────────────────────────────────┐
 │ Fungsi                            │ Dipanggil dari                       │
 ├───────────────────────────────────┼──────────────────────────────────────┤
 │ kirim_notifikasi_tagihan()        │ sewa/views.py setelah tagihan dibuat │
 │ kirim_notifikasi_kwitansi()       │ sewa/views.py setelah bayar created  │
 │ kirim_notifikasi_biaya()          │ biaya/views.py setelah biaya dibuat  │
 │ kirim_notifikasi_gaji()           │ hr/views.py setelah gaji dibuat      │
 └───────────────────────────────────┴──────────────────────────────────────┘
==========================================================================
"""

from .telegram_service import kirim_notifikasi_async, kirim_dokumen_async, format_angka


def _is_kirim_pdf_aktif():
    """Cek apakah fitur kirim PDF aktif di pengaturan."""
    try:
        from .models import PengaturanTelegram
        pengaturan = PengaturanTelegram.load()
        return pengaturan.aktif and getattr(pengaturan, 'kirim_pdf', False)
    except Exception:
        return False


def kirim_notifikasi_tagihan(instance):
    """
    Kirim notifikasi Telegram untuk Tagihan Sewa yang baru dibuat.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    bulan_names = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                   'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

    data = {
        'nomor_tagihan': instance.nomor_tagihan,
        'penyewa': instance.kontrak.penyewa.nama,
        'kamar': str(instance.kontrak.kamar),
        'periode': f"{bulan_names[instance.periode_bulan]} {instance.periode_tahun}",
        'jumlah': format_angka(instance.jumlah),
        'jatuh_tempo': instance.tanggal_jatuh_tempo.strftime('%d/%m/%Y') if instance.tanggal_jatuh_tempo else '-',
        'status': instance.get_status_display(),
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_tagihan_pdf
        kirim_dokumen_async('tagihan', instance.nomor_tagihan, instance, generate_tagihan_pdf, data)
    else:
        kirim_notifikasi_async('tagihan', instance.nomor_tagihan, data)


def kirim_notifikasi_kwitansi(instance):
    """
    Kirim notifikasi Telegram untuk Pembayaran Sewa yang baru dilakukan.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    data = {
        'nomor_pembayaran': instance.nomor_pembayaran,
        'penyewa': instance.tagihan.kontrak.penyewa.nama,
        'kamar': str(instance.tagihan.kontrak.kamar),
        'nomor_tagihan': instance.tagihan.nomor_tagihan,
        'jumlah_bayar': format_angka(instance.jumlah_bayar),
        'tanggal_bayar': instance.tanggal_bayar.strftime('%d/%m/%Y') if instance.tanggal_bayar else '-',
        'metode_bayar': instance.nama_metode_bayar,
        'status_tagihan': instance.tagihan.get_status_display(),
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_kwitansi_pdf
        kirim_dokumen_async('kwitansi', instance.nomor_pembayaran, instance, generate_kwitansi_pdf, data)
    else:
        kirim_notifikasi_async('kwitansi', instance.nomor_pembayaran, data)


def kirim_notifikasi_biaya(instance):
    """
    Kirim notifikasi Telegram untuk Biaya Operasional yang baru dicatat.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    data = {
        'nomor_transaksi': instance.nomor_transaksi,
        'tanggal': instance.tanggal.strftime('%d/%m/%Y') if instance.tanggal else '-',
        'kategori': str(instance.kategori) if instance.kategori else '-',
        'jumlah': format_angka(instance.jumlah),
        'deskripsi': instance.deskripsi or '-',
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else '-',
        'dibuat_oleh': instance.dibuat_oleh.get_full_name() or instance.dibuat_oleh.username if instance.dibuat_oleh else '-',
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_biaya_pdf
        kirim_dokumen_async('biaya', instance.nomor_transaksi, instance, generate_biaya_pdf, data)
    else:
        kirim_notifikasi_async('biaya', instance.nomor_transaksi, data)


def kirim_notifikasi_gaji(instance):
    """
    Kirim notifikasi Telegram untuk Slip Gaji karyawan.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    total_tunjangan = (
        instance.tunjangan_jabatan +
        instance.tunjangan_makan +
        instance.tunjangan_transport +
        instance.tunjangan_lainnya
    )

    total_potongan = (
        instance.potongan_bpjs_kesehatan +
        instance.potongan_bpjs_ketenagakerjaan +
        instance.potongan_pph21 +
        instance.potongan_lainnya
    )

    nomor_ref = f"GAJI/{instance.karyawan.nik}/{instance.periode_bulan}/{instance.periode_tahun}"

    data = {
        'nama_karyawan': instance.karyawan.nama,
        'nik': instance.karyawan.nik,
        'jabatan': instance.karyawan.jabatan.nama if instance.karyawan.jabatan else '-',
        'periode': instance.periode,
        'gaji_pokok': format_angka(instance.gaji_pokok),
        'tunjangan': format_angka(total_tunjangan),
        'potongan': format_angka(total_potongan),
        'gaji_bersih': format_angka(instance.gaji_bersih),
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else '-',
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_slip_gaji_pdf
        kirim_dokumen_async('gaji', nomor_ref, instance, generate_slip_gaji_pdf, data)
    else:
        kirim_notifikasi_async('gaji', nomor_ref, data)


def kirim_notifikasi_penggajian(instance):
    """
    Kirim notifikasi Telegram untuk Slip Gaji karyawan.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    # Hitung total tunjangan dan potongan untuk template pesan
    total_tunjangan = (
        instance.tunjangan_jabatan +
        instance.tunjangan_makan +
        instance.tunjangan_transport +
        instance.tunjangan_lainnya
    )

    total_potongan = (
        instance.potongan_bpjs_kesehatan +
        instance.potongan_bpjs_ketenagakerjaan +
        instance.potongan_pph21 +
        instance.potongan_lainnya
    )

    nomor_ref = f"GAJI/{instance.karyawan.nik}/{instance.periode_bulan}/{instance.periode_tahun}"

    data = {
        'nama_karyawan': instance.karyawan.nama,
        'nik': instance.karyawan.nik,
        'jabatan': instance.karyawan.jabatan.nama if instance.karyawan.jabatan else '-',
        'departemen': instance.karyawan.departemen.nama if instance.karyawan.departemen else '-',
        'periode': instance.periode,
        'gaji_pokok': format_angka(instance.gaji_pokok),
        'tunjangan': format_angka(total_tunjangan),
        'potongan': format_angka(total_potongan),
        'gaji_bersih': format_angka(instance.gaji_bersih),
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_penggajian_pdf
        kirim_dokumen_async('gaji', nomor_ref, instance, generate_penggajian_pdf, data)
    else:
        kirim_notifikasi_async('gaji', nomor_ref, data)