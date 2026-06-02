"""
==========================================================================
 CORE MIXINS - Mixin Permission untuk Views
==========================================================================
 File ini berisi Mixin classes yang menambahkan pengecekan hak akses
 ke View Django (Class-Based Views / CBV).

 Apa itu Mixin?
 - Mixin adalah class yang DITAMBAHKAN ke class lain via multiple inheritance
 - Menambahkan fitur tanpa mengubah class aslinya
 - Contoh: class MyView(SubModulePermissionMixin, ListView)
   → MyView mendapat fitur permission check DARI mixin
   → DAN fitur list data DARI ListView
   → Urutan penting! Mixin HARUS di KIRI agar dispatch() dipanggil duluan

 Cara kerja:
 1. View diakses user → dispatch() dipanggil
 2. Mixin menangkap dispatch() SEBELUM view asli dijalankan
 3. Mixin cek permission via has_permission()
 4. Jika diizinkan → super().dispatch() → view asli berjalan
 5. Jika ditolak → PermissionDenied (403) atau redirect ke dashboard

 Daftar Mixin:
 - SubModulePermissionMixin → Cek permission modul + sub-modul (UTAMA)
 - ModulePermissionMixin → Cek permission modul saja (sederhana)
 - ReadPermissionMixin → Cek can_view
 - CreatePermissionMixin → Cek can_create
 - UpdatePermissionMixin → Cek can_edit
 - DeletePermissionMixin → Cek can_delete
 - AdminOrSuperuserMixin → Hanya admin/superuser (legacy)
 - SuperuserRequiredMixin → Hanya superuser (legacy)

 Koneksi:
 - apps/core/permissions.py → has_permission() yang dipanggil oleh mixin
 - Semua views di proyek → Menggunakan mixin ini
 - auth/models.py → Profile.role yang dicek oleh has_permission()
==========================================================================
"""

from django.shortcuts import redirect                   # Fungsi redirect
from django.contrib import messages                      # Framework pesan flash
from django.core.exceptions import PermissionDenied      # Exception 403 Forbidden
from apps.core.permissions import has_permission         # Fungsi cek permission


class SubModulePermissionMixin:
    """
    Mixin UTAMA — Mengecek permission modul DAN sub-modul sebelum view diakses.

    Ini adalah mixin yang PALING SERING digunakan di seluruh proyek.
    Mendukung pengecekan di level sub-modul (lebih granular).

    Cara pakai:
        class KategoriListView(SubModulePermissionMixin, ListView):
            permission_module = 'produk'          # Wajib: nama modul
            permission_sub_module = 'kategori'    # Opsional: nama sub-modul
            permission_action = 'read'            # Wajib: aksi ('read'/'create'/'write'/'delete')
            permission_redirect_url = 'dashboard:index'  # Opsional: URL redirect jika ditolak

    Atribut yang harus diisi di view:
    - permission_module (str): Nama modul — WAJIB (contoh: 'produk', 'inventory')
    - permission_sub_module (str): Nama sub-modul — OPSIONAL (contoh: 'kategori', 'gudang')
    - permission_action (str): Jenis aksi — default 'read'
    - permission_redirect_url (str): URL redirect jika ditolak
    - permission_raise_403 (bool): Jika True → raise 403 Exception (bukan redirect)
    """
    permission_module = None              # Harus diisi oleh view turunan
    permission_sub_module = None          # Opsional
    permission_action = 'read'            # Default: cek akses baca
    permission_redirect_url = 'dashboard:index'  # Default: redirect ke dashboard
    permission_raise_403 = False          # Default: False (raise 403 forbidden)

    def dispatch(self, request, *args, **kwargs):
        """
        Mengecek permission SEBELUM view dijalankan.

        dispatch() adalah method pertama yang dipanggil saat view diakses.
        Ini yang memutuskan apakah view boleh dijalankan atau tidak.

        Alur:
        1. Jika superuser → langsung izinkan (bypass semua cek)
        2. Validasi: pastikan permission_module sudah diisi
        3. Panggil has_permission() dengan module + sub_module
        4. Jika True → panggil super().dispatch() (jalankan view)
        5. Jika False → raise PermissionDenied (halaman 403)
        """
        # Superuser bypass semua pengecekan
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        # Validasi: permission_module WAJIB diisi
        if not self.permission_module:
            raise ValueError(
                f"{self.__class__.__name__} must define 'permission_module' attribute"
            )

        # Cek permission dengan sub_module support
        if not has_permission(
            request.user,
            self.permission_action,
            self.permission_module,
            self.permission_sub_module    # Pass sub_module untuk pengecekan granular
        ):
            # Permission ditolak → raise 403 Forbidden
            module_name = self.permission_sub_module or self.permission_module
            raise PermissionDenied(
                f"Anda tidak memiliki akses {self.permission_action} untuk {module_name.title()}"
            )

        # Permission diizinkan → lanjutkan ke view asli
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Inject RBAC variables into context for global UI gating."""
        context = {}
        if hasattr(super(), 'get_context_data'):
            context = super().get_context_data(**kwargs)
        
        context['rbac_current_module'] = self.permission_module
        context['rbac_current_sub_module'] = self.permission_sub_module
        
        user = getattr(self.request, 'user', None)
        if user and not user.is_superuser:
            context['rbac_can_read'] = has_permission(user, 'read', self.permission_module, self.permission_sub_module)
            context['rbac_can_create'] = has_permission(user, 'create', self.permission_module, self.permission_sub_module)
            context['rbac_can_edit'] = has_permission(user, 'write', self.permission_module, self.permission_sub_module)
            context['rbac_can_delete'] = has_permission(user, 'delete', self.permission_module, self.permission_sub_module)
        else:
            context['rbac_can_read'] = context['rbac_can_create'] = context['rbac_can_edit'] = context['rbac_can_delete'] = True
            
        return context

    def post(self, request, *args, **kwargs):
        """
        Ensure POST requests explicitly call the delete() method if this is a DeleteView.
        Django 4.0+ DeletionMixin.post() uses FormMixin.form_valid() instead
        of directly calling delete(). This breaks custom AJAX delete() implementations.
        """
        # Hack to bypass form_valid for ajax delete views
        if hasattr(self, 'delete') and getattr(self, 'object', None) is None and 'delete' in request.path:
            return self.delete(request, *args, **kwargs)
        if hasattr(super(), 'post'):
            return super().post(request, *args, **kwargs)
        # Fallback if no post method
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET', 'POST'])


class ModulePermissionMixin:
    """
    Mixin sederhana — Mengecek permission di level MODUL saja (tanpa sub-modul).

    Lebih ringan dari SubModulePermissionMixin, cocok untuk view
    yang tidak perlu pengecekan sub-modul.

    Cara pakai:
        class DashboardView(ModulePermissionMixin, TemplateView):
            permission_module = 'dashboard'
            permission_action = 'read'

    Perbedaan dengan SubModulePermissionMixin:
    - ModulePermissionMixin: hanya cek modul (tanpa sub-modul)
    - Jika ditolak: redirect ke dashboard (bukan 403)
    """
    permission_module = None              # Harus diisi oleh view turunan
    permission_action = 'read'            # Default: cek akses baca
    permission_redirect_url = 'dashboard:index'
    permission_raise_403 = False

    def dispatch(self, request, *args, **kwargs):
        """Cek permission level modul sebelum view dijalankan."""
        # Superuser bypass
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        # Validasi
        if not self.permission_module:
            raise ValueError(
                f"{self.__class__.__name__} must define 'permission_module' attribute"
            )

        # Cek permission modul (tanpa sub-modul)
        if not has_permission(request.user, self.permission_action, self.permission_module):
            if self.permission_raise_403:
                raise PermissionDenied("You don't have permission to access this page.")

            # Tampilkan pesan warning dan redirect
            messages.warning(request, f"Anda tidak memiliki akses ke modul {self.permission_module.title()}")
            return redirect(self.permission_redirect_url)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Inject RBAC variables into context for global UI gating."""
        context = {}
        if hasattr(super(), 'get_context_data'):
            context = super().get_context_data(**kwargs)
        
        context['rbac_current_module'] = self.permission_module
        context['rbac_current_sub_module'] = None
        
        user = getattr(self.request, 'user', None)
        if user and not user.is_superuser:
            context['rbac_can_read'] = has_permission(user, 'read', self.permission_module)
            context['rbac_can_create'] = has_permission(user, 'create', self.permission_module)
            context['rbac_can_edit'] = has_permission(user, 'write', self.permission_module)
            context['rbac_can_delete'] = has_permission(user, 'delete', self.permission_module)
        else:
            context['rbac_can_read'] = context['rbac_can_create'] = context['rbac_can_edit'] = context['rbac_can_delete'] = True
            
        return context


# ==================== MIXIN LEGACY (Backward Compatibility) ====================
# Mixin lama yang tetap dipertahankan agar kode yang sudah ada tidak rusak

class AdminOrSuperuserMixin:
    """
    Mixin LEGACY — Membatasi akses hanya untuk admin atau superuser.
    Menggunakan is_superuser atau is_staff dari User Django bawaan.
    TIDAK menggunakan sistem RBAC baru.
    """
    def dispatch(self, request,  *args, **kwargs):
        """Dipanggil sebelum view dijalankan — cek permission."""
        if not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, 'Akses ditolak. Hanya admin yang dapat mengakses halaman ini.')
            return redirect('dashboard:index')
        return super().dispatch(request, *args, **kwargs)


class SuperuserRequiredMixin:
    """
    Mixin LEGACY — Membatasi akses hanya untuk SUPERUSER saja.
    Lebih ketat dari AdminOrSuperuserMixin (is_staff tidak cukup).
    """
    def dispatch(self, request, *args, **kwargs):
        """Dipanggil sebelum view dijalankan — cek permission."""
        if not request.user.is_superuser:
            messages.error(request, 'Akses ditolak. Hanya superuser yang dapat mengakses halaman ini.')
            return redirect('dashboard:index')
        return super().dispatch(request, *args, **kwargs)


# ==================== MIXIN CRUD SPESIFIK ====================
# Mixin khusus untuk setiap jenis aksi CRUD
# Semuanya raise PermissionDenied (403) jika ditolak — TANPA redirect

class ReadPermissionMixin:
    """
    Mixin untuk cek permission BACA (can_view) dengan support sub-modul.
    Raise PermissionDenied (403) jika user tidak punya akses baca.

    Cara pakai:
        class KategoriListView(ReadPermissionMixin, ListView):
            permission_module = 'produk'
            permission_sub_module = 'kategori'  # Opsional
    """
    permission_module = None
    permission_sub_module = None

    def dispatch(self, request, *args, **kwargs):
        """Dipanggil sebelum view dijalankan — cek permission."""
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if not self.permission_module:
            raise ValueError(f"{self.__class__.__name__} must define 'permission_module'")

        # Cek permission VIEW
        if not has_permission(request.user, 'read', self.permission_module, self.permission_sub_module):
            module_name = self.permission_sub_module or self.permission_module
            raise PermissionDenied(f'Anda tidak memiliki akses untuk melihat {module_name.title()}')

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Inject RBAC variables into context for global UI gating."""
        context = {}
        if hasattr(super(), 'get_context_data'):
            context = super().get_context_data(**kwargs)
        
        context['rbac_current_module'] = self.permission_module
        context['rbac_current_sub_module'] = self.permission_sub_module
        
        user = getattr(self.request, 'user', None)
        if user and not user.is_superuser:
            context['rbac_can_read'] = has_permission(user, 'read', self.permission_module, self.permission_sub_module)
            context['rbac_can_create'] = has_permission(user, 'create', self.permission_module, self.permission_sub_module)
            context['rbac_can_edit'] = has_permission(user, 'write', self.permission_module, self.permission_sub_module)
            context['rbac_can_delete'] = has_permission(user, 'delete', self.permission_module, self.permission_sub_module)
            context['is_readonly_mode'] = not context['rbac_can_edit']
        else:
            context['rbac_can_read'] = context['rbac_can_create'] = context['rbac_can_edit'] = context['rbac_can_delete'] = True
            context['is_readonly_mode'] = False
            
        return context


class CreatePermissionMixin:
    """
    Mixin untuk cek permission TAMBAH (can_create) dengan support sub-modul.
    Raise PermissionDenied (403) jika user tidak punya akses tambah.
    """
    permission_module = None
    permission_sub_module = None

    def dispatch(self, request, *args, **kwargs):
        """Dipanggil sebelum view dijalankan — cek permission."""
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if not self.permission_module:
            raise ValueError(f"{self.__class__.__name__} must define 'permission_module'")

        # Cek permission CREATE
        if not has_permission(request.user, 'create', self.permission_module, self.permission_sub_module):
            module_name = self.permission_sub_module or self.permission_module
            raise PermissionDenied(f'Anda tidak memiliki akses untuk menambah data di {module_name.title()}')

        return super().dispatch(request, *args, **kwargs)


class UpdatePermissionMixin:
    """
    Mixin untuk cek permission EDIT (can_edit) dengan support sub-modul.
    Raise PermissionDenied (403) jika user tidak punya akses edit.
    """
    permission_module = None
    permission_sub_module = None

    def dispatch(self, request, *args, **kwargs):
        """Dipanggil sebelum view dijalankan — cek permission."""
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if not self.permission_module:
            raise ValueError(f"{self.__class__.__name__} must define 'permission_module'")

        # Cek permission EDIT (action='write' = alias untuk 'update')
        if not has_permission(request.user, 'write', self.permission_module, self.permission_sub_module):
            module_name = self.permission_sub_module or self.permission_module
            raise PermissionDenied(f'Anda tidak memiliki akses untuk mengubah data di {module_name.title()}')

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Inject RBAC variables into context for global UI gating."""
        context = {}
        if hasattr(super(), 'get_context_data'):
            context = super().get_context_data(**kwargs)
        
        context['rbac_current_module'] = self.permission_module
        context['rbac_current_sub_module'] = self.permission_sub_module
        
        user = getattr(self.request, 'user', None)
        if user and not user.is_superuser:
            context['rbac_can_read'] = has_permission(user, 'read', self.permission_module, self.permission_sub_module)
            context['rbac_can_create'] = has_permission(user, 'create', self.permission_module, self.permission_sub_module)
            context['rbac_can_edit'] = has_permission(user, 'write', self.permission_module, self.permission_sub_module)
            context['rbac_can_delete'] = has_permission(user, 'delete', self.permission_module, self.permission_sub_module)
            context['is_readonly_mode'] = not context['rbac_can_edit']
        else:
            context['rbac_can_read'] = context['rbac_can_create'] = context['rbac_can_edit'] = context['rbac_can_delete'] = True
            context['is_readonly_mode'] = False
            
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            if not has_permission(request.user, 'write', self.permission_module, self.permission_sub_module):
                module_name = self.permission_sub_module or self.permission_module
                raise PermissionDenied(f'Anda tidak memiliki akses untuk mengubah data di {module_name.title()}')
        if hasattr(super(), 'post'):
            return super().post(request, *args, **kwargs)
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET', 'POST'])


class DeletePermissionMixin:
    """
    Mixin untuk cek permission HAPUS (can_delete) dengan support sub-modul.
    Raise PermissionDenied (403) jika user tidak punya akses hapus.
    """
    permission_module = None
    permission_sub_module = None

    def dispatch(self, request, *args, **kwargs):
        """Dipanggil sebelum view dijalankan — cek permission."""
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        if not self.permission_module:
            raise ValueError(f"{self.__class__.__name__} must define 'permission_module'")

        # Cek permission DELETE
        if not has_permission(request.user, 'delete', self.permission_module, self.permission_sub_module):
            module_name = self.permission_sub_module or self.permission_module
            raise PermissionDenied(f'Anda tidak memiliki akses untuk menghapus data di {module_name.title()}')

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """Inject RBAC variables into context for global UI gating."""
        context = {}
        if hasattr(super(), 'get_context_data'):
            context = super().get_context_data(**kwargs)
        
        context['rbac_current_module'] = self.permission_module
        context['rbac_current_sub_module'] = self.permission_sub_module
        
        user = getattr(self.request, 'user', None)
        if user and not user.is_superuser:
            context['rbac_can_read'] = has_permission(user, 'read', self.permission_module, self.permission_sub_module)
            context['rbac_can_create'] = has_permission(user, 'create', self.permission_module, self.permission_sub_module)
            context['rbac_can_edit'] = has_permission(user, 'write', self.permission_module, self.permission_sub_module)
            context['rbac_can_delete'] = has_permission(user, 'delete', self.permission_module, self.permission_sub_module)
            context['is_readonly_mode'] = not context['rbac_can_edit']
        else:
            context['rbac_can_read'] = context['rbac_can_create'] = context['rbac_can_edit'] = context['rbac_can_delete'] = True
            context['is_readonly_mode'] = False
            
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            if not has_permission(request.user, 'delete', self.permission_module, self.permission_sub_module):
                module_name = self.permission_sub_module or self.permission_module
                raise PermissionDenied(f'Anda tidak memiliki akses untuk menghapus data di {module_name.title()}')
        if hasattr(super(), 'post'):
            return super().post(request, *args, **kwargs)
        if hasattr(self, 'delete'):
            return self.delete(request, *args, **kwargs)
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET', 'POST'])
