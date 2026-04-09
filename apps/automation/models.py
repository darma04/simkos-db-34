"""
==========================================================================
 AUTOMATION MODELS - Model Sistem Notifikasi Telegram Otomatis
==========================================================================
 File ini berisi 3 model untuk sistem notifikasi Telegram:

 1. PengaturanTelegram (Singleton Pattern)
    - Menyimpan konfigurasi bot: token, chat_id, toggle notifikasi
    - Singleton = hanya 1 record (pk=1 selalu)
    - Alasan: Pengaturan bot Telegram hanya perlu 1 konfigurasi global

 2. TemplatePesan
    - Template pesan notifikasi per jenis transaksi
    - Menggunakan placeholder {{variabel}} yang di-render saat kirim
    - Default template otomatis dibuat jika belum ada

 3. LogNotifikasi
    - Riwayat pengiriman notifikasi (sukses/gagal)
    - Untuk monitoring dan debugging pengiriman pesan

 Alur kerja notifikasi:
 ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  ┌──────────┐
 │ User membuat │→│ views.py      │→│ signals.py       │→│ telegram  │
 │ transaksi    │  │ save data     │  │ siapkan data     │  │ _service  │
 └──────────────┘  └───────────────┘  │ panggil kirim    │  │ kirim API│
                                      └──────────────────┘  └──────────┘

 Terhubung dengan:
 - signals.py → Memformat data transaksi untuk notifikasi
 - telegram_service.py → Mengirim pesan via Telegram Bot API
 - views.py → Halaman pengaturan dan log notifikasi
==========================================================================
"""
from django.db import models


class PengaturanTelegram(models.Model):
    """
    Model konfigurasi bot Telegram menggunakan Singleton Pattern.
    Singleton = hanya boleh ada 1 record di database (pk=1).
    Menggunakan method load() untuk mengambil/membuat konfigurasi.
    """
    bot_token = models.CharField(
        max_length=200, 
        blank=True, 
        verbose_name="Bot Token",
        help_text="Token dari @BotFather, contoh: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    )
    chat_id = models.CharField(
        max_length=100, 
        blank=True, 
        verbose_name="Chat ID",
        help_text="Chat ID tujuan (grup atau personal). Gunakan @userinfobot untuk mengetahui Chat ID"
    )
    aktif = models.BooleanField(default=False, verbose_name="Aktif")
    
    # Toggle per jenis transaksi SIMKOS
    notif_tagihan = models.BooleanField(default=True, verbose_name="Notifikasi Tagihan Sewa")
    notif_kwitansi = models.BooleanField(default=True, verbose_name="Notifikasi Kwitansi Pembayaran")
    notif_biaya = models.BooleanField(default=True, verbose_name="Notifikasi Biaya Operasional")
    notif_gaji = models.BooleanField(default=True, verbose_name="Notifikasi Gaji Karyawan KOS")
    
    # Toggle kirim PDF — jika True, setiap notifikasi juga mengirim file PDF
    kirim_pdf = models.BooleanField(
        default=True,
        verbose_name="Kirim PDF Otomatis",
        help_text="Jika aktif, setiap notifikasi juga akan mengirim file PDF dokumen ke Telegram"
    )

    # ═══ FIELD: System Prompt Bot Telegram ═══
    # Instruksi kustom untuk mengatur perilaku AI chatbot di Telegram
    # Jika kosong, akan menggunakan system prompt default dari telegram_bot.py
    system_prompt_bot = models.TextField(
        blank=True,
        default='',
        verbose_name="System Prompt Bot AI",
        help_text="Instruksi tambahan untuk mengatur perilaku AI chatbot Telegram. Kosongkan untuk menggunakan default."
    )

    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)
    
    class Meta:
        """Konfigurasi metadata model untuk Django."""
        verbose_name = "Pengaturan Telegram"
        verbose_name_plural = "Pengaturan Telegram"
    
    def __str__(self):
        """Representasi string objek untuk admin dan debugging."""
        return f"Pengaturan Telegram ({'Aktif' if self.aktif else 'Nonaktif'})"
    
    def save(self, *args, **kwargs):
        # Singleton pattern: pastikan hanya ada 1 record
        """Override save — logika bisnis sebelum menyimpan ke database."""
        self.pk = 1
        super().save(*args, **kwargs)
    
    @classmethod
    def load(cls):
        """Memuat pengaturan Telegram (buat baru jika belum ada)"""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class TemplatePesan(models.Model):
    """Template pesan notifikasi Telegram untuk setiap jenis transaksi"""
    JENIS_CHOICES = [
        ('tagihan', 'Tagihan Sewa'),
        ('kwitansi', 'Kwitansi Pembayaran'),
        ('biaya', 'Biaya Operasional'),
        ('gaji', 'Gaji Karyawan KOS'),
    ]
    
    jenis = models.CharField(
        max_length=30, 
        choices=JENIS_CHOICES, 
        unique=True, 
        verbose_name="Jenis Transaksi"
    )
    nama = models.CharField(max_length=100, verbose_name="Nama Template")
    template_pesan = models.TextField(
        verbose_name="Template Pesan",
        help_text="Gunakan variabel dalam kurung kurawal ganda, contoh: {{nomor_transaksi}}"
    )
    aktif = models.BooleanField(default=True, verbose_name="Aktif")
    
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)
    
    class Meta:
        """Konfigurasi metadata model untuk Django."""
        verbose_name = "Template Pesan"
        verbose_name_plural = "Template Pesan"
        ordering = ['jenis']
    
    def __str__(self):
        """Representasi string objek untuk admin dan debugging."""
        return f"{self.get_jenis_display()} - {self.nama}"
    
    @classmethod
    def get_template(cls, jenis):
        """Mengambil template berdasarkan jenis transaksi, buat default jika belum ada"""
        obj, created = cls.objects.get_or_create(
            jenis=jenis,
            defaults={
                'nama': f'Template {dict(cls.JENIS_CHOICES).get(jenis, jenis)}',
                'template_pesan': cls._get_default_template(jenis),
                'aktif': True,
            }
        )
        return obj
    
    @classmethod
    def _get_default_template(cls, jenis):
        """Mendapatkan template default untuk setiap jenis transaksi"""
        templates = {
            'tagihan': (
                "📋 *TAGIHAN SEWA BARU*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_tagihan}}\n"
                "📅 Periode: {{periode}}\n"
                "👤 Penyewa: {{penyewa}}\n"
                "🏠 Kamar: {{kamar}}\n"
                "💰 Jumlah: Rp {{jumlah}}\n"
                "📅 Jatuh Tempo: {{jatuh_tempo}}\n"
                "📊 Status: {{status}}"
            ),
            'kwitansi': (
                "✅ *PEMBAYARAN DITERIMA*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_pembayaran}}\n"
                "📅 Tanggal: {{tanggal}}\n"
                "👤 Penyewa: {{penyewa}}\n"
                "💰 Jumlah: Rp {{jumlah}}\n"
                "💳 Metode: {{metode}}\n"
                "📝 Keterangan: {{keterangan}}"
            ),
            'biaya': (
                "💸 *BIAYA OPERASIONAL BARU*\n"
                "━━━━━━━━━━━━━━━\n"
                "📋 No: {{nomor_transaksi}}\n"
                "📅 Tanggal: {{tanggal}}\n"
                "📂 Kategori: {{kategori}}\n"
                "💰 Jumlah: Rp {{jumlah}}\n"
                "📝 Deskripsi: {{deskripsi}}\n"
                "👤 Dibuat oleh: {{dibuat_oleh}}"
            ),
            'gaji': (
                "💼 *GAJI KARYAWAN KOS*\n"
                "━━━━━━━━━━━━━━━\n"
                "👤 Karyawan: {{nama_karyawan}}\n"
                "📅 Periode: {{periode}}\n"
                "💰 Gaji Pokok: Rp {{gaji_pokok}}\n"
                "➕ Tunjangan: Rp {{tunjangan}}\n"
                "➖ Potongan: Rp {{potongan}}\n"
                "💵 *Gaji Bersih: Rp {{gaji_bersih}}*\n"
                "📊 Status: {{status}}"
            ),
        }
        return templates.get(jenis, "{{nomor_transaksi}} - {{total}}")


class LogNotifikasi(models.Model):
    """Log riwayat pengiriman notifikasi Telegram (sukses/gagal)"""
    STATUS_CHOICES = [
        ('sukses', 'Sukses'),
        ('gagal', 'Gagal'),
    ]
    
    JENIS_CHOICES = TemplatePesan.JENIS_CHOICES
    
    jenis_transaksi = models.CharField(max_length=30, choices=JENIS_CHOICES, verbose_name="Jenis Transaksi")
    nomor_referensi = models.CharField(max_length=100, verbose_name="Nomor Referensi")
    pesan = models.TextField(verbose_name="Pesan yang Dikirim")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, verbose_name="Status")
    respons = models.TextField(blank=True, null=True, verbose_name="Respons API")
    error_message = models.TextField(blank=True, null=True, verbose_name="Pesan Error")
    
    dikirim_pada = models.DateTimeField(auto_now_add=True, verbose_name="Dikirim Pada")
    
    class Meta:
        """Konfigurasi metadata model untuk Django."""
        verbose_name = "Log Notifikasi"
        verbose_name_plural = "Log Notifikasi"
        ordering = ['-dikirim_pada']
    
    def __str__(self):
        """Representasi string objek untuk admin dan debugging."""
        return f"[{self.status}] {self.jenis_transaksi} - {self.nomor_referensi}"
