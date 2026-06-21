"""
==========================================================================
 DASHBOARD VIEWS - Dashboard Utama SIMKOS (Sistem Manajemen Kost)
==========================================================================
 Menampilkan ringkasan bisnis kost/kontrakan:
 - Statistik properti dan kamar
 - Pemasukan & pengeluaran bulan ini
 - Tagihan yang belum dibayar
 - Penyewa aktif
 - Grafik pemasukan 6 bulan terakhir
 - Grafik status kamar (donut)
 - Grafik tagihan per bulan (bar)
==========================================================================
"""

import logging
logger = logging.getLogger(__name__)

# ==========================================================================
# PANDUAN DJANGO UNTUK DEVELOPER PEMULA (baca ini sebelum mempelajari views)
# ==========================================================================
#
# APA ITU CLASS-BASED VIEW (CBV)?
# - CBV = class Python yang menangani HTTP request dan return response
# - Django menyediakan CBV bawaan: ListView, CreateView, UpdateView, DeleteView
# - Setiap CBV punya "lifecycle" (siklus hidup) yang bisa di-customize
#
# SIKLUS HIDUP CBV (urutan method yang dipanggil):
# 1. as_view()     → Entry point, dipanggil oleh URL router
# 2. dispatch()    → Tentukan method (GET/POST) → panggil get() atau post()
# 3. get()/post()  → Handle request, kumpulkan data
# 4. get_queryset()→ Ambil data dari database (bisa di-filter/optimasi)
# 5. get_context_data() → Siapkan data untuk template (variabel {{ }})
# 6. render()      → Gabungkan template + context → HTML response
#
# METHOD PENTING YANG SERING DI-OVERRIDE:
# - get_queryset()     → Optimasi query (prefetch_related, select_related)
# - get_context_data() → Tambah variabel ke template (self.context)
# - form_valid()       → Proses setelah form divalidasi (sebelum save)
# - get_success_url()  → URL redirect setelah operasi berhasil
#
# DECORATOR YANG SERING DIGUNAKAN:
# @login_required       → User HARUS login, jika tidak → redirect ke /login/
# @permission_required  → User harus punya permission tertentu (RBAC)
# @require_http_methods → Batasi method yang diterima (GET, POST, dll)
# @never_cache          → Response tidak boleh di-cache oleh browser
#
# POLA UMUM VIEW DI PROYEK INI:
# class MyListView(SubModulePermissionMixin, ListView):
#     module_name = 'nama_modul'          # Untuk pengecekan RBAC
#     sub_module_name = 'nama_sub_modul'  # Sub-modul yang diakses
#     model = MyModel                      # Model database yang dipakai
#     template_name = 'modul/page.html'    # File HTML template
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context = TemplateLayout.init(self, context)  # WAJIB: setup layout
#         context['data_tambahan'] = ...    # Tambah data custom
#         return context
# ==========================================================================

from django.views.generic import TemplateView
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from web_project import TemplateLayout
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal
import json
import traceback

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    relativedelta = None



@method_decorator(login_required, name='dispatch')
class DashboardView(TemplateView):
    """View utama DASHBOARD SIMKOS."""
    template_name = 'dashboard/dashboard.html'

    def _parse_date_filter(self):
        """Parse start_date dan end_date dari query params."""
        now = datetime.now()
        start_str = self.request.GET.get('start_date', '')
        end_str = self.request.GET.get('end_date', '')
        start_date = None
        end_date = None
        filter_label = now.strftime('%B %Y')  # default: "March 2026"
        is_filtered = False

        if start_str:
            try:
                start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            except ValueError:
                start_date = None
        if end_str:
            try:
                end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            except ValueError:
                end_date = None

        if start_date and end_date:
            is_filtered = True
            nama_bulan = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
                          'Jul', 'Ags', 'Sep', 'Okt', 'Nov', 'Des']
            filter_label = f"{start_date.strftime('%d')} {nama_bulan[start_date.month]} {start_date.year} — {end_date.strftime('%d')} {nama_bulan[end_date.month]} {end_date.year}"
        elif start_date:
            is_filtered = True
            filter_label = f"Sejak {start_date.strftime('%d/%m/%Y')}"

        return start_date, end_date, filter_label, is_filtered

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        now = datetime.now()
        start_date, end_date, filter_label, is_filtered = self._parse_date_filter()

        # Tentukan range default (bulan ini) jika tidak ada filter
        if not is_filtered:
            bulan_ini = now.month
            tahun_ini = now.year
        else:
            bulan_ini = None
            tahun_ini = None

        # Label dinamis berdasarkan filter
        if is_filtered:
            label_periode = 'Periode Ini'
        else:
            label_periode = 'Bulan Ini'

        try:
            # ── Statistik Properti ──
            from apps.properti.models import Properti, Kamar, TipeKamar
            total_properti = Properti.objects.filter(aktif=True).count()
            total_kamar = Kamar.objects.count()
            kamar_tersedia = Kamar.objects.filter(status='tersedia').count()
            kamar_terisi = Kamar.objects.filter(status='terisi').count()
            kamar_maintenance = Kamar.objects.filter(status='maintenance').count()

            # Tingkat hunian
            tingkat_hunian = 0
            if total_kamar > 0:
                tingkat_hunian = round((kamar_terisi / total_kamar) * 100, 1)

            # ── Statistik Penyewa ──
            from apps.penyewa.models import Penyewa
            total_penyewa = Penyewa.objects.filter(status='aktif').count()
            total_penyewa_semua = Penyewa.objects.count()

            # ── Statistik Keuangan ──
            from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa
            kontrak_aktif = KontrakSewa.objects.filter(status='aktif').count()

            # Filter pemasukan & pengeluaran
            from apps.biaya.models import TransaksiBiaya
            if is_filtered and start_date and end_date:
                pembayaran_qs = PembayaranSewa.objects.filter(
                    tanggal_bayar__gte=start_date,
                    tanggal_bayar__lte=end_date
                )
                pengeluaran_qs = TransaksiBiaya.objects.filter(
                    tanggal__gte=start_date,
                    tanggal__lte=end_date,
                    status='approved'
                )
            elif is_filtered and start_date:
                pembayaran_qs = PembayaranSewa.objects.filter(
                    tanggal_bayar__gte=start_date
                )
                pengeluaran_qs = TransaksiBiaya.objects.filter(
                    tanggal__gte=start_date,
                    status='approved'
                )
            else:
                pembayaran_qs = PembayaranSewa.objects.filter(
                    tanggal_bayar__month=bulan_ini,
                    tanggal_bayar__year=tahun_ini
                )
                pengeluaran_qs = TransaksiBiaya.objects.filter(
                    tanggal__month=bulan_ini,
                    tanggal__year=tahun_ini,
                    status='approved'
                )

            pemasukan_bulan_ini = pembayaran_qs.aggregate(
                total=Sum('jumlah_bayar'))['total'] or 0
            pengeluaran_biaya = pengeluaran_qs.aggregate(
                total=Sum('jumlah'))['total'] or 0

            # Tambahkan gaji karyawan yang sudah dibayar (konsisten dengan Laporan Keuangan)
            try:
                from apps.hr.models import Penggajian
                if is_filtered and start_date and end_date:
                    gaji_qs = Penggajian.objects.filter(
                        status='dibayar',
                        tanggal_bayar__gte=start_date,
                        tanggal_bayar__lte=end_date,
                    )
                elif is_filtered and start_date:
                    gaji_qs = Penggajian.objects.filter(
                        status='dibayar',
                        tanggal_bayar__gte=start_date,
                    )
                else:
                    gaji_qs = Penggajian.objects.filter(
                        status='dibayar',
                        tanggal_bayar__month=bulan_ini,
                        tanggal_bayar__year=tahun_ini,
                    )
                pengeluaran_gaji = gaji_qs.aggregate(total=Sum('gaji_bersih'))['total'] or 0
            except Exception:
                pengeluaran_gaji = 0

            pengeluaran_bulan_ini = pengeluaran_biaya + pengeluaran_gaji

            # Tagihan belum bayar (filter by jatuh tempo jika ada filter)
            tagihan_pending_qs = TagihanSewa.objects.filter(
                status__in=['belum_bayar', 'sebagian', 'terlambat']
            )
            if is_filtered and start_date and end_date:
                tagihan_pending_qs = tagihan_pending_qs.filter(
                    tanggal_jatuh_tempo__gte=start_date,
                    tanggal_jatuh_tempo__lte=end_date
                )
            tagihan_pending = tagihan_pending_qs.count()
            # Hitung sisa tagihan = SUM(jumlah) - SUM(pembayaran) per tagihan, agregat dalam 2 query
            from django.db.models import Sum as _Sum, F
            total_jumlah_pending = tagihan_pending_qs.aggregate(t=_Sum('jumlah'))['t'] or 0
            total_dibayar_pending = (
                PembayaranSewa.objects.filter(tagihan__in=tagihan_pending_qs)
                .aggregate(t=_Sum('jumlah_bayar'))['t'] or 0
            )
            total_tagihan_pending = total_jumlah_pending - total_dibayar_pending

            # Pembayaran terbaru (5) — filter jika ada date range
            pembayaran_terbaru_qs = PembayaranSewa.objects.select_related(
                'tagihan__kontrak__penyewa'
            )
            if is_filtered and start_date and end_date:
                pembayaran_terbaru_qs = pembayaran_terbaru_qs.filter(
                    tanggal_bayar__gte=start_date,
                    tanggal_bayar__lte=end_date
                )
            pembayaran_terbaru = pembayaran_terbaru_qs.order_by('-dibuat_pada')[:5]

            # Kontrak akan berakhir (30 hari ke depan)
            tgl_30_hari = now.date() + timedelta(days=30)
            kontrak_akan_habis = KontrakSewa.objects.filter(
                status='aktif',
                tanggal_keluar__isnull=False,
                tanggal_keluar__lte=tgl_30_hari
            ).select_related('penyewa', 'kamar')[:5]

            # Tagihan terbaru belum bayar — filter jika ada date range
            tagihan_terbaru_qs = TagihanSewa.objects.filter(
                status__in=['belum_bayar', 'terlambat']
            ).select_related('kontrak__penyewa')
            if is_filtered and start_date and end_date:
                tagihan_terbaru_qs = tagihan_terbaru_qs.filter(
                    tanggal_jatuh_tempo__gte=start_date,
                    tanggal_jatuh_tempo__lte=end_date
                )
            tagihan_terbaru = tagihan_terbaru_qs.order_by('tanggal_jatuh_tempo')[:5]

            # ── Data untuk Grafik ──
            nama_bulan = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
                          'Jul', 'Ags', 'Sep', 'Okt', 'Nov', 'Des']
            nama_hari = ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min']

            # Helper: hitung pengeluaran (biaya approved + gaji dibayar) dalam rentang tanggal
            try:
                from apps.hr.models import Penggajian as _Penggajian
            except Exception:
                _Penggajian = None

            def _hitung_pengeluaran_periode(filter_kwargs_biaya, filter_kwargs_gaji):
                """Hitung total pengeluaran (TransaksiBiaya approved + Penggajian dibayar)."""
                biaya = TransaksiBiaya.objects.filter(
                    status='approved', **filter_kwargs_biaya
                ).aggregate(total=Sum('jumlah'))['total'] or 0
                gaji = 0
                if _Penggajian is not None:
                    gaji = _Penggajian.objects.filter(
                        status='dibayar', **filter_kwargs_gaji
                    ).aggregate(total=Sum('gaji_bersih'))['total'] or 0
                return float(biaya) + float(gaji)

            # 1. Grafik Pemasukan & Pengeluaran (Agregasi Dinamis)
            chart_labels = []
            chart_pemasukan = []
            chart_pengeluaran = []
            chart_type = 'area'  # selalu area/gelombang

            if is_filtered and start_date and end_date:
                # Hitung jumlah hari dalam range filter
                delta_days = (end_date - start_date).days + 1

                if delta_days <= 62:
                    # ── AGREGASI HARIAN (filter ≤ 62 hari) ──
                    chart_type = 'area'
                    # Jika hanya 1-2 hari, tambahkan hari sebelumnya sebagai konteks
                    # agar area chart punya cukup titik untuk menggambar gelombang
                    if delta_days <= 2:
                        current_date = start_date - timedelta(days=6)
                    else:
                        current_date = start_date
                    while current_date <= end_date:
                        # Label: "13 Mar" format
                        chart_labels.append(f"{current_date.day} {nama_bulan[current_date.month]}")

                        pemasukan = PembayaranSewa.objects.filter(
                            tanggal_bayar=current_date
                        ).aggregate(total=Sum('jumlah_bayar'))['total'] or 0
                        pengeluaran = _hitung_pengeluaran_periode(
                            {'tanggal': current_date},
                            {'tanggal_bayar': current_date},
                        )

                        chart_pemasukan.append(float(pemasukan))
                        chart_pengeluaran.append(pengeluaran)
                        current_date += timedelta(days=1)
                else:
                    # ── AGREGASI BULANAN (filter > 62 hari) ──
                    chart_type = 'area'
                    current_year = start_date.year
                    current_month = start_date.month
                    end_year = end_date.year
                    end_month_num = end_date.month

                    while (current_year < end_year) or (current_year == end_year and current_month <= end_month_num):
                        chart_labels.append(f"{nama_bulan[current_month]} {current_year}")

                        # Query hanya dalam range filter (bukan seluruh bulan)
                        import calendar
                        month_start = max(start_date, datetime(current_year, current_month, 1).date())
                        last_day = calendar.monthrange(current_year, current_month)[1]
                        month_end = min(end_date, datetime(current_year, current_month, last_day).date())

                        pemasukan = PembayaranSewa.objects.filter(
                            tanggal_bayar__gte=month_start,
                            tanggal_bayar__lte=month_end
                        ).aggregate(total=Sum('jumlah_bayar'))['total'] or 0
                        pengeluaran = _hitung_pengeluaran_periode(
                            {'tanggal__gte': month_start, 'tanggal__lte': month_end},
                            {'tanggal_bayar__gte': month_start, 'tanggal_bayar__lte': month_end},
                        )

                        chart_pemasukan.append(float(pemasukan))
                        chart_pengeluaran.append(pengeluaran)
                        current_month += 1
                        if current_month > 12:
                            current_month = 1
                            current_year += 1
            else:
                # Default: 6 bulan terakhir (agregasi bulanan)
                for i in range(5, -1, -1):
                    m = now.month - i
                    y = now.year
                    while m <= 0:
                        m += 12
                        y -= 1
                    chart_labels.append(f"{nama_bulan[m]} {y}")

                    pemasukan = PembayaranSewa.objects.filter(
                        tanggal_bayar__month=m,
                        tanggal_bayar__year=y
                    ).aggregate(total=Sum('jumlah_bayar'))['total'] or 0
                    pengeluaran = _hitung_pengeluaran_periode(
                        {'tanggal__month': m, 'tanggal__year': y},
                        {'tanggal_bayar__month': m, 'tanggal_bayar__year': y},
                    )

                    chart_pemasukan.append(float(pemasukan))
                    chart_pengeluaran.append(pengeluaran)

            # 2. Data Status Kamar (Donut Chart)
            chart_kamar_labels = json.dumps(['Tersedia', 'Terisi', 'Perbaikan'])
            chart_kamar_data = json.dumps([kamar_tersedia, kamar_terisi, kamar_maintenance])

            # 3. Data Tagihan per Status (Donut Chart)
            # Status Tagihan adalah overview keseluruhan (tidak difilter tanggal)
            # karena menunjukkan kondisi tagihan saat ini, bukan data transaksional
            tagihan_status_qs = TagihanSewa.objects.all()
            tagihan_belum = tagihan_status_qs.filter(status='belum_bayar').count()
            tagihan_sebagian = tagihan_status_qs.filter(status='sebagian').count()
            tagihan_lunas_count = tagihan_status_qs.filter(status='lunas').count()
            tagihan_terlambat_count = tagihan_status_qs.filter(status='terlambat').count()

            chart_tagihan_labels = json.dumps(['Belum Bayar', 'Sebagian', 'Lunas', 'Terlambat'])
            chart_tagihan_data = json.dumps([tagihan_belum, tagihan_sebagian, tagihan_lunas_count, tagihan_terlambat_count])

            # 4. Daftar Properti terbaru
            properti_list = Properti.objects.filter(aktif=True).order_by('-dibuat_pada')[:5]

            # Laba bersih
            laba_bersih = float(pemasukan_bulan_ini) - float(pengeluaran_bulan_ini)

            context.update({
                'total_properti': total_properti,
                'total_kamar': total_kamar,
                'kamar_tersedia': kamar_tersedia,
                'kamar_terisi': kamar_terisi,
                'kamar_maintenance': kamar_maintenance,
                'tingkat_hunian': tingkat_hunian,
                'total_penyewa': total_penyewa,
                'total_penyewa_semua': total_penyewa_semua,
                'kontrak_aktif': kontrak_aktif,
                'pemasukan_bulan_ini': pemasukan_bulan_ini,
                'pengeluaran_bulan_ini': pengeluaran_bulan_ini,
                'laba_bersih': laba_bersih,
                'tagihan_pending': tagihan_pending,
                'total_tagihan_pending': total_tagihan_pending,
                'pembayaran_terbaru': pembayaran_terbaru,
                'kontrak_akan_habis': kontrak_akan_habis,
                'tagihan_terbaru': tagihan_terbaru,
                'bulan_ini': filter_label,
                'label_periode': label_periode,
                'properti_list': properti_list,
                # Data chart JSON
                'chart_labels': json.dumps(chart_labels),
                'chart_pemasukan': json.dumps(chart_pemasukan),
                'chart_pengeluaran': json.dumps(chart_pengeluaran),
                'chart_type': chart_type,
                'chart_kamar_labels': chart_kamar_labels,
                'chart_kamar_data': chart_kamar_data,
                'chart_tagihan_labels': chart_tagihan_labels,
                'chart_tagihan_data': chart_tagihan_data,
                # Filter state
                'is_dashboard_page': True,
                'filter_start_date': self.request.GET.get('start_date', ''),
                'filter_end_date': self.request.GET.get('end_date', ''),
                'is_filtered': is_filtered,
            })

        except Exception as e:
            logger.error(f"Error loading dashboard data: {e}")
            logger.error(traceback.format_exc())
            print(f"[DASHBOARD ERROR] {e}")
            print(traceback.format_exc())
            context.update({
                'total_properti': 0, 'total_kamar': 0, 'kamar_tersedia': 0,
                'kamar_terisi': 0, 'kamar_maintenance': 0, 'tingkat_hunian': 0,
                'total_penyewa': 0, 'total_penyewa_semua': 0, 'kontrak_aktif': 0,
                'pemasukan_bulan_ini': 0, 'pengeluaran_bulan_ini': 0, 'laba_bersih': 0,
                'tagihan_pending': 0, 'total_tagihan_pending': 0,
                'pembayaran_terbaru': [], 'kontrak_akan_habis': [],
                'tagihan_terbaru': [], 'bulan_ini': now.strftime('%B %Y'),
                'label_periode': 'Bulan Ini',
                'properti_list': [],
                'chart_labels': '[]', 'chart_pemasukan': '[]', 'chart_pengeluaran': '[]',
                'chart_kamar_labels': '[]', 'chart_kamar_data': '[]',
                'chart_tagihan_labels': '[]', 'chart_tagihan_data': '[]',
                'is_dashboard_page': True,
                'filter_start_date': '', 'filter_end_date': '', 'is_filtered': False,
            })

        return context
