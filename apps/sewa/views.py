"""
==========================================================================
 SEWA VIEWS - Views untuk Kontrak Sewa, Tagihan, dan Pembayaran
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

from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from apps.core.mixins import (
    ReadPermissionMixin, CreatePermissionMixin,
    UpdatePermissionMixin, DeletePermissionMixin,
)
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Sum
from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa
from apps.sewa.forms import KontrakSewaForm, TagihanSewaForm, PembayaranSewaForm
from web_project import TemplateLayout





# ╔══════════════════════════════════════════════════════════════╗
# ║                    KONTRAK SEWA CRUD                         ║
# ╚══════════════════════════════════════════════════════════════╝

class KontrakSewaListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    model = KontrakSewa
    template_name = 'sewa/kontrak_list.html'
    context_object_name = 'kontrak_list'
    permission_module = 'sewa'
    permission_sub_module = 'kontrak'

    def get_queryset(self):
        return super().get_queryset().select_related('penyewa', 'kamar', 'kamar__properti')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_kontrak'] = qs.count()
        context['kontrak_aktif'] = qs.filter(status='aktif').count()
        context['total_nominal'] = qs.aggregate(total=Sum('harga_sewa'))['total'] or 0
        return context


class KontrakSewaDetailView(ReadPermissionMixin, DetailView):
    model = KontrakSewa
    template_name = 'sewa/kontrak_detail.html'
    context_object_name = 'kontrak'
    permission_module = 'sewa'
    permission_sub_module = 'kontrak'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['tagihan_list'] = TagihanSewa.objects.filter(
            kontrak=self.object
        ).order_by('-periode_tahun', '-periode_bulan')
        return context


class KontrakSewaCreateView(CreatePermissionMixin, CreateView):
    model = KontrakSewa
    form_class = KontrakSewaForm
    template_name = 'sewa/kontrak_form.html'
    success_url = reverse_lazy('sewa:kontrak_list')
    permission_module = 'sewa'
    permission_sub_module = 'kontrak'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Buat Kontrak Sewa'
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        form.instance.dibuat_oleh = self.request.user
        messages.success(self.request, 'Kontrak sewa berhasil dibuat')
        return super().form_valid(form)


class KontrakSewaUpdateView(UpdatePermissionMixin, UpdateView):
    model = KontrakSewa
    form_class = KontrakSewaForm
    template_name = 'sewa/kontrak_form.html'
    success_url = reverse_lazy('sewa:kontrak_list')
    permission_module = 'sewa'
    permission_sub_module = 'kontrak'
    permission_action = 'write'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Kontrak Sewa'
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Kontrak sewa berhasil diperbarui')
        return super().form_valid(form)


class KontrakSewaDeleteView(DeletePermissionMixin, DeleteView):
    model = KontrakSewa
    success_url = reverse_lazy('sewa:kontrak_list')
    permission_module = 'sewa'
    permission_sub_module = 'kontrak'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nomor = self.object.nomor_kontrak
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Kontrak {nomor} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus kontrak "{self.object.nomor_kontrak}" karena masih memiliki tagihan atau pembayaran yang terkait. Silakan hapus data terkait terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
# ║                    TAGIHAN SEWA CRUD                         ║
# ╚══════════════════════════════════════════════════════════════╝

class TagihanSewaListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    model = TagihanSewa
    template_name = 'sewa/tagihan_list.html'
    context_object_name = 'tagihan_list'
    permission_module = 'sewa'
    permission_sub_module = 'tagihan'

    def get_queryset(self):
        return super().get_queryset().select_related('kontrak__penyewa')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_tagihan'] = qs.count()
        context['tagihan_belum_bayar'] = qs.filter(status__in=['belum_bayar', 'terlambat']).count()
        context['tagihan_lunas'] = qs.filter(status='lunas').count()
        context['total_nominal'] = qs.aggregate(total=Sum('jumlah'))['total'] or 0
        # Hitung total pembayaran dari semua tagihan yang ada
        from django.db.models import Subquery, OuterRef, DecimalField
        from django.db.models.functions import Coalesce
        context['total_sudah_bayar'] = PembayaranSewa.objects.aggregate(
            total=Sum('jumlah_bayar'))['total'] or 0
        return context


class TagihanSewaCreateView(CreatePermissionMixin, CreateView):
    model = TagihanSewa
    form_class = TagihanSewaForm
    template_name = 'sewa/tagihan_form.html'
    success_url = reverse_lazy('sewa:tagihan_list')
    permission_module = 'sewa'
    permission_sub_module = 'tagihan'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Buat Tagihan'
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        from django.db import transaction
        from datetime import date
        tagihan = form.save(commit=False)
        tagihan.dibuat_oleh = self.request.user
        tagihan.save()

        # Auto-create PembayaranSewa jika jumlah_bayar > 0
        jumlah_bayar = form.cleaned_data.get('jumlah_bayar') or 0
        metode = form.cleaned_data.get('metode_pembayaran') or ''
        if jumlah_bayar > 0:
            PembayaranSewa.objects.create(
                tagihan=tagihan,
                tanggal_bayar=date.today(),
                jumlah_bayar=jumlah_bayar,
                metode_bayar=metode,
                catatan=f"Pembayaran otomatis dari tagihan {tagihan.nomor_tagihan}",
                dicatat_oleh=self.request.user,
            )

        # Kirim notifikasi Telegram
        try:
            from apps.automation.signals import kirim_notifikasi_tagihan
            kirim_notifikasi_tagihan(tagihan)
        except Exception:
            pass  # Jangan block transaksi jika Telegram gagal

        messages.success(self.request, 'Tagihan berhasil dibuat')
        return super().form_valid(form)


class TagihanSewaUpdateView(UpdatePermissionMixin, UpdateView):
    model = TagihanSewa
    form_class = TagihanSewaForm
    template_name = 'sewa/tagihan_form.html'
    success_url = reverse_lazy('sewa:tagihan_list')
    permission_module = 'sewa'
    permission_sub_module = 'tagihan'
    permission_action = 'write'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Tagihan'
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        from django.db import transaction
        from datetime import date
        tagihan = form.save(commit=False)
        tagihan.save()

        # Auto-create/update PembayaranSewa jika jumlah_bayar berubah
        jumlah_bayar = form.cleaned_data.get('jumlah_bayar') or 0
        metode = form.cleaned_data.get('metode_pembayaran') or ''

        # Cari pembayaran otomatis yang sudah ada
        existing_auto = tagihan.pembayaran.filter(
            catatan__startswith="Pembayaran otomatis dari tagihan"
        ).first()

        if jumlah_bayar > 0:
            if existing_auto:
                # Update pembayaran yang sudah ada
                existing_auto.jumlah_bayar = jumlah_bayar
                existing_auto.metode_bayar = metode
                existing_auto.save()
            else:
                # Buat pembayaran baru
                PembayaranSewa.objects.create(
                    tagihan=tagihan,
                    tanggal_bayar=date.today(),
                    jumlah_bayar=jumlah_bayar,
                    metode_bayar=metode,
                    catatan=f"Pembayaran otomatis dari tagihan {tagihan.nomor_tagihan}",
                    dicatat_oleh=self.request.user,
                )
        elif existing_auto and jumlah_bayar == 0:
            # Hapus pembayaran otomatis jika jumlah_bayar diubah ke 0
            existing_auto.delete()

        messages.success(self.request, 'Tagihan berhasil diperbarui')
        return super().form_valid(form)


class TagihanSewaDeleteView(DeletePermissionMixin, DeleteView):
    model = TagihanSewa
    success_url = reverse_lazy('sewa:tagihan_list')
    permission_module = 'sewa'
    permission_sub_module = 'tagihan'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nomor = self.object.nomor_tagihan
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Tagihan {nomor} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus tagihan "{self.object.nomor_tagihan}" karena masih memiliki pembayaran yang terkait. Silakan hapus data pembayaran terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})


    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   PEMBAYARAN SEWA CRUD                       ║
# ╚══════════════════════════════════════════════════════════════╝

class PembayaranSewaListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    model = PembayaranSewa
    template_name = 'sewa/pembayaran_list.html'
    context_object_name = 'pembayaran_list'
    permission_module = 'sewa'
    permission_sub_module = 'pembayaran'

    def get_queryset(self):
        return super().get_queryset().select_related('tagihan__kontrak__penyewa')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_pembayaran'] = qs.count()
        context['total_nominal'] = qs.aggregate(total=Sum('jumlah_bayar'))['total'] or 0
        return context


class PembayaranSewaCreateView(CreatePermissionMixin, CreateView):
    model = PembayaranSewa
    form_class = PembayaranSewaForm
    template_name = 'sewa/pembayaran_form.html'
    success_url = reverse_lazy('sewa:pembayaran_list')
    permission_module = 'sewa'
    permission_sub_module = 'pembayaran'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Catat Pembayaran'
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        """Simpan pembayaran baru dan kirim notifikasi Telegram."""
        form.instance.dicatat_oleh = self.request.user
        response = super().form_valid(form)

        # Kirim notifikasi Telegram
        try:
            from apps.automation.signals import kirim_notifikasi_kwitansi
            kirim_notifikasi_kwitansi(self.object)
        except Exception:
            pass  # Jangan block transaksi jika Telegram gagal

        messages.success(self.request, 'Pembayaran berhasil dicatat')
        return response


class PembayaranSewaDeleteView(DeletePermissionMixin, DeleteView):
    model = PembayaranSewa
    success_url = reverse_lazy('sewa:pembayaran_list')
    permission_module = 'sewa'
    permission_sub_module = 'pembayaran'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nomor = self.object.nomor_pembayaran
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Pembayaran {nomor} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus pembayaran "{self.object.nomor_pembayaran}" karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
# ║                    CETAK TAGIHAN                             ║
# ╚══════════════════════════════════════════════════════════════╝

class TagihanCetakView(ReadPermissionMixin, DetailView):
    """Halaman cetak tagihan/invoice format A4."""
    model = TagihanSewa
    template_name = 'sewa/tagihan_cetak.html'
    context_object_name = 'tagihan'
    permission_module = 'sewa'
    permission_sub_module = 'tagihan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tagihan = self.object
        context['kontrak'] = tagihan.kontrak
        context['penyewa'] = tagihan.kontrak.penyewa
        context['kamar'] = tagihan.kontrak.kamar
        context['properti'] = tagihan.kontrak.kamar.properti
        context['pembayaran_list'] = tagihan.pembayaran.all().order_by('tanggal_bayar')
        # Data perusahaan untuk logo di header cetak
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            context['perusahaan'] = PengaturanPerusahaan.load()
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║                  PEMBAYARAN DETAIL & CETAK                    ║
# ╚══════════════════════════════════════════════════════════════╝

class PembayaranDetailView(ReadPermissionMixin, DetailView):
    """Halaman detail pembayaran."""
    model = PembayaranSewa
    template_name = 'sewa/pembayaran_detail.html'
    context_object_name = 'pembayaran'
    permission_module = 'sewa'
    permission_sub_module = 'pembayaran'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        p = self.object
        context['tagihan'] = p.tagihan
        context['kontrak'] = p.tagihan.kontrak
        context['penyewa'] = p.tagihan.kontrak.penyewa
        context['kamar'] = p.tagihan.kontrak.kamar
        context['properti'] = p.tagihan.kontrak.kamar.properti
        return context


class PembayaranCetakView(ReadPermissionMixin, DetailView):
    """Halaman cetak kwitansi pembayaran format A4."""
    model = PembayaranSewa
    template_name = 'sewa/pembayaran_cetak.html'
    context_object_name = 'pembayaran'
    permission_module = 'sewa'
    permission_sub_module = 'pembayaran'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        p = self.object
        context['tagihan'] = p.tagihan
        context['kontrak'] = p.tagihan.kontrak
        context['penyewa'] = p.tagihan.kontrak.penyewa
        context['kamar'] = p.tagihan.kontrak.kamar
        context['properti'] = p.tagihan.kontrak.kamar.properti
        # Data perusahaan untuk logo di header cetak
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            context['perusahaan'] = PengaturanPerusahaan.load()
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)
        return context

