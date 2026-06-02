"""
==========================================================================
 LAPORAN VIEWS - Laporan SIMKOS (Pemasukan, Pengeluaran, Hunian, Keuangan)
==========================================================================
"""
from django.views.generic import TemplateView, ListView
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from web_project import TemplateLayout
from django.db.models import Sum, Count, Q
from datetime import datetime


@method_decorator(login_required, name='dispatch')
class LaporanPemasukanView(TemplateView):
    """Laporan Pemasukan — pembayaran sewa dari penyewa."""
    template_name = 'laporan/pemasukan.html'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.sewa.models import PembayaranSewa
        from apps.penyewa.models import Penyewa

        # Filter tanggal
        start_date = self.request.GET.get('start_date', '')
        end_date = self.request.GET.get('end_date', '')
        filter_penyewa = self.request.GET.get('penyewa', '')

        qs = PembayaranSewa.objects.select_related('tagihan__kontrak__penyewa').all()
        if start_date:
            qs = qs.filter(tanggal_bayar__gte=start_date)
        if end_date:
            qs = qs.filter(tanggal_bayar__lte=end_date)
        if filter_penyewa:
            qs = qs.filter(tagihan__kontrak__penyewa__id=filter_penyewa)

        context['pembayaran_list'] = qs.order_by('-tanggal_bayar')
        context['total_pemasukan'] = qs.aggregate(total=Sum('jumlah_bayar'))['total'] or 0
        context['total_transaksi'] = qs.count()
        context['start_date'] = start_date
        context['end_date'] = end_date
        context['filter_penyewa'] = filter_penyewa
        context['penyewa_list'] = Penyewa.objects.filter(status='aktif').order_by('nama')
        return context


@method_decorator(login_required, name='dispatch')
class LaporanPengeluaranView(TemplateView):
    """Laporan Pengeluaran — transaksi biaya operasional."""
    template_name = 'laporan/pengeluaran.html'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.biaya.models import TransaksiBiaya, KategoriBiaya

        start_date = self.request.GET.get('start_date', '')
        end_date = self.request.GET.get('end_date', '')
        filter_kategori = self.request.GET.get('kategori', '')

        qs = TransaksiBiaya.objects.select_related('kategori').filter(
            status='approved'
        )
        if start_date:
            qs = qs.filter(tanggal__gte=start_date)
        if end_date:
            qs = qs.filter(tanggal__lte=end_date)
        if filter_kategori:
            qs = qs.filter(kategori__id=filter_kategori)

        context['biaya_list'] = qs.order_by('-tanggal')
        context['total_pengeluaran'] = qs.aggregate(total=Sum('jumlah'))['total'] or 0
        context['total_transaksi'] = qs.count()
        context['start_date'] = start_date
        context['end_date'] = end_date
        context['filter_kategori'] = filter_kategori
        context['kategori_list'] = KategoriBiaya.objects.filter(aktif=True).order_by('nama')
        return context


@method_decorator(login_required, name='dispatch')
class LaporanHunianView(TemplateView):
    """Laporan Hunian — statistik kamar dan penyewa."""
    template_name = 'laporan/hunian.html'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.properti.models import Properti, Kamar
        from apps.sewa.models import KontrakSewa

        properti_list = Properti.objects.filter(aktif=True)
        data = []
        for p in properti_list:
            kamar = Kamar.objects.filter(properti=p)
            total = kamar.count()
            terisi = kamar.filter(status='terisi').count()
            tersedia = kamar.filter(status='tersedia').count()
            hunian = round((terisi / total * 100), 1) if total > 0 else 0
            data.append({
                'properti': p,
                'total_kamar': total,
                'kamar_terisi': terisi,
                'kamar_tersedia': tersedia,
                'tingkat_hunian': hunian,
            })

        total_kamar = Kamar.objects.count()
        total_terisi = Kamar.objects.filter(status='terisi').count()

        context['data_properti'] = data
        context['total_kamar'] = total_kamar
        context['total_terisi'] = total_terisi
        context['total_tersedia'] = Kamar.objects.filter(status='tersedia').count()
        context['tingkat_hunian'] = round((total_terisi / total_kamar * 100), 1) if total_kamar > 0 else 0
        context['kontrak_aktif'] = KontrakSewa.objects.filter(status='aktif').count()
        return context


@method_decorator(login_required, name='dispatch')
class LaporanKeuanganView(TemplateView):
    """Laporan Keuangan — ringkasan pemasukan, pengeluaran, laba bersih."""
    template_name = 'laporan/keuangan.html'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.sewa.models import PembayaranSewa
        from apps.biaya.models import TransaksiBiaya

        start_date = self.request.GET.get('start_date', '')
        end_date = self.request.GET.get('end_date', '')
        jenis_filter = self.request.GET.get('jenis', '')

        # Pemasukan
        pemasukan_qs = PembayaranSewa.objects.select_related('tagihan__kontrak__penyewa').all()
        if start_date:
            pemasukan_qs = pemasukan_qs.filter(tanggal_bayar__gte=start_date)
        if end_date:
            pemasukan_qs = pemasukan_qs.filter(tanggal_bayar__lte=end_date)
        total_pemasukan = pemasukan_qs.aggregate(total=Sum('jumlah_bayar'))['total'] or 0

        # Pengeluaran (hanya yang sudah disetujui)
        pengeluaran_qs = TransaksiBiaya.objects.filter(status='approved')
        if start_date:
            pengeluaran_qs = pengeluaran_qs.filter(tanggal__gte=start_date)
        if end_date:
            pengeluaran_qs = pengeluaran_qs.filter(tanggal__lte=end_date)
        total_biaya = pengeluaran_qs.aggregate(total=Sum('jumlah'))['total'] or 0

        # Pengeluaran tambahan: Gaji karyawan yang sudah dibayar
        total_gaji = 0
        gaji_qs = None
        try:
            from apps.hr.models import Penggajian
            gaji_qs = Penggajian.objects.filter(status='dibayar').select_related('karyawan')
            if start_date:
                gaji_qs = gaji_qs.filter(tanggal_bayar__gte=start_date)
            if end_date:
                gaji_qs = gaji_qs.filter(tanggal_bayar__lte=end_date)
            total_gaji = gaji_qs.aggregate(total=Sum('gaji_bersih'))['total'] or 0
        except Exception:
            pass

        total_pengeluaran = total_biaya + total_gaji

        laba_bersih = total_pemasukan - total_pengeluaran
        margin = round((laba_bersih / total_pemasukan * 100), 1) if total_pemasukan > 0 else 0

        context['total_pemasukan'] = total_pemasukan
        context['total_pengeluaran'] = total_pengeluaran
        context['total_biaya'] = total_biaya
        context['total_gaji'] = total_gaji
        context['laba_bersih'] = laba_bersih
        context['margin_persen'] = margin
        context['total_trx_masuk'] = pemasukan_qs.count()
        context['total_trx_keluar'] = pengeluaran_qs.count() + (gaji_qs.count() if gaji_qs is not None else 0)
        context['pemasukan_list'] = pemasukan_qs.order_by('-tanggal_bayar')
        context['pengeluaran_list'] = pengeluaran_qs.order_by('-tanggal')
        context['gaji_list'] = gaji_qs.order_by('-tanggal_bayar') if gaji_qs is not None else []
        context['start_date'] = start_date
        context['end_date'] = end_date
        context['jenis_filter'] = jenis_filter
        return context
