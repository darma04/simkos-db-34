"""
==========================================================================
 LICENSE MODELS — Model Konfigurasi Lisensi Lokal
==========================================================================
 Menyimpan data lisensi di database lokal aplikasi klien.
 Model ini digunakan oleh license_middleware.py untuk:
 - Menyimpan license_key dan hardware_id
 - Menyimpan hasil validasi terakhir (cache 24 jam)
 - Menentukan apakah aplikasi boleh diakses atau harus diblokir

 Koneksi:
 - apps/core/license_middleware.py → Middleware membaca model ini
 - apps/core/license_views.py → View aktivasi menulis ke model ini
 - Central License Server (CLS) → API validate/activate dipanggil secara berkala
==========================================================================
"""
import uuid
import hashlib
import platform
from django.db import models
from django.utils import timezone


def generate_hardware_id():
    """
    Generate Hardware ID unik berdasarkan kombinasi identitas mesin.
    Menggunakan: hostname + processor + platform sebagai 'sidik jari'.
    Untuk Android (Capacitor), HWID dikirim dari sisi JavaScript.
    """
    raw = f"{platform.node()}-{platform.processor()}-{platform.system()}-{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class LicenseConfig(models.Model):
    """
    Konfigurasi lisensi lokal — hanya boleh ada 1 record (singleton).

    Field:
    - license_key: Kunci lisensi dari CLS (contoh: SIMKOS-2026-ABCD-EF12)
    - hardware_id: Sidik jari perangkat (SHA256 dari info mesin)
    - cls_server_url: URL Central License Server
    - is_activated: Apakah lisensi sudah pernah berhasil diaktifkan
    - last_validated: Kapan terakhir kali validasi berhasil
    - validation_cache: Hasil validasi terakhir (True/False)
    - cache_expires_at: Kapan cache kedaluwarsa (24 jam setelah validasi)
    """
    license_key = models.CharField(
        max_length=50, blank=True, null=True,
        verbose_name="Kunci Lisensi"
    )
    hardware_id = models.CharField(
        max_length=64, blank=True, null=True,
        verbose_name="Hardware ID"
    )
    cls_server_url = models.URLField(
        default="https://cls.serpgroup.cloud",
        verbose_name="URL Central License Server",
        help_text="Alamat server CLS (contoh: https://cls.serpgroup.cloud)"
    )
    is_activated = models.BooleanField(
        default=False,
        verbose_name="Sudah Diaktifkan?"
    )
    last_validated = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Terakhir Divalidasi"
    )
    validation_cache = models.BooleanField(
        default=False,
        verbose_name="Cache Validasi (Valid/Invalid)"
    )
    cache_expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Cache Kedaluwarsa Pada"
    )
    validation_message = models.TextField(
        blank=True, null=True,
        verbose_name="Pesan Validasi Terakhir"
    )
    product_name = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Nama Produk"
    )
    client_name = models.CharField(
        max_length=150, blank=True, null=True,
        verbose_name="Nama Klien"
    )
    expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Tanggal Lisensi Berakhir"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Konfigurasi Lisensi"
        verbose_name_plural = "Konfigurasi Lisensi"

    def __str__(self):
        if self.license_key:
            status = "Aktif" if self.is_activated else "Belum Aktif"
            return f"{self.license_key} ({status})"
        return "Belum dikonfigurasi"

    @classmethod
    def get_config(cls):
        """Mengambil atau membuat config singleton."""
        config, _ = cls.objects.get_or_create(pk=1)
        return config

    def is_cache_valid(self):
        """Cek apakah cache validasi masih berlaku (belum 24 jam)."""
        if not self.cache_expires_at:
            return False
        return timezone.now() < self.cache_expires_at

    def update_validation_cache(self, is_valid, message="", expires_at=None,
                                 product_name=None, client_name=None):
        """Update cache validasi dengan hasil terbaru dari CLS."""
        from datetime import timedelta
        self.validation_cache = is_valid
        self.validation_message = message
        self.last_validated = timezone.now()
        # Cache berlaku 1 jam (bukan 24 jam) agar perubahan status di CLS lebih cepat terasa
        self.cache_expires_at = timezone.now() + timedelta(hours=1)
        if product_name:
            self.product_name = product_name
        if client_name:
            self.client_name = client_name
        if expires_at:
            from django.utils.dateparse import parse_datetime
            if isinstance(expires_at, str):
                self.expires_at = parse_datetime(expires_at)
            else:
                self.expires_at = expires_at
        self.save()

    def save(self, *args, **kwargs):
        """Override save untuk memastikan hanya ada 1 record (singleton)."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Cegah penghapusan config."""
        pass
