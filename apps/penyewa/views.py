"""
==========================================================================
 PENYEWA VIEWS - Views CRUD untuk manajemen penyewa
==========================================================================
"""

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
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from apps.penyewa.models import Penyewa
from apps.penyewa.forms import PenyewaForm
from web_project import TemplateLayout
from django.db import transaction
from apps.core.mixins import (
    ReadPermissionMixin, CreatePermissionMixin,
    UpdatePermissionMixin, DeletePermissionMixin,
)


class PenyewaListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """Daftar semua penyewa."""
    model = Penyewa
    template_name = 'penyewa/penyewa_list.html'
    context_object_name = 'penyewa_list'
    permission_module = 'penyewa'
    permission_sub_module = 'penyewa'

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if q:
            qs = qs.filter(nama__icontains=q)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_penyewa'] = qs.count()
        context['penyewa_aktif'] = qs.filter(status='aktif').count()
        return context



class PenyewaDetailView(ReadPermissionMixin, DetailView):
    """Detail penyewa lengkap dengan riwayat kontrak."""
    model = Penyewa
    template_name = 'penyewa/penyewa_detail.html'
    context_object_name = 'penyewa'
    permission_module = 'penyewa'
    permission_sub_module = 'penyewa'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from apps.sewa.models import KontrakSewa
        context['kontrak_list'] = KontrakSewa.objects.filter(
            penyewa=self.object
        ).select_related('kamar', 'kamar__properti').order_by('-tanggal_masuk')
        return context


class PenyewaCreateView(CreatePermissionMixin, CreateView):
    model = Penyewa
    form_class = PenyewaForm
    template_name = 'penyewa/penyewa_form.html'
    success_url = reverse_lazy('penyewa:list')
    permission_module = 'penyewa'
    permission_sub_module = 'penyewa'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Penyewa'
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        """Simpan data penyewa baru."""
        messages.success(self.request, 'Penyewa berhasil ditambahkan')
        return super().form_valid(form)


class PenyewaUpdateView(UpdatePermissionMixin, UpdateView):
    model = Penyewa
    form_class = PenyewaForm
    template_name = 'penyewa/penyewa_form.html'
    success_url = reverse_lazy('penyewa:list')
    permission_module = 'penyewa'
    permission_sub_module = 'penyewa'
    permission_action = 'write'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Penyewa'
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        """Update data penyewa."""
        messages.success(self.request, 'Data penyewa berhasil diperbarui')
        return super().form_valid(form)


class PenyewaDeleteView(DeletePermissionMixin, DeleteView):
    model = Penyewa
    success_url = reverse_lazy('penyewa:list')
    permission_module = 'penyewa'
    permission_sub_module = 'penyewa'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nama = self.object.nama
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Penyewa {nama} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus penyewa "{self.object.nama}" karena masih memiliki kontrak sewa aktif. Silakan hapus atau akhiri kontrak terkait terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)
