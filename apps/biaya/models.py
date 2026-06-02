"""
==========================================================================
 BIAYA MODELS - Manajemen Biaya / Pengeluaran Operasional
==========================================================================
 File ini berisi 2 model untuk pencatatan biaya/expense:

 1. KategoriBiaya → Pengelompokan biaya (Listrik, Gaji, Sewa, dll)
 2. TransaksiBiaya → Record pengeluaran (expense record)

 ALUR TRANSAKSI BIAYA:
 ┌──────┐   ┌───────────┐   ┌──────────┐
 │Draft │──→│ Submitted │──→│ Approved │  → Uang keluar
 └──────┘   └───────────┘   └──────────┘
                                │
                           ┌──────────┐
                           │ Rejected │  → Ditolak
                           └──────────┘

 Koneksi:
 - apps/pos/models.py → MetodePembayaran (FK untuk pembayaran biaya)
 - apps/dashboard/views.py → Menampilkan total biaya di dashboard
 - apps/laporan/ → Laporan biaya
==========================================================================
"""

from django.db import models, transaction
from django.contrib.auth.models import User


class KategoriBiaya(models.Model):
    """
    Model untuk KATEGORI BIAYA / pengelompokan expense.

    Contoh: Listrik, Gaji Karyawan, Sewa Gedung, Transportasi, Internet, dll.
    """
    # Nama kategori biaya — contoh: 'Listrik', 'Gaji Karyawan', 'Sewa Gedung'
    nama = models.CharField(max_length=100, verbose_name="Nama Kategori")

    # Deskripsi opsional — penjelasan detail tentang kategori ini
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")

    # Flag aktif — kategori nonaktif tidak muncul di dropdown saat buat transaksi biaya
    aktif = models.BooleanField(default=True, verbose_name="Aktif")

    # Timestamp kapan kategori ini dibuat — auto_now_add hanya diisi sekali saat create
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Konfigurasi metadata model KategoriBiaya."""
        verbose_name = "Kategori Biaya"            # Nama singular di Django Admin
        verbose_name_plural = "Kategori Biaya"     # Nama plural di Django Admin
        ordering = ['nama']                        # Urutan default A-Z berdasarkan nama

    def __str__(self):
        """Representasi string — nama kategori (contoh: 'Listrik')."""
        return self.nama


class TransaksiBiaya(models.Model):
    """
    Model untuk TRANSAKSI BIAYA / pengeluaran operasional.

    Setiap transaksi biaya memiliki:
    - Nomor unik (auto-generate: EXP/2024/01/0001)
    - Kategori biaya (Listrik, Gaji, dll)
    - Jumlah uang yang dikeluarkan
    - Status workflow (draft → submitted → approved/rejected)
    - Bukti (foto/PDF bon/kwitansi)
    - Metode pembayaran (Cash, Transfer, dll)
    """

    # ===== STATUS WORKFLOW =====
    # Status menentukan alur persetujuan biaya:
    # draft → submitted → approved (uang keluar) ATAU rejected (ditolak)
    STATUS_CHOICES = [
        ('draft', 'Draft'),              # Baru dibuat, belum diajukan
        ('submitted', 'Diajukan'),       # Sudah diajukan, menunggu persetujuan
        ('approved', 'Disetujui'),       # Disetujui manager → uang keluar dari kas
        ('rejected', 'Ditolak'),         # Ditolak manager → tidak ada pengeluaran
    ]

    # ===== IDENTITAS TRANSAKSI =====
    # Nomor transaksi unik — auto-generate format: EXP/2024/01/0001
    nomor_transaksi = models.CharField(max_length=50, unique=True, verbose_name="Nomor Transaksi")

    # Tanggal pengeluaran — DateField (bukan DateTimeField) karena hanya perlu tanggal
    # Berbeda dengan POS yang pakai DateTimeField karena butuh waktu detail
    tanggal = models.DateField(verbose_name="Tanggal", db_index=True)

    # Kategori biaya — FK ke KategoriBiaya (contoh: Listrik, Gaji)
    # on_delete=PROTECT → kategori tidak bisa dihapus jika masih ada transaksi
    kategori = models.ForeignKey(KategoriBiaya, on_delete=models.PROTECT, related_name='transaksi', verbose_name="Kategori")

    # Nominal pengeluaran — berapa uang yang dikeluarkan
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah")

    # Deskripsi wajib — penjelasan detail tentang biaya ini
    # Tidak ada blank=True, artinya deskripsi WAJIB diisi (required field)
    deskripsi = models.TextField(verbose_name="Deskripsi")

    # Bukti pengeluaran — file foto/PDF bon, kwitansi, atau nota
    # upload_to='biaya/' → disimpan di MEDIA_ROOT/biaya/
    bukti = models.FileField(upload_to='biaya/', blank=True, null=True, verbose_name="Bukti (Foto/PDF)")

    # Status workflow — mengikuti alur persetujuan (lihat STATUS_CHOICES di atas)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status", db_index=True)

    # ===== TRACKING PENGGUNA =====
    # Siapa yang membuat transaksi biaya ini
    # on_delete=SET_NULL → jika user dihapus, transaksi tetap ada (creator=null)
    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='biaya_dibuat')

    # Siapa yang menyetujui biaya ini (diisi saat status berubah ke 'approved')
    # Opsional — hanya diisi saat ada approval
    disetujui_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='biaya_disetujui')

    # ===== METODE PEMBAYARAN =====
    # Menyimpan kode metode pembayaran dari model MetodePembayaran (Pengaturan)
    # Choices ditampilkan secara dinamis di form dari MetodePembayaran aktif
    metode_pembayaran = models.CharField(
        max_length=50,
        blank=True, null=True,
        verbose_name="Metode Pembayaran"
    )

    # Timestamp tracking
    dibuat_pada = models.DateTimeField(auto_now_add=True)   # Otomatis saat create
    diupdate_pada = models.DateTimeField(auto_now=True)     # Otomatis saat update

    class Meta:
        """Konfigurasi metadata model TransaksiBiaya."""
        verbose_name = "Transaksi Biaya"           # Nama singular
        verbose_name_plural = "Transaksi Biaya"    # Nama plural
        # Urutan: tanggal terbaru → kemudian dibuat terbaru
        ordering = ['-tanggal', '-dibuat_pada']

    def __str__(self):
        """
        Representasi string transaksi untuk admin/debugging.
        Format: 'EXP/2024/01/0001 - Listrik - Rp 500,000'
        :,.0f → format angka dengan separator ribuan tanpa desimal
        """
        return f"{self.nomor_transaksi} - {self.kategori.nama} - Rp {self.jumlah:,.0f}"

    @property
    def nama_metode_pembayaran(self):
        """Ambil nama metode pembayaran dari model MetodePembayaran berdasarkan kode."""
        if not self.metode_pembayaran:
            return '-'
        try:
            from apps.pengaturan.models import MetodePembayaran
            metode = MetodePembayaran.objects.filter(kode=self.metode_pembayaran).first()
            if metode:
                return metode.nama
        except Exception:
            pass
        # Fallback: tampilkan kode langsung jika MetodePembayaran tidak ditemukan
        return self.metode_pembayaran

    def save(self, *args, **kwargs):
        """
        Override save() untuk auto-generate nomor transaksi.

        Alur:
        1. Cek apakah nomor_transaksi sudah diisi atau belum
        2. Jika belum → generate nomor otomatis
        3. Simpan ke database via super().save()
        """
        if not self.nomor_transaksi:
            # Generate nomor otomatis hanya jika field kosong
            self.nomor_transaksi = self.generate_nomor()
        with transaction.atomic():
            super().save(*args, **kwargs)  # Simpan semua field ke database

    def generate_nomor(self):
        """
        Generate nomor transaksi biaya otomatis (per BULAN).

        Format: EXP/{TAHUN}/{BULAN}/{NOMOR_URUT_4_DIGIT}
        Contoh: EXP/2024/01/0001, EXP/2024/01/0002

        Algoritma (sama dengan pola di PO/SO):
        1. Buat prefix berdasarkan tahun+bulan → 'EXP/2024/01'
        2. Cari transaksi terakhir dengan prefix yang sama
        3. Parse dan increment nomor urut
        4. Return nomor baru dengan zero-padding 4 digit

        Return: String nomor transaksi — contoh 'EXP/2024/01/0001'
        """
        from datetime import datetime
        today = datetime.now()
        # Format prefix: EXP/2024/01 (per bulan, bukan per hari seperti POS)
        prefix = f"EXP/{today.year}/{today.month:02d}"

        # Cari transaksi biaya terakhir BULAN INI
        last_exp = TransaksiBiaya.objects.filter(
            nomor_transaksi__startswith=prefix  # Filter transaksi bulan ini
        ).order_by('-nomor_transaksi').first()  # Ambil yang nomor terbesar

        if last_exp:
            try:
                # Parse nomor urut dari nomor terakhir
                # Contoh: 'EXP/2024/01/0005'.split('/') → [-1] = '0005' → int = 5
                last_number = int(last_exp.nomor_transaksi.split('/')[-1])
                new_number = last_number + 1  # Increment: 5 → 6
            except (ValueError, IndexError):
                new_number = 1  # Fallback jika format tidak standar
        else:
            new_number = 1  # Transaksi biaya pertama bulan ini

        # Format dengan zero-padding 4 digit: 1 → '0001'
        return f"{prefix}/{new_number:04d}"
