"""
==========================================================================
PROPERTI VIEWS - View CRUD untuk Properti, Tipe Kamar, Kamar
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

import json
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from apps.properti.models import Properti, TipeKamar, Kamar
from apps.properti.forms import PropertiForm, TipeKamarForm, KamarForm
from web_project import TemplateLayout
from django.db import transaction
from django.contrib.auth.decorators import login_required
from apps.core.mixins import (
    ReadPermissionMixin, CreatePermissionMixin,
    UpdatePermissionMixin, DeletePermissionMixin,
)


# ╔══════════════════════════════════════════════════════════════╗
# ║                     PROPERTI CRUD                            ║
# ╚══════════════════════════════════════════════════════════════╝

class PropertiListView(ReadPermissionMixin, ListView):
    permission_module = 'properti'
    permission_sub_module = 'properti'
    paginate_by = 50
    """Daftar semua properti. URL: /properti/"""
    model = Properti
    template_name = 'properti/properti_list.html'
    context_object_name = 'properti_list'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_properti'] = qs.count()
        context['total_aktif'] = qs.filter(aktif=True).count()
        context['total_kamar'] = Kamar.objects.count()
        context['kamar_terisi'] = Kamar.objects.filter(status='terisi').count()
        return context


class PropertiDetailView(ReadPermissionMixin, DetailView):
    permission_module = 'properti'
    permission_sub_module = 'properti'
    """Detail properti dengan denah kamar per lantai. URL: /properti/<pk>/"""
    model = Properti
    template_name = 'properti/properti_detail.html'
    context_object_name = 'properti'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        obj = self.object
        kamar_list = obj.kamar_set.all().select_related('tipe_kamar').order_by('lantai', 'nomor_kamar')

        # Ambil kontrak aktif per kamar untuk menampilkan nama penyewa & jumlah
        from apps.sewa.models import KontrakSewa
        kontrak_aktif = KontrakSewa.objects.filter(
            kamar__properti=obj, status='aktif'
        ).select_related('kamar', 'penyewa')
        penyewa_per_kamar = {}
        jumlah_per_kamar = {}
        for kontrak in kontrak_aktif:
            penyewa_per_kamar[kontrak.kamar_id] = kontrak.penyewa.nama
            jumlah_per_kamar[kontrak.kamar_id] = jumlah_per_kamar.get(kontrak.kamar_id, 0) + 1

        # Annotate each kamar with penyewa name and count
        for k in kamar_list:
            k.penyewa_nama = penyewa_per_kamar.get(k.pk, '')
            k.jumlah_penghuni = jumlah_per_kamar.get(k.pk, 0)

        # Group kamar per lantai untuk denah
        lantai_dict = {}
        for k in kamar_list:
            floor = k.lantai
            if floor not in lantai_dict:
                lantai_dict[floor] = []
            lantai_dict[floor].append(k)

        # Urutkan berdasarkan lantai
        lantai_sorted = sorted(lantai_dict.items(), key=lambda x: x[0])

        context['kamar_list'] = kamar_list
        context['lantai_data'] = lantai_sorted
        context['total_kamar'] = kamar_list.count()
        context['kamar_tersedia'] = kamar_list.filter(status='tersedia').count()
        context['kamar_terisi'] = kamar_list.filter(status='terisi').count()
        context['kamar_maintenance'] = kamar_list.filter(status='maintenance').count()

        # Tingkat hunian properti ini
        total = kamar_list.count()
        terisi = kamar_list.filter(status='terisi').count()
        context['tingkat_hunian'] = round((terisi / total * 100), 1) if total > 0 else 0

        # Tipe kamar untuk modal create/edit
        context['tipe_kamar_list'] = TipeKamar.objects.filter(aktif=True)

        return context


class PropertiCreateView(CreatePermissionMixin, CreateView):
    """Tambah properti baru. URL: /properti/add/"""
    permission_module = 'properti'
    permission_sub_module = 'properti'
    permission_action = 'create'
    model = Properti
    form_class = PropertiForm
    template_name = 'properti/properti_form.html'
    success_url = reverse_lazy('properti:properti_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Properti'
        context['is_edit'] = False
        return context


    def form_valid(self, form):


        form.instance.dibuat_oleh = self.request.user
        messages.success(self.request, 'Properti berhasil ditambahkan')
        return super().form_valid(form)


class PropertiUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit properti. URL: /properti/<pk>/edit/"""
    permission_module = 'properti'
    permission_sub_module = 'properti'
    permission_action = 'write'
    model = Properti
    form_class = PropertiForm
    template_name = 'properti/properti_form.html'
    success_url = reverse_lazy('properti:properti_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Properti'
        context['is_edit'] = True
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Properti berhasil diperbarui')
        return super().form_valid(form)


class PropertiDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus properti - return JSON untuk AJAX."""
    permission_module = 'properti'
    permission_sub_module = 'properti'
    permission_action = 'delete'
    model = Properti
    success_url = reverse_lazy('properti:properti_list')

    def delete(self, request, *args, **kwargs):
        from django.http import JsonResponse
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nama = self.object.nama
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Properti {nama} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus properti "{self.object.nama}" karena masih memiliki data kamar atau kontrak sewa yang terkait. Silakan hapus data terkait terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})

    # Django 5.0: post() tidak memanggil delete(), perlu alias
    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


    # ╔══════════════════════════════════════════════════════════════╗
    # ║                   TIPE KAMAR CRUD                            ║
    # ╚══════════════════════════════════════════════════════════════╝

class TipeKamarListView(ReadPermissionMixin, ListView):
    permission_module = 'properti'
    permission_sub_module = 'tipe_kamar'
    paginate_by = 50
    """Daftar tipe kamar. URL: /properti/tipe-kamar/"""
    model = TipeKamar
    template_name = 'properti/tipe_kamar_list.html'
    context_object_name = 'tipe_kamar_list'

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if q:
            qs = qs.filter(nama__icontains=q)
        if status == 'aktif':
            qs = qs.filter(aktif=True)
        elif status == 'nonaktif':
            qs = qs.filter(aktif=False)
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_tipe'] = qs.count()
        context['tipe_aktif'] = qs.filter(aktif=True).count()
        from django.db.models import Sum
        context['total_harga'] = qs.aggregate(total=Sum('harga_bulanan'))['total'] or 0
        return context



class TipeKamarCreateView(CreatePermissionMixin, CreateView):
    """Tambah tipe kamar baru."""
    permission_module = 'properti'
    permission_sub_module = 'tipe_kamar'
    permission_action = 'create'
    model = TipeKamar
    form_class = TipeKamarForm
    template_name = 'properti/tipe_kamar_form.html'
    success_url = reverse_lazy('properti:tipe_kamar_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Tipe Kamar'
        context['is_edit'] = False
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Tipe kamar berhasil ditambahkan')
        return super().form_valid(form)


class TipeKamarUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit tipe kamar."""
    permission_module = 'properti'
    permission_sub_module = 'tipe_kamar'
    permission_action = 'write'
    model = TipeKamar
    form_class = TipeKamarForm
    template_name = 'properti/tipe_kamar_form.html'
    success_url = reverse_lazy('properti:tipe_kamar_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Tipe Kamar'
        context['is_edit'] = True
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Tipe kamar berhasil diperbarui')
        return super().form_valid(form)


class TipeKamarDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus tipe kamar - return JSON untuk AJAX."""
    permission_module = 'properti'
    permission_sub_module = 'tipe_kamar'
    permission_action = 'delete'
    model = TipeKamar
    success_url = reverse_lazy('properti:tipe_kamar_list')

    def delete(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nama = self.object.nama
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Tipe kamar {nama} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus tipe kamar "{self.object.nama}" karena masih digunakan oleh kamar yang ada. Silakan ubah tipe kamar tersebut terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
            # ║                      KAMAR CRUD                              ║
# ╚══════════════════════════════════════════════════════════════╝

class KamarListView(ReadPermissionMixin, ListView):
    permission_module = 'properti'
    permission_sub_module = 'kamar'
    paginate_by = 50
    """Daftar kamar. URL: /properti/kamar/"""
    model = Kamar
    template_name = 'properti/kamar_list.html'
    context_object_name = 'kamar_list'

    def get_queryset(self):
        qs = super().get_queryset().select_related('properti', 'tipe_kamar')
        properti_id = self.request.GET.get('properti', '').strip()
        status = self.request.GET.get('status', '').strip()
        lantai = self.request.GET.get('lantai', '').strip()
        if properti_id:
            qs = qs.filter(properti_id=properti_id)
        if status:
            qs = qs.filter(status=status)
        if lantai:
            qs = qs.filter(lantai=lantai)
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context['total_kamar'] = qs.count()
        context['kamar_tersedia'] = qs.filter(status='tersedia').count()
        context['kamar_terisi'] = qs.filter(status='terisi').count()
        context['kamar_maintenance'] = qs.filter(status='maintenance').count()
        context['properti_filter'] = Properti.objects.filter(aktif=True)
        context['selected_properti'] = self.request.GET.get('properti', '')
        # Hitung total harga bulanan untuk FOOTER_DATA export (kolom Harga/Bulan index 4)
        from django.db.models import Sum
        context['total_harga'] = qs.select_related('tipe_kamar').aggregate(
            total=Sum('tipe_kamar__harga_bulanan')
        )['total'] or 0
        return context


class KamarCreateView(CreatePermissionMixin, CreateView):
    """Tambah kamar baru."""
    permission_module = 'properti'
    permission_sub_module = 'kamar'
    permission_action = 'create'
    model = Kamar
    form_class = KamarForm
    template_name = 'properti/kamar_form.html'
    success_url = reverse_lazy('properti:kamar_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Kamar'
        context['is_edit'] = False
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Kamar berhasil ditambahkan')
        return super().form_valid(form)


class KamarUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit kamar."""
    permission_module = 'properti'
    permission_sub_module = 'kamar'
    permission_action = 'write'
    model = Kamar
    form_class = KamarForm
    template_name = 'properti/kamar_form.html'
    success_url = reverse_lazy('properti:kamar_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Kamar'
        context['is_edit'] = True
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Kamar berhasil diperbarui')
        return super().form_valid(form)


class KamarDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus kamar - return JSON untuk AJAX."""
    permission_module = 'properti'
    permission_sub_module = 'kamar'
    permission_action = 'delete'
    model = Kamar
    success_url = reverse_lazy('properti:kamar_list')

    def delete(self, request, *args, **kwargs):
        from django.db.models import ProtectedError
        self.object = self.get_object()
        try:
            nomor = self.object.nomor_kamar
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Kamar {nomor} berhasil dihapus'})
        except ProtectedError:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus kamar "{self.object.nomor_kamar}" karena masih memiliki kontrak sewa aktif. Silakan hapus atau akhiri kontrak terkait terlebih dahulu.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
                        # ║                   DENAH API VIEWS                            ║
# ╚══════════════════════════════════════════════════════════════╝

@login_required
def denah_update_position(request, pk):
    """API: Update posisi kamar di denah (drag-and-drop)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        kamar = Kamar.objects.get(pk=pk)
        kamar.pos_x = int(data.get('pos_x', kamar.pos_x))
        kamar.pos_y = int(data.get('pos_y', kamar.pos_y))
        if 'width' in data:
            kamar.width = int(data['width'])
        if 'height' in data:
            kamar.height = int(data['height'])
        kamar.save()
        return JsonResponse({'success': True, 'message': f'Posisi kamar {kamar.nomor_kamar} disimpan'})
    except Kamar.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Kamar tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def denah_create_kamar(request, properti_pk):
    """API: Buat kamar baru dari denah."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        properti = Properti.objects.get(pk=properti_pk)
        kamar = Kamar.objects.create(
            properti=properti,
            nomor_kamar=data['nomor_kamar'],
            lantai=int(data.get('lantai', 1)),
            tipe_kamar_id=data.get('tipe_kamar') or None,
            status=data.get('status', 'tersedia'),
            pos_x=int(data.get('pos_x', 20)),
            pos_y=int(data.get('pos_y', 20)),
            width=int(data.get('width', 120)),
            height=int(data.get('height', 100)),
            fasilitas_tambahan=data.get('fasilitas_tambahan', ''),
            catatan=data.get('catatan', ''),
        )
        return JsonResponse({
            'success': True,
            'message': f'Kamar {kamar.nomor_kamar} berhasil dibuat',
            'kamar': {
                'id': kamar.pk, 'nomor_kamar': kamar.nomor_kamar, 'lantai': kamar.lantai,
                'tipe_kamar': kamar.tipe_kamar.nama if kamar.tipe_kamar else '-',
                'status': kamar.status, 'harga': float(kamar.harga),
                'pos_x': kamar.pos_x, 'pos_y': kamar.pos_y,
                'width': kamar.width, 'height': kamar.height,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def denah_edit_kamar(request, pk):
    """API: Edit data kamar dari denah."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        kamar = Kamar.objects.get(pk=pk)
        for field in ['nomor_kamar', 'status', 'fasilitas_tambahan', 'catatan']:
            if field in data:
                setattr(kamar, field, data[field])
        if 'lantai' in data:
            kamar.lantai = int(data['lantai'])
        if 'tipe_kamar' in data:
            kamar.tipe_kamar_id = data['tipe_kamar'] or None
        kamar.save()
        return JsonResponse({
            'success': True,
            'message': f'Kamar {kamar.nomor_kamar} berhasil diupdate',
            'kamar': {
                'id': kamar.pk, 'nomor_kamar': kamar.nomor_kamar, 'lantai': kamar.lantai,
                'tipe_kamar': kamar.tipe_kamar.nama if kamar.tipe_kamar else '-',
                'status': kamar.status, 'harga': float(kamar.harga),
            }
        })
    except Kamar.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Kamar tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def denah_delete_kamar(request, pk):
    """API: Hapus kamar dari denah."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    try:
        kamar = Kamar.objects.get(pk=pk)
        nomor = kamar.nomor_kamar
        kamar.delete()
        return JsonResponse({'success': True, 'message': f'Kamar {nomor} berhasil dihapus'})
    except Kamar.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Kamar tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

