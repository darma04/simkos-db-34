"""
==========================================================================
 SEWA MODELS - Kontrak Sewa, Tagihan, dan Pembayaran
==========================================================================
 1. KontrakSewa   - Kontrak sewa penyewa dengan kamar tertentu
 2. TagihanSewa   - Tagihan bulanan yang dibuat dari kontrak
 3. PembayaranSewa - Record pembayaran dari penyewa
==========================================================================
"""

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from apps.properti.models import Kamar
from apps.penyewa.models import Penyewa


class KontrakSewa(models.Model):
    """Model untuk KONTRAK SEWA antara penyewa dan kamar."""

    STATUS_CHOICES = [
        ('aktif', 'Aktif'),
        ('selesai', 'Selesai'),
        ('dibatalkan', 'Dibatalkan'),
    ]

    nomor_kontrak = models.CharField(max_length=50, unique=True, verbose_name="Nomor Kontrak")
    penyewa = models.ForeignKey(Penyewa, on_delete=models.PROTECT, related_name='kontrak', verbose_name="Penyewa")
    kamar = models.ForeignKey(Kamar, on_delete=models.PROTECT, related_name='kontrak', verbose_name="Kamar")
    tanggal_masuk = models.DateField(verbose_name="Tanggal Masuk")
    tanggal_keluar = models.DateField(blank=True, null=True, verbose_name="Tanggal Keluar (Rencana)")
    harga_sewa = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="Harga Sewa per Bulan (Rp)")
    deposit = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Deposit (Rp)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='aktif', verbose_name="Status")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='kontrak_dibuat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Kontrak Sewa"
        verbose_name_plural = "Kontrak Sewa"
        ordering = ['-dibuat_pada']

    def __str__(self):
        return f"{self.nomor_kontrak} - {self.penyewa.nama}"

    def clean(self):
        """Validasi tanggal kontrak: tanggal_keluar harus setelah tanggal_masuk."""
        if self.tanggal_masuk and self.tanggal_keluar:
            if self.tanggal_keluar <= self.tanggal_masuk:
                raise ValidationError({
                    'tanggal_keluar': 'Tanggal keluar harus setelah tanggal masuk.'
                })

    def save(self, *args, **kwargs):
        if not self.nomor_kontrak:
            self.nomor_kontrak = self.generate_nomor()
        with transaction.atomic():
            # Update status kamar berdasarkan status kontrak
            if self.status == 'aktif':
                self.kamar.status = 'terisi'
                self.kamar.save()
            elif self.status in ('selesai', 'dibatalkan'):
                # Revert kamar ke 'tersedia' jika tidak ada kontrak aktif lain di kamar ini
                kontrak_aktif_lain = KontrakSewa.objects.filter(
                    kamar=self.kamar, status='aktif'
                ).exclude(pk=self.pk).exists()
                if not kontrak_aktif_lain:
                    self.kamar.status = 'tersedia'
                    self.kamar.save()
            super().save(*args, **kwargs)

    def generate_nomor(self):
        """Generate nomor kontrak: KTR/2026/02/0001"""
        from datetime import datetime
        today = datetime.now()
        prefix = f"KTR/{today.year}/{today.month:02d}"
        last = KontrakSewa.objects.filter(
            nomor_kontrak__startswith=prefix
        ).order_by('-nomor_kontrak').first()

        if last:
            try:
                last_number = int(last.nomor_kontrak.split('/')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        return f"{prefix}/{new_number:04d}"


class TagihanSewa(models.Model):
    """Model untuk TAGIHAN SEWA bulanan.

    Field jumlah_bayar dan metode_pembayaran berfungsi sebagai shortcut
    untuk mencatat deposit/bayar langsung dari form tagihan.
    Saat disimpan dengan jumlah_bayar > 0, otomatis membuat record
    PembayaranSewa yang terhubung — data terintegrasi real-time.
    """

    STATUS_CHOICES = [
        ('belum_bayar', 'Belum Bayar'),
        ('lunas', 'Lunas'),
        ('sebagian', 'Bayar Sebagian'),
        ('terlambat', 'Terlambat'),
    ]

    nomor_tagihan = models.CharField(max_length=50, unique=True, verbose_name="Nomor Tagihan")
    kontrak = models.ForeignKey(KontrakSewa, on_delete=models.CASCADE, related_name='tagihan', verbose_name="Kontrak")
    periode_bulan = models.PositiveIntegerField(verbose_name="Bulan")
    periode_tahun = models.PositiveIntegerField(verbose_name="Tahun")
    jumlah = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="Jumlah Tagihan (Rp)")
    jumlah_bayar = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="Jumlah Bayar (Rp)",
                                        help_text="Nominal deposit/bayar langsung saat buat tagihan")
    metode_pembayaran = models.CharField(max_length=50, blank=True, null=True, verbose_name="Metode Pembayaran",
                                          help_text="Metode pembayaran (Transfer, Tunai, dll)")
    tanggal_jatuh_tempo = models.DateField(verbose_name="Jatuh Tempo")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='belum_bayar', verbose_name="Status")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    dibuat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tagihan_dibuat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tagihan Sewa"
        verbose_name_plural = "Tagihan Sewa"
        ordering = ['-periode_tahun', '-periode_bulan']
        unique_together = ['kontrak', 'periode_bulan', 'periode_tahun']

    def __str__(self):
        return f"{self.nomor_tagihan} - {self.kontrak.penyewa.nama}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.nomor_tagihan:
                self.nomor_tagihan = self.generate_nomor()
            super().save(*args, **kwargs)
            # Re-evaluate status after save in case jumlah berubah
            if self.pk:
                total_bayar = self.total_dibayar
                if total_bayar >= self.jumlah:
                    new_status = 'lunas'
                elif total_bayar > 0:
                    new_status = 'sebagian'
                else:
                    new_status = 'belum_bayar'
                if self.status != new_status:
                    type(self).objects.filter(pk=self.pk).update(status=new_status)

    def generate_nomor(self):
        """Generate nomor tagihan: TGH/2026/02/0001"""
        from datetime import datetime
        today = datetime.now()
        prefix = f"TGH/{today.year}/{today.month:02d}"
        last = TagihanSewa.objects.filter(
            nomor_tagihan__startswith=prefix
        ).order_by('-nomor_tagihan').first()

        if last:
            try:
                last_number = int(last.nomor_tagihan.split('/')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        return f"{prefix}/{new_number:04d}"

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
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
        return self.metode_pembayaran

    @property
    def total_dibayar(self):
        """Total yang sudah dibayar untuk tagihan ini (dari semua record pembayaran)."""
        return self.pembayaran.aggregate(models.Sum('jumlah_bayar'))['jumlah_bayar__sum'] or 0

    @property
    def sisa_tagihan(self):
        """Sisa tagihan yang belum dibayar."""
        return self.jumlah - self.total_dibayar


class PembayaranSewa(models.Model):
    """Model untuk PEMBAYARAN SEWA dari penyewa."""

    # Choices metode bayar diambil dinamis dari MetodePembayaran di form
    nomor_pembayaran = models.CharField(max_length=50, unique=True, verbose_name="Nomor Pembayaran")
    tagihan = models.ForeignKey(TagihanSewa, on_delete=models.CASCADE, related_name='pembayaran', verbose_name="Tagihan")
    tanggal_bayar = models.DateField(verbose_name="Tanggal Bayar")
    jumlah_bayar = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="Jumlah Bayar (Rp)")
    metode_bayar = models.CharField(max_length=50, blank=True, null=True, verbose_name="Metode Bayar")
    bukti_bayar = models.FileField(upload_to='pembayaran/', blank=True, null=True, verbose_name="Bukti Bayar")
    catatan = models.TextField(blank=True, null=True, verbose_name="Catatan")

    dicatat_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='pembayaran_dicatat')
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pembayaran Sewa"
        verbose_name_plural = "Pembayaran Sewa"
        ordering = ['-tanggal_bayar']

    def __str__(self):
        return f"{self.nomor_pembayaran} - Rp {self.jumlah_bayar:,.0f}"

    def clean(self):
        """Validasi: pembayaran tidak boleh melebihi sisa tagihan."""
        if self.tagihan_id and self.jumlah_bayar:
            sisa = self.tagihan.sisa_tagihan
            # Jika ini edit (sudah punya pk), tambahkan kembali jumlah lama
            if self.pk:
                try:
                    old = PembayaranSewa.objects.get(pk=self.pk)
                    sisa += old.jumlah_bayar
                except PembayaranSewa.DoesNotExist:
                    pass
            if self.jumlah_bayar > sisa:
                raise ValidationError({
                    'jumlah_bayar': f'Jumlah bayar (Rp {self.jumlah_bayar:,.0f}) melebihi sisa tagihan (Rp {sisa:,.0f}).'
                })

    @property
    def nama_metode_bayar(self):
        """Ambil nama metode pembayaran dari model MetodePembayaran berdasarkan kode."""
        if not self.metode_bayar:
            return '-'
        try:
            from apps.pengaturan.models import MetodePembayaran
            metode = MetodePembayaran.objects.filter(kode=self.metode_bayar).first()
            if metode:
                return metode.nama
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
        # Fallback: tampilkan kode langsung jika MetodePembayaran tidak ditemukan
        return self.metode_bayar

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.nomor_pembayaran:
                self.nomor_pembayaran = self.generate_nomor()
            super().save(*args, **kwargs)
            # Update status tagihan setelah pembayaran
            self.update_status_tagihan()

    def generate_nomor(self):
        """Generate nomor pembayaran: BYR/2026/02/0001"""
        from datetime import datetime
        today = datetime.now()
        prefix = f"BYR/{today.year}/{today.month:02d}"
        last = PembayaranSewa.objects.filter(
            nomor_pembayaran__startswith=prefix
        ).order_by('-nomor_pembayaran').first()

        if last:
            try:
                last_number = int(last.nomor_pembayaran.split('/')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = 1
        else:
            new_number = 1
        return f"{prefix}/{new_number:04d}"

    def update_status_tagihan(self):
        """Update status tagihan berdasarkan total pembayaran."""
        tagihan = self.tagihan
        total_bayar = tagihan.total_dibayar
        if total_bayar >= tagihan.jumlah:
            new_status = 'lunas'
        elif total_bayar > 0:
            new_status = 'sebagian'
        else:
            new_status = 'belum_bayar'
        # Bypass save() override untuk hindari rekursi update_status
        type(tagihan).objects.filter(pk=tagihan.pk).update(status=new_status)


# ========================
#  POST-DELETE SIGNAL: REVERT STATUS TAGIHAN
# ========================
from django.db.models.signals import post_delete
from django.dispatch import receiver

import logging

logger = logging.getLogger(__name__)



@receiver(post_delete, sender=PembayaranSewa)
def _revert_tagihan_status_on_pembayaran_delete(sender, instance, **kwargs):
    """Re-evaluate status tagihan setelah pembayaran dihapus."""
    try:
        tagihan = instance.tagihan
        TagihanSewa.objects.filter(pk=tagihan.pk).exists() or None
        tagihan.refresh_from_db()
        total_bayar = tagihan.total_dibayar
        if total_bayar >= tagihan.jumlah:
            new_status = 'lunas'
        elif total_bayar > 0:
            new_status = 'sebagian'
        else:
            new_status = 'belum_bayar'
        TagihanSewa.objects.filter(pk=tagihan.pk).update(status=new_status)
    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)
