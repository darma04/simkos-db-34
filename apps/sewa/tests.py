
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from apps.properti.models import Properti, TipeKamar, Kamar
from apps.penyewa.models import Penyewa
from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa


class PropertiTest(TestCase):
    def setUp(self):
        self.properti = Properti.objects.create(
            nama="Kost Mawar", tipe="kost", alamat="Jl. Mawar No. 1", kota="Jakarta"
        )

    def test_string_representation(self):
        self.assertIn("Kost Mawar", str(self.properti))

    def test_total_kamar_zero_on_empty(self):
        self.assertEqual(self.properti.total_kamar, 0)

    def test_total_kamar_with_rooms(self):
        tipe = TipeKamar.objects.create(nama="AC", harga_bulanan=Decimal("1500000"))
        Kamar.objects.create(properti=self.properti, tipe_kamar=tipe, nomor_kamar="101")
        Kamar.objects.create(properti=self.properti, tipe_kamar=tipe, nomor_kamar="102")
        self.assertEqual(self.properti.total_kamar, 2)

    def test_kamar_tersedia_default(self):
        tipe = TipeKamar.objects.create(nama="Non-AC", harga_bulanan=Decimal("1000000"))
        Kamar.objects.create(properti=self.properti, tipe_kamar=tipe, nomor_kamar="101")
        self.assertEqual(self.properti.kamar_tersedia, 1)
        self.assertEqual(self.properti.kamar_terisi, 0)

    def test_kamar_counts_with_mixed_status(self):
        tipe = TipeKamar.objects.create(nama="Standard", harga_bulanan=Decimal("1200000"))
        Kamar.objects.create(properti=self.properti, tipe_kamar=tipe, nomor_kamar="101")
        Kamar.objects.create(properti=self.properti, tipe_kamar=tipe, nomor_kamar="102", status="terisi")
        Kamar.objects.create(properti=self.properti, tipe_kamar=tipe, nomor_kamar="103", status="maintenance")
        self.assertEqual(self.properti.total_kamar, 3)
        self.assertEqual(self.properti.kamar_tersedia, 1)
        self.assertEqual(self.properti.kamar_terisi, 1)


class TipeKamarTest(TestCase):
    def test_create_tipe_kamar(self):
        tipe = TipeKamar.objects.create(nama="VIP", harga_bulanan=Decimal("2000000"))
        self.assertIn("VIP", str(tipe))

    def test_harga_bulanan_default(self):
        tipe = TipeKamar.objects.create(nama="Standar")
        self.assertEqual(tipe.harga_bulanan, 0)

    def test_aktif_default(self):
        tipe = TipeKamar.objects.create(nama="Ekonomi")
        self.assertTrue(tipe.aktif)


class KamarTest(TestCase):
    def setUp(self):
        self.properti = Properti.objects.create(
            nama="Kost Melati", tipe="kost", alamat="Jl. Melati No. 2"
        )
        self.tipe = TipeKamar.objects.create(nama="AC", harga_bulanan=Decimal("1500000"))

    def test_create_kamar(self):
        kamar = Kamar.objects.create(
            properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="201"
        )
        self.assertIn("Kost Melati", str(kamar))
        self.assertIn("201", str(kamar))

    def test_status_default_tersedia(self):
        kamar = Kamar.objects.create(
            properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="201"
        )
        self.assertEqual(kamar.status, "tersedia")

    def test_harga_from_tipe(self):
        kamar = Kamar.objects.create(
            properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="201"
        )
        self.assertEqual(kamar.harga, Decimal("1500000"))

    def test_harga_zero_if_no_tipe(self):
        kamar = Kamar.objects.create(properti=self.properti, nomor_kamar="201")
        self.assertEqual(kamar.harga, 0)

    def test_unique_together_properti_nomor(self):
        Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="201")
        with self.assertRaises(Exception):
            Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="201")


class KontrakSewaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="pass")
        self.properti = Properti.objects.create(nama="Kost Melati", tipe="kost", alamat="Jl. Melati")
        self.tipe = TipeKamar.objects.create(nama="AC", harga_bulanan=Decimal("1500000"))
        self.kamar = Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="101")
        self.penyewa = Penyewa.objects.create(nama="Ahmad", telepon="08123456789")

    def test_auto_nomor_kontrak(self):
        kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        self.assertTrue(kontrak.nomor_kontrak.startswith("KTR/"))

    def test_kamar_menjadi_terisi_saat_kontrak_aktif(self):
        kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        self.kamar.refresh_from_db()
        self.assertEqual(self.kamar.status, "terisi")

    def test_kamar_kembali_tersedia_saat_kontrak_selesai(self):
        kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        kontrak.status = "selesai"
        kontrak.save()
        self.kamar.refresh_from_db()
        self.assertEqual(self.kamar.status, "tersedia")

    def test_kamar_kembali_tersedia_saat_kontrak_dibatalkan(self):
        kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        kontrak.status = "dibatalkan"
        kontrak.save()
        self.kamar.refresh_from_db()
        self.assertEqual(self.kamar.status, "tersedia")

    def test_kamar_tetap_terisi_jika_masih_ada_kontrak_aktif_lain(self):
        kamar2 = Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="102")
        kontrak1 = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=kamar2,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        kontrak2 = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=kamar2,
            tanggal_masuk=date(2026, 2, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        kontrak1.status = "selesai"
        kontrak1.save()
        kamar2.refresh_from_db()
        self.assertEqual(kamar2.status, "terisi")

    def test_clean_validates_tanggal_keluar_after_masuk(self):
        kontrak = KontrakSewa(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 3, 1),
            tanggal_keluar=date(2026, 2, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        with self.assertRaises(ValidationError):
            kontrak.clean()

    def test_clean_allows_tanggal_keluar_after_masuk(self):
        kontrak = KontrakSewa(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            tanggal_keluar=date(2026, 6, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        try:
            kontrak.clean()
        except ValidationError:
            self.fail("ValidationError raised for valid date range")

    def test_deposit_default_zero(self):
        kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        self.assertEqual(kontrak.deposit, 0)

    def test_string_representation(self):
        kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
            nomor_kontrak="KTR/2026/01/0001",
        )
        self.assertIn("Ahmad", str(kontrak))

    def test_explicit_nomor_tidak_diganti(self):
        kontrak = KontrakSewa.objects.create(
            nomor_kontrak="KTR-CUSTOM-001",
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        self.assertEqual(kontrak.nomor_kontrak, "KTR-CUSTOM-001")


class TagihanSewaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="pass")
        self.properti = Properti.objects.create(nama="Kost Mawar", tipe="kost", alamat="Jl. Mawar")
        self.tipe = TipeKamar.objects.create(nama="AC", harga_bulanan=Decimal("1500000"))
        self.kamar = Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="101")
        self.penyewa = Penyewa.objects.create(nama="Budi", telepon="081")
        self.kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )

    def test_auto_nomor_tagihan(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=2,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 2, 10),
            dibuat_oleh=self.user,
        )
        self.assertTrue(tagihan.nomor_tagihan.startswith("TGH/"))

    def test_status_default_belum_bayar(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=2,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 2, 10),
            dibuat_oleh=self.user,
        )
        self.assertEqual(tagihan.status, "belum_bayar")

    def test_total_dibayar_zero_when_no_payments(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=3,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 3, 10),
            dibuat_oleh=self.user,
        )
        self.assertEqual(tagihan.total_dibayar, 0)

    def test_sisa_tagihan_equal_jumlah_when_unpaid(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=3,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 3, 10),
            dibuat_oleh=self.user,
        )
        self.assertEqual(tagihan.sisa_tagihan, Decimal("1500000"))

    def test_status_auto_update_to_lunas_when_paid(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=4,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 4, 10),
            dibuat_oleh=self.user,
        )
        PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 4, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "lunas")

    def test_status_auto_update_to_sebagian_when_partially_paid(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=5,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 5, 10),
            dibuat_oleh=self.user,
        )
        PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 5, 5),
            jumlah_bayar=Decimal("500000"),
            dicatat_oleh=self.user,
        )
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "sebagian")

    def test_status_reverts_when_payment_deleted(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=6,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 6, 10),
            dibuat_oleh=self.user,
        )
        bayar = PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 6, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "lunas")
        bayar.delete()
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "belum_bayar")

    def test_unique_together_kontrak_periode(self):
        TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=7,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 7, 10),
            dibuat_oleh=self.user,
        )
        with self.assertRaises(Exception):
            TagihanSewa.objects.create(
                kontrak=self.kontrak,
                periode_bulan=7,
                periode_tahun=2026,
                jumlah=Decimal("1500000"),
                tanggal_jatuh_tempo=date(2026, 7, 10),
                dibuat_oleh=self.user,
            )

    def test_string_representation(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=8,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 8, 10),
            dibuat_oleh=self.user,
        )
        self.assertIn("Budi", str(tagihan))

    def test_explicit_nomor_tidak_diganti(self):
        tagihan = TagihanSewa.objects.create(
            nomor_tagihan="TGH-CUSTOM",
            kontrak=self.kontrak,
            periode_bulan=9,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 9, 10),
            dibuat_oleh=self.user,
        )
        self.assertEqual(tagihan.nomor_tagihan, "TGH-CUSTOM")

    def test_auto_recalc_status_after_adding_payment(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=10,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 10, 10),
            dibuat_oleh=self.user,
        )
        PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 10, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "lunas")


class PembayaranSewaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="pass")
        self.properti = Properti.objects.create(nama="Kost Mawar", tipe="kost", alamat="Jl. Mawar")
        self.tipe = TipeKamar.objects.create(nama="AC", harga_bulanan=Decimal("1500000"))
        self.kamar = Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="101")
        self.penyewa = Penyewa.objects.create(nama="Citra", telepon="081")
        self.kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("1500000"),
            dibuat_oleh=self.user,
        )
        self.tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=1,
            periode_tahun=2026,
            jumlah=Decimal("1500000"),
            tanggal_jatuh_tempo=date(2026, 1, 10),
            dibuat_oleh=self.user,
        )

    def test_auto_nomor_pembayaran(self):
        bayar = PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        self.assertTrue(bayar.nomor_pembayaran.startswith("BYR/"))

    def test_clean_allows_full_payment(self):
        bayar = PembayaranSewa(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        try:
            bayar.clean()
        except ValidationError:
            self.fail("ValidationError raised for valid full payment")

    def test_clean_allows_partial_payment(self):
        bayar = PembayaranSewa(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("500000"),
            dicatat_oleh=self.user,
        )
        try:
            bayar.clean()
        except ValidationError:
            self.fail("ValidationError raised for valid partial payment")

    def test_clean_raises_on_overpayment(self):
        bayar = PembayaranSewa(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("2000000"),
            dicatat_oleh=self.user,
        )
        with self.assertRaises(ValidationError):
            bayar.clean()

    def test_clean_allows_final_remaining_payment(self):
        PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 4),
            jumlah_bayar=Decimal("1000000"),
            dicatat_oleh=self.user,
        )
        bayar = PembayaranSewa(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("500000"),
            dicatat_oleh=self.user,
        )
        try:
            bayar.clean()
        except ValidationError:
            self.fail("ValidationError raised for valid remaining payment")

    def test_clean_raises_on_accumulated_overpayment(self):
        PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 4),
            jumlah_bayar=Decimal("1000000"),
            dicatat_oleh=self.user,
        )
        bayar = PembayaranSewa(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("600000"),
            dicatat_oleh=self.user,
        )
        with self.assertRaises(ValidationError):
            bayar.clean()

    def test_clean_allows_edit_to_increase_payment(self):
        bayar = PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 4),
            jumlah_bayar=Decimal("1000000"),
            dicatat_oleh=self.user,
        )
        bayar.jumlah_bayar = Decimal("1500000")
        try:
            bayar.clean()
        except ValidationError:
            self.fail("ValidationError raised when editing payment to increase amount")
        bayar.save()
        self.tagihan.refresh_from_db()
        self.assertEqual(self.tagihan.status, "lunas")

    def test_payment_triggers_tagihan_status_update(self):
        self.assertEqual(self.tagihan.status, "belum_bayar")
        PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        self.tagihan.refresh_from_db()
        self.assertEqual(self.tagihan.status, "lunas")

    def test_multiple_payments_accumulate(self):
        PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("500000"),
            dicatat_oleh=self.user,
        )
        PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 10),
            jumlah_bayar=Decimal("1000000"),
            dicatat_oleh=self.user,
        )
        self.tagihan.refresh_from_db()
        self.assertEqual(self.tagihan.total_dibayar, Decimal("1500000"))
        self.assertEqual(self.tagihan.status, "lunas")

    def test_string_representation(self):
        bayar = PembayaranSewa.objects.create(
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        self.assertIn("BYR/", str(bayar))
        self.assertIn("1500000", str(bayar).replace(",", ""))

    def test_explicit_nomor_tidak_diganti(self):
        bayar = PembayaranSewa.objects.create(
            nomor_pembayaran="BYR-CUSTOM-001",
            tagihan=self.tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("1500000"),
            dicatat_oleh=self.user,
        )
        self.assertEqual(bayar.nomor_pembayaran, "BYR-CUSTOM-001")


class PostDeleteSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="pass")
        self.properti = Properti.objects.create(nama="Kost Anggrek", tipe="kost", alamat="Jl. Anggrek")
        self.tipe = TipeKamar.objects.create(nama="AC", harga_bulanan=Decimal("2000000"))
        self.kamar = Kamar.objects.create(properti=self.properti, tipe_kamar=self.tipe, nomor_kamar="301")
        self.penyewa = Penyewa.objects.create(nama="Dewi", telepon="081")
        self.kontrak = KontrakSewa.objects.create(
            penyewa=self.penyewa,
            kamar=self.kamar,
            tanggal_masuk=date(2026, 1, 1),
            harga_sewa=Decimal("2000000"),
            dibuat_oleh=self.user,
        )

    def test_revert_tagihan_status_on_pembayaran_delete_lunas_to_belum(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=1,
            periode_tahun=2026,
            jumlah=Decimal("2000000"),
            tanggal_jatuh_tempo=date(2026, 1, 10),
            dibuat_oleh=self.user,
        )
        bayar = PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 1, 5),
            jumlah_bayar=Decimal("2000000"),
            dicatat_oleh=self.user,
        )
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "lunas")
        bayar.delete()
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "belum_bayar")

    def test_revert_tagihan_status_on_pembayaran_delete_lunas_to_sebagian(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=2,
            periode_tahun=2026,
            jumlah=Decimal("2000000"),
            tanggal_jatuh_tempo=date(2026, 2, 10),
            dibuat_oleh=self.user,
        )
        bayar1 = PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 2, 5),
            jumlah_bayar=Decimal("1000000"),
            dicatat_oleh=self.user,
        )
        bayar2 = PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 2, 10),
            jumlah_bayar=Decimal("1000000"),
            dicatat_oleh=self.user,
        )
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "lunas")
        bayar2.delete()
        tagihan.refresh_from_db()
        self.assertEqual(tagihan.status, "sebagian")

    def test_signal_handles_tagihan_deletion_gracefully(self):
        tagihan = TagihanSewa.objects.create(
            kontrak=self.kontrak,
            periode_bulan=3,
            periode_tahun=2026,
            jumlah=Decimal("2000000"),
            tanggal_jatuh_tempo=date(2026, 3, 10),
            dibuat_oleh=self.user,
        )
        bayar = PembayaranSewa.objects.create(
            tagihan=tagihan,
            tanggal_bayar=date(2026, 3, 5),
            jumlah_bayar=Decimal("2000000"),
            dicatat_oleh=self.user,
        )
        tagihan.delete()
        bayar.delete()
