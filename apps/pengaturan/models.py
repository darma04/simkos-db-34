"""
==========================================================================
 PENGATURAN MODELS - Model Pengaturan Sistem & Template Cetak
==========================================================================
 File ini berisi model-model pengaturan sistem ERP:

 Model:
 ┌───────────────────────┬──────────────────────────────────────────────┐
 │ Model                 │ Penjelasan                                    │
 ├───────────────────────┼──────────────────────────────────────────────┤
 │ PengaturanPerusahaan  │ Setting perusahaan (singleton) — nama,       │
 │                       │ logo, SMTP, pajak, maintenance mode          │
 │ TemplateCetak         │ Template cetak dokumen (Invoice, PO, SO,     │
 │                       │ Export Excel/PDF) — header, footer, signature│
 │ BackupHistory         │ Riwayat backup/restore/reset database        │
 └───────────────────────┴──────────────────────────────────────────────┘

 Pola Desain:
 - PengaturanPerusahaan menggunakan Singleton Pattern (hanya 1 record, pk=1)
 - TemplateCetak menggunakan Factory Pattern via get_template()
 - BackupHistory sebagai audit trail untuk operasi database

 Terhubung dengan:
 - Dashboard views (logo, nama perusahaan)
 - Cetak views (template dokumen)
 - Email system (SMTP settings)
 - Backup/restore views (riwayat)
==========================================================================
"""
from django.db import models


class PengaturanPerusahaan(models.Model):
    """Model untuk pengaturan perusahaan (singleton)"""
    nama_perusahaan = models.CharField(max_length=200, verbose_name="Nama Perusahaan")
    logo = models.ImageField(upload_to='perusahaan/', blank=True, null=True, verbose_name="Logo")
    alamat = models.TextField(blank=True, null=True, verbose_name="Alamat")
    telepon = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telepon")
    email = models.EmailField(blank=True, null=True, verbose_name="Email")
    website = models.URLField(blank=True, null=True, verbose_name="Website")
    
    # System Settings / Meta Configuration
    system_title = models.CharField(max_length=200, default='SERPGROUP KOS System', verbose_name="Judul Sistem")
    system_description = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Deskripsi Sistem",
        help_text="Deskripsi singkat tentang sistem (untuk meta description)"
    )
    system_keywords = models.CharField(
        max_length=500, 
        blank=True, 
        null=True, 
        verbose_name="Keywords (SEO)",
        help_text="Pisahkan dengan koma. Contoh: erp, inventory, pos"
    )
    system_logo = models.ImageField(
        upload_to='system/', 
        blank=True, 
        null=True, 
        verbose_name="Logo Sistem",
        help_text="Logo yang ditampilkan di sidebar & login page"
    )
    system_favicon = models.ImageField(
        upload_to='system/', 
        blank=True, 
        null=True, 
        verbose_name="Favicon",
        help_text="Icon yang tampil di tab browser (.ico atau .png 32x32)"
    )
    maintenance_mode = models.BooleanField(
        default=False, 
        verbose_name="Mode Maintenance",
        help_text="Aktifkan untuk menampilkan halaman maintenance"
    )
    maintenance_message = models.TextField(
        default='Sistem sedang dalam maintenance. Silakan coba lagi nanti.',
        blank=True,
        verbose_name="Pesan Maintenance"
    )
    
    # Email/SMTP Settings for sending emails (forgot password, register verification)
    email_smtp_host = models.CharField(max_length=100, default='smtp.gmail.com', verbose_name="SMTP Host")
    email_smtp_port = models.IntegerField(default=587, verbose_name="SMTP Port")
    email_smtp_user = models.EmailField(blank=True, null=True, verbose_name="Email SMTP User")
    email_smtp_password = models.CharField(max_length=255, blank=True, null=True, verbose_name="Email SMTP Password")
    email_use_tls = models.BooleanField(default=True, verbose_name="Use TLS")
    
    # Email Template Settings
    email_header = models.TextField(
        default='Halo,',
        verbose_name="Email Header",
        help_text="Header yang muncul di awal email"
    )
    email_footer = models.TextField(
        default='Terima kasih,\n{company_name}',
        verbose_name="Email Footer",
        help_text="Footer yang muncul di akhir email. Gunakan {company_name} untuk nama perusahaan"
    )
    
    # Forgot Password Email Template
    forgot_password_subject = models.CharField(
        max_length=200,
        default='Reset Password Anda',
        verbose_name="Subjek Email Forgot Password"
    )
    forgot_password_message = models.TextField(
        default='Anda menerima email ini karena ada permintaan reset password untuk akun Anda.\n\nKlik link berikut untuk reset password:\n{reset_link}\n\nJika Anda tidak melakukan permintaan ini, abaikan email ini.',
        verbose_name="Pesan Forgot Password",
        help_text="Gunakan {reset_link} untuk link reset password"
    )
    
    # Register/Verification Email Template
    register_subject = models.CharField(
        max_length=200,
        default='Verifikasi Email Anda',
        verbose_name="Subjek Email Register"
    )
    register_message = models.TextField(
        default='Terima kasih telah mendaftar di sistem kami.\n\nSilakan verifikasi email Anda dengan klik link berikut:\n{verification_link}\n\nLink ini akan kadaluarsa dalam 24 jam.',
        verbose_name="Pesan Register",
        help_text="Gunakan {verification_link} untuk link verifikasi"
    )
    
    # Pajak default
    pajak_default = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Pajak Default (%)")
    
    diupdate_pada = models.DateTimeField(auto_now=True)
    
    class Meta:
        """Konfigurasi metadata — singleton model, hanya 1 instance di database."""
        verbose_name = "Pengaturan Perusahaan"
        verbose_name_plural = "Pengaturan Perusahaan"
    
    def __str__(self):
        """Representasi string — nama perusahaan."""
        return self.nama_perusahaan
    
    def save(self, *args, **kwargs):
        """Override save — paksa pk=1 untuk singleton pattern (hanya 1 instance)."""
        # Pastikan hanya ada 1 instance (singleton pattern)
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        """Memuat pengaturan perusahaan (buat baru jika belum ada)"""
        obj, created = cls.objects.get_or_create(
            pk=1,
            defaults={'nama_perusahaan': 'SERPGROUP'}
        )
        return obj


class TemplateCetak(models.Model):
    """Model untuk mengatur template cetak dokumen"""
    JENIS_TEMPLATE = (
        ('tagihan', 'Tagihan Sewa'),
        ('kwitansi', 'Kwitansi Pembayaran'),
        ('slip_gaji', 'Slip Gaji Karyawan'),
        ('export_excel', 'Template Export Excel'),
        ('export_pdf', 'Template Export PDF'),
    )
    
    nama = models.CharField(max_length=100, verbose_name="Nama Template")
    jenis = models.CharField(max_length=20, choices=JENIS_TEMPLATE, unique=True, verbose_name="Jenis Dokumen")
    
    # Informasi Header Dokumen
    header_nama_perusahaan = models.CharField(max_length=200, default="SINTSGROUP", verbose_name="Nama Perusahaan")
    header_alamat = models.TextField(default="Jl. Contoh Alamat No. 123, Jakarta 12345", verbose_name="Alamat")
    header_telepon = models.CharField(max_length=50, default="(021) 1234-5678", verbose_name="Telepon")
    header_email = models.EmailField(default="info@starterkit.com", verbose_name="Email")
    header_website = models.CharField(max_length=100, blank=True, null=True, verbose_name="Website")
    
    # Informasi Footer Dokumen
    footer_ucapan = models.CharField(max_length=200, default="Terima kasih atas kepercayaan Anda!", verbose_name="Ucapan Terima Kasih")
    footer_keterangan = models.CharField(max_length=200, default="Dokumen ini dicetak secara otomatis dan sah tanpa tanda tangan.", verbose_name="Keterangan")
    footer_copyright = models.CharField(max_length=200, default="© 2026 SINTSGROUP", verbose_name="Footer Copyright")
    
    # Label Tanda Tangan
    signature_kiri_label = models.CharField(max_length=50, default="Disetujui Oleh", verbose_name="Label Tanda Tangan Kiri")
    signature_kanan_label = models.CharField(max_length=50, default="Dibuat Oleh", verbose_name="Label Tanda Tangan Kanan")
    
    # Pengaturan Tambahan
    tampilkan_logo = models.BooleanField(default=True, verbose_name="Tampilkan Logo")
    tampilkan_website = models.BooleanField(default=False, verbose_name="Tampilkan Website")
    
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)
    
    class Meta:
        """Konfigurasi metadata — 1 template per jenis dokumen, urut berdasarkan jenis."""
        verbose_name = "Template Cetak"
        verbose_name_plural = "Template Cetak"
        ordering = ['jenis']
    
    def __str__(self):
        """Representasi string: 'Template Invoice (Invoice)' — untuk admin."""
        return f"{self.nama} ({self.get_jenis_display()})"
    
    @classmethod
    def get_template(cls, jenis):
        """Mengambil template berdasarkan jenis dokumen, buat default jika belum ada"""
        defaults = cls._get_default_values(jenis)
        obj, created = cls.objects.get_or_create(
            jenis=jenis,
            defaults=defaults
        )
        return obj
    
    @classmethod
    def _get_default_values(cls, jenis):
        """Mendapatkan nilai default untuk setiap jenis template cetak"""
        defaults_map = {
            'tagihan': {
                'nama': 'Template Tagihan Sewa',
                'signature_kiri_label': 'Pengelola KOS',
                'signature_kanan_label': 'Penyewa',
            },
            'kwitansi': {
                'nama': 'Template Kwitansi Pembayaran',
                'signature_kiri_label': 'Penerima',
                'signature_kanan_label': 'Pembayar',
            },
            'slip_gaji': {
                'nama': 'Template Slip Gaji Karyawan',
                'signature_kiri_label': 'Diterima Oleh',
                'signature_kanan_label': 'Pengelola KOS',
                'footer_ucapan': 'Slip gaji ini bersifat rahasia.',
                'footer_keterangan': 'Dokumen ini dicetak secara otomatis oleh sistem.',
            },
            'export_excel': {
                'nama': 'Template Export Excel',
                'signature_kiri_label': '-',
                'signature_kanan_label': '-',
                'footer_ucapan': '',
                'footer_keterangan': 'Diekspor dari SIMKOS - Sistem Informasi Manajemen Kos.',
                'footer_copyright': '© 2026 SINTSGROUP',
            },
            'export_pdf': {
                'nama': 'Template Export PDF',
                'signature_kiri_label': '-',
                'signature_kanan_label': '-',
                'footer_ucapan': '',
                'footer_keterangan': 'Diekspor dari SIMKOS - Sistem Informasi Manajemen Kos.',
                'footer_copyright': '© 2026 SINTSGROUP',
            },
        }
        
        base_defaults = {
            'header_nama_perusahaan': 'SINTSGROUP',
            'header_alamat': 'Jl. Contoh Alamat No. 123',
            'header_telepon': '(021) 1234-5678',
            'header_email': 'info@simkos.com',
            'footer_ucapan': 'Terima kasih atas kepercayaan Anda!',
            'footer_keterangan': 'Dokumen ini dicetak secara otomatis dan sah tanpa tanda tangan.',
            'footer_copyright': '© 2026 SINTSGROUP',
        }
        
        # Merge with specific defaults
        base_defaults.update(defaults_map.get(jenis, {}))
        return base_defaults


class BackupHistory(models.Model):
    """Model untuk mencatat riwayat aktivitas backup, restore, dan reset data"""
    JENIS_CHOICES = (
        ('backup', 'Backup Data'),
        ('restore', 'Restore Data'),
        ('reset', 'Reset Data'),
    )
    
    STATUS_CHOICES = (
        ('sukses', 'Sukses'),
        ('gagal', 'Gagal'),
    )
    
    nama_file = models.CharField(max_length=255, verbose_name="Nama File")
    ukuran_file = models.BigIntegerField(default=0, verbose_name="Ukuran File (bytes)")
    jenis = models.CharField(max_length=10, choices=JENIS_CHOICES, verbose_name="Jenis Aktivitas")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sukses', verbose_name="Status")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")
    dibuat_oleh = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Dibuat Oleh", related_name='backup_histories'
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True, verbose_name="Tanggal")
    
    class Meta:
        """Konfigurasi metadata — riwayat backup terbaru di atas."""
        verbose_name = "Riwayat Backup"
        verbose_name_plural = "Riwayat Backup"
        ordering = ['-dibuat_pada']
    
    def __str__(self):
        """Representasi string: 'Backup Data - backup_2024.sql' — untuk admin."""
        return f"{self.get_jenis_display()} - {self.nama_file}"
    
    @property
    def ukuran_display(self):
        """Format ukuran file ke KB/MB"""
        if self.ukuran_file < 1024:
            return f"{self.ukuran_file} B"
        elif self.ukuran_file < 1024 * 1024:
            return f"{self.ukuran_file / 1024:.1f} KB"
        else:
            return f"{self.ukuran_file / (1024 * 1024):.1f} MB"


class MetodePembayaran(models.Model):
    """
    Model untuk METODE PEMBAYARAN di SIMKOS.

    Contoh: Tunai, Transfer Bank, E-Wallet, QRIS
    Digunakan di: PembayaranSewa, TransaksiBiaya
    Dikelola dari: Pengaturan > Metode Pembayaran
    """
    nama = models.CharField(max_length=100, verbose_name="Nama Metode")
    kode = models.CharField(max_length=20, unique=True, verbose_name="Kode")
    nama_pemilik = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nama Pemilik")
    deskripsi = models.TextField(blank=True, null=True, verbose_name="Deskripsi")
    gambar = models.ImageField(upload_to='metode_pembayaran/', blank=True, null=True, verbose_name="Gambar/Logo")
    saldo = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Saldo Awal")
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    dibuat_pada = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat Pada")
    diupdate_pada = models.DateTimeField(auto_now=True, verbose_name="Diupdate Pada")

    class Meta:
        verbose_name = "Metode Pembayaran"
        verbose_name_plural = "Metode Pembayaran"
        ordering = ['nama']

    def __str__(self):
        return self.nama

    @property
    def total_pendapatan(self):
        """Total pendapatan dari pembayaran sewa yang menggunakan metode ini."""
        from django.db.models import Sum
        from apps.sewa.models import PembayaranSewa
        total = PembayaranSewa.objects.filter(
            metode_bayar=self.kode
        ).aggregate(t=Sum('jumlah_bayar'))['t'] or 0
        return total

    @property
    def total_pengeluaran(self):
        """Total pengeluaran dari transaksi biaya yang menggunakan metode ini."""
        from django.db.models import Sum
        from apps.biaya.models import TransaksiBiaya
        # Hitung semua transaksi (tidak filter status) agar data muncul
        total = TransaksiBiaya.objects.filter(
            metode_pembayaran=self.kode
        ).exclude(status='rejected').aggregate(t=Sum('jumlah'))['t'] or 0
        return total

    @property
    def saldo_terhitung(self):
        """Saldo dinamis = saldo awal + pendapatan - pengeluaran."""
        return self.saldo + self.total_pendapatan - self.total_pengeluaran

    @property
    def total_transaksi_count(self):
        """Total jumlah transaksi yang menggunakan metode ini."""
        from apps.sewa.models import PembayaranSewa
        from apps.biaya.models import TransaksiBiaya
        pembayaran_count = PembayaranSewa.objects.filter(metode_bayar=self.kode).count()
        biaya_count = TransaksiBiaya.objects.filter(metode_pembayaran=self.kode).count()
        return pembayaran_count + biaya_count
