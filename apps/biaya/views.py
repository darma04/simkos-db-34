"""
==========================================================================
BIAYA VIEWS - View CRUD untuk Kategori Biaya & Transaksi Biaya
==========================================================================
File ini berisi views untuk modul Biaya (Expense):

KATEGORI BIAYA CRUD:
    KategoriBiayaListView   → Daftar kategori biaya
    KategoriBiayaCreateView → Tambah kategori baru
    KategoriBiayaUpdateView → Edit kategori
    KategoriBiayaDeleteView → Hapus kategori (JSON)

TRANSAKSI BIAYA CRUD:
    TransaksiBiayaListView   → Daftar transaksi + total nominal
    TransaksiBiayaCreateView → Catat pengeluaran baru + notifikasi Telegram
    TransaksiBiayaDetailView → Detail transaksi + riwayat activity log
    TransaksiBiayaUpdateView → Edit transaksi
    TransaksiBiayaDeleteView → Hapus transaksi + log sebelum hapus
    TransaksiBiayaPrintView  → Cetak bukti pengeluaran

Fitur:
- Detail transaksi menampilkan riwayat activity log (audit trail)
- Notifikasi Telegram dikirim saat transaksi baru dibuat
- Activity log dicatat untuk setiap perubahan (create/update/delete)
==========================================================================
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from apps.biaya.models import KategoriBiaya, TransaksiBiaya
from apps.biaya.forms import KategoriBiayaForm, TransaksiBiayaForm
from web_project import TemplateLayout
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from django.db import transaction


# ╔══════════════════════════════════════════════════════════════╗
# ║               KATEGORI BIAYA CRUD                              ║
# ╚══════════════════════════════════════════════════════════════╝

class KategoriBiayaListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """Daftar kategori biaya. URL: /biaya/kategori/"""
    model = KategoriBiaya
    template_name = 'biaya/kategori_list.html'
    context_object_name = 'kategori_list'
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_kategori'] = self.get_queryset().count()
        return context


class KategoriBiayaCreateView(CreatePermissionMixin, CreateView):
    """Tambah kategori biaya. URL: /biaya/kategori/add/"""
    model = KategoriBiaya
    form_class = KategoriBiayaForm
    template_name = 'biaya/kategori_form.html'
    success_url = reverse_lazy('biaya:kategori')
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Kategori Biaya'
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Kategori biaya berhasil ditambahkan')
        return super().form_valid(form)


class KategoriBiayaUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit kategori biaya. URL: /biaya/kategori/<pk>/edit/"""
    model = KategoriBiaya
    form_class = KategoriBiayaForm
    template_name = 'biaya/kategori_form.html'
    success_url = reverse_lazy('biaya:kategori')
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Kategori Biaya'
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Kategori biaya berhasil diperbarui')
        return super().form_valid(form)


class KategoriBiayaDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus kategori biaya - return JSON untuk AJAX."""
    model = KategoriBiaya
    success_url = reverse_lazy('biaya:kategori')
    permission_module = 'biaya'
    permission_sub_module = 'kategori_biaya'

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        try:
            kategori_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True, 
                'message': f'Kategori biaya {kategori_name} berhasil dihapus'
            })
        except Exception as e:
            if 'protected' in str(e).lower() or 'Cannot delete' in str(e):
                return JsonResponse({
                    'success': False, 
                    'message': f'Tidak dapat menghapus kategori "{self.object.nama}" karena masih memiliki transaksi biaya yang terkait. Silakan hapus transaksi terkait terlebih dahulu.'
                })
            return JsonResponse({
                'success': False, 
                'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'
            })


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
        # ║              TRANSAKSI BIAYA CRUD                              ║
# ╚══════════════════════════════════════════════════════════════╝

class TransaksiBiayaListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Daftar transaksi biaya + summary nominal.
    URL: /biaya/transaksi/
    """
    model = TransaksiBiaya
    template_name = 'biaya/transaksi_list.html'
    context_object_name = 'transaksi_list'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from django.db.models import Sum
        queryset = self.get_queryset()
        context['total_transaksi_biaya'] = queryset.count()
        context['total_amount_biaya'] = queryset.aggregate(Sum('jumlah'))['jumlah__sum'] or 0
        return context


class TransaksiBiayaCreateView(CreatePermissionMixin, CreateView):
    """
    Catat pengeluaran biaya baru.
    URL: /biaya/transaksi/add/

    Setelah save:
    - Kirim notifikasi Telegram
    - Log activity
    """
    model = TransaksiBiaya
    form_class = TransaksiBiayaForm
    template_name = 'biaya/transaksi_form.html'
    success_url = reverse_lazy('biaya:transaksi')
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Catat Pengeluaran Biaya'
        return context


    def form_valid(self, form):

        form.instance.dibuat_oleh = self.request.user
        response = super().form_valid(form)

        # Kirim notifikasi Telegram
        try:
            from apps.automation.signals import kirim_notifikasi_biaya
            kirim_notifikasi_biaya(self.object)
        except Exception as e:
            pass

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            self.request,
            action='create',
            model_name='Transaksi Biaya',
            object_id=self.object.pk,
            object_repr=str(self.object),
            description=f'Mencatat transaksi biaya: {self.object.nomor_transaksi} - Rp {self.object.jumlah:,.0f}'
        )

        messages.success(self.request, 'Transaksi biaya berhasil dicatat')
        return response


class TransaksiBiayaDetailView(ReadPermissionMixin, TemplateView):
    """
    Detail transaksi biaya + RIWAYAT ACTIVITY LOG.
    URL: /biaya/transaksi/<pk>/

    Menampilkan audit trail: siapa melakukan apa dan kapan
    untuk transaksi biaya ini.
    """
    template_name = 'biaya/transaksi_detail.html'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from django.shortcuts import get_object_or_404
        from apps.activity_log.models import UserActivity

        transaksi_id = kwargs.get('pk')
        transaksi = get_object_or_404(TransaksiBiaya, pk=transaksi_id)
        context['transaksi'] = transaksi

        # Riwayat activity log (audit trail)
        context['activity_logs'] = UserActivity.objects.filter(
            model_name__icontains='transaksi',
            object_id=str(transaksi.pk)
        ).select_related('user').order_by('-timestamp')[:50]

        return context


class TransaksiBiayaUpdateView(UpdatePermissionMixin, UpdateView):
    """Edit transaksi biaya + log activity. URL: /biaya/transaksi/<pk>/edit/"""
    model = TransaksiBiaya
    form_class = TransaksiBiayaForm
    template_name = 'biaya/transaksi_form.html'
    success_url = reverse_lazy('biaya:transaksi')
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Transaksi Biaya'
        return context


    def form_valid(self, form):

        response = super().form_valid(form)

        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            self.request,
            action='update',
            model_name='Transaksi Biaya',
            object_id=self.object.pk,
            object_repr=str(self.object),
            description=f'Mengubah transaksi biaya: {self.object.nomor_transaksi}'
        )

        messages.success(self.request, 'Transaksi biaya berhasil diperbarui')
        return response


class TransaksiBiayaDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus transaksi biaya - log activity SEBELUM hapus, lalu return JSON.
    URL: /biaya/transaksi/<pk>/delete/
    """
    model = TransaksiBiaya
    success_url = reverse_lazy('biaya:transaksi')
    permission_module = 'biaya'

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Log activity SEBELUM hapus (agar referensi masih ada)
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='delete',
            model_name='Transaksi Biaya',
            object_id=self.object.pk,
            object_repr=str(self.object),
            description=f'Menghapus transaksi biaya: {self.object.nomor_transaksi}'
        )

        try:
            nomor_transaksi = self.object.nomor_transaksi
            self.object.delete()
            return JsonResponse({
                'success': True, 
                'message': f'Transaksi biaya {nomor_transaksi} berhasil dihapus'
            })
        except Exception as e:
            if 'protected' in str(e).lower() or 'Cannot delete' in str(e):
                return JsonResponse({
                    'success': False, 
                    'message': f'Tidak dapat menghapus transaksi "{self.object.nomor_transaksi}" karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'
                })
            return JsonResponse({
                'success': False, 
                'message': f'Terjadi kesalahan saat menghapus data. Silakan coba lagi.'
            })

    def post(self, request, *args, **kwargs):
        return self.delete(request, *args, **kwargs)


class TransaksiBiayaPrintView(ReadPermissionMixin, TemplateView):
    """
    Cetak bukti pengeluaran biaya.
    URL: /biaya/transaksi/<pk>/print/
    Menggunakan data perusahaan + template cetak 'expense'.
    """
    template_name = 'biaya/transaksi_biaya_print.html'
    permission_module = 'biaya'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = super().get_context_data(**kwargs)
        from apps.pengaturan.models import PengaturanPerusahaan, TemplateCetak
        from django.shortcuts import get_object_or_404

        transaksi = get_object_or_404(TransaksiBiaya, pk=self.kwargs['pk'])
        context['transaksi'] = transaksi
        context['perusahaan'] = PengaturanPerusahaan.load()
        context['template'] = TemplateCetak.get_template('expense')
        return context


class TransaksiBiayaApproveView(UpdatePermissionMixin, TemplateView):
    """
    Approve (Setujui) transaksi biaya — ubah status ke 'approved'.
    URL: /biaya/transaksi/<pk>/approve/
    Method: POST (via AJAX)
    """
    template_name = 'biaya/transaksi_detail.html'
    permission_module = 'biaya'

    def post(self, request, *args, **kwargs):
        """Proses approve transaksi biaya via AJAX POST."""
        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        transaksi = get_object_or_404(TransaksiBiaya, pk=kwargs['pk'])

        # Validasi: hanya status draft/submitted yang bisa di-approve
        if transaksi.status not in ['draft', 'submitted']:
            return JsonResponse({
                'success': False,
                'message': f'Transaksi dengan status "{transaksi.get_status_display()}" tidak dapat disetujui.'
            }, status=400)

        # Simpan status lama untuk log
        old_status = transaksi.get_status_display()

        # Update status ke approved
        transaksi.status = 'approved'
        transaksi.disetujui_oleh = request.user
        transaksi.save()

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Transaksi Biaya',
            object_id=transaksi.pk,
            object_repr=str(transaksi),
            description=f'Menyetujui transaksi biaya: {transaksi.nomor_transaksi} (status: {old_status} → Disetujui)'
        )

        return JsonResponse({
            'success': True,
            'message': f'Transaksi biaya {transaksi.nomor_transaksi} berhasil disetujui.'
        })


class TransaksiBiayaRejectView(UpdatePermissionMixin, TemplateView):
    """
    Reject (Tolak) transaksi biaya — ubah status ke 'rejected'.
    URL: /biaya/transaksi/<pk>/reject/
    Method: POST (via AJAX)
    """
    template_name = 'biaya/transaksi_detail.html'
    permission_module = 'biaya'

    def post(self, request, *args, **kwargs):
        """Proses reject transaksi biaya via AJAX POST."""
        from django.http import JsonResponse
        from django.shortcuts import get_object_or_404

        transaksi = get_object_or_404(TransaksiBiaya, pk=kwargs['pk'])

        # Validasi: hanya status draft/submitted yang bisa di-reject
        if transaksi.status not in ['draft', 'submitted']:
            return JsonResponse({
                'success': False,
                'message': f'Transaksi dengan status "{transaksi.get_status_display()}" tidak dapat ditolak.'
            }, status=400)

        # Simpan status lama untuk log
        old_status = transaksi.get_status_display()

        # Update status ke rejected
        transaksi.status = 'rejected'
        transaksi.save()

        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Transaksi Biaya',
            object_id=transaksi.pk,
            object_repr=str(transaksi),
            description=f'Menolak transaksi biaya: {transaksi.nomor_transaksi} (status: {old_status} → Ditolak)'
        )

        return JsonResponse({
            'success': True,
            'message': f'Transaksi biaya {transaksi.nomor_transaksi} berhasil ditolak.'
        })
