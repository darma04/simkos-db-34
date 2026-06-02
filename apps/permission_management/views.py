"""
==========================================================================
PERMISSION MANAGEMENT VIEWS - CRUD Permission per Role
==========================================================================
File ini menangani seluruh operasi CRUD untuk manajemen permission:

Page Views (dengan template):
- PermissionListView        → Daftar semua permission (DataTables)
- RolePermissionCreateView  → Form tambah permission baru
- RolePermissionUpdateView  → Form edit permission
- RolePermissionDeleteView  → Hapus permission (AJAX JSON response)

AJAX Views (tanpa template, return JSON):
- PermissionCreateAjaxView  → Buat permission via modal popup
- PermissionUpdateAjaxView  → Update permission via modal popup
- PermissionDataAjaxView    → Ambil data permission untuk edit modal

Semua view dilindungi:
- @login_required → Wajib login
- SuperuserRequiredMixin → Hanya superuser yang boleh akses

Terhubung dengan:
- apps/core/models.py → Model RolePermission
- apps/core/mixins.py → SuperuserRequiredMixin
- permission_management/urls.py → Routing URL
- templates/permission_management/ → Template HTML
==========================================================================
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.utils.decorators import method_decorator
from django.views import View
from web_project import TemplateLayout
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from apps.core.models import RolePermission
from apps.core.mixins import (
    ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin, SuperuserRequiredMixin
)
from django.db import transaction

@method_decorator(login_required, name='dispatch')
class PermissionListView(ReadPermissionMixin, ListView):
    permission_module = 'access_control'
    permission_sub_module = 'role'
    paginate_by = 50
    """
    View untuk menampilkan DAFTAR SEMUA PERMISSION di sistem.

    Menampilkan tabel permission yang bisa difilter/search via DataTables.
    Hanya SUPERUSER yang bisa mengakses halaman ini.

    Data yang ditampilkan: role, module, can_view/create/edit/delete
    Template: permission_management/permission_list.html
    URL: /access/permissions/ (namespace: permission_management:list)
    """
    model = RolePermission
    template_name = 'permission_management/permission_list.html'
    context_object_name = 'permissions'
    ordering = ['role', 'module']
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Permissions Management'
        context['role_choices'] = RolePermission.get_all_roles()
        context['module_choices'] = RolePermission.MODULE_CHOICES
        context['user_role'] = getattr(self.request.user.profile, 'role', None) if hasattr(self.request.user, 'profile') else None
        
        return context


@method_decorator(login_required, name='dispatch')
class RolePermissionCreateView(CreatePermissionMixin, CreateView):
    """
    View untuk MENAMBAHKAN PERMISSION BARU (role + module).

    Form: role, module, can_view/create/edit/delete, deskripsi.
    Hanya SUPERUSER yang bisa menambah permission.

    Template: permission_management/role_permission_form.html
    URL: /access/permissions/add/ (namespace: permission_management:create)
    """
    model = RolePermission
    template_name = 'permission_management/role_permission_form.html'
    fields = ['role', 'module', 'can_view', 'can_create', 'can_edit', 'can_delete', 'description']
    success_url = reverse_lazy('permission_management:list')
    permission_module = 'access_control'
    permission_sub_module = 'role'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Permission Baru'
        context['is_edit'] = False
        context['role_choices'] = RolePermission.ROLE_CHOICES
        context['user_role'] = getattr(self.request.user.profile, 'role', None) if hasattr(self.request.user, 'profile') else None
        return context
    
    
    def form_valid(self, form):


        messages.success(self.request, f'Permission untuk {form.instance.get_role_display()} - {form.instance.get_module_display()} berhasil ditambahkan!')
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class RolePermissionUpdateView(UpdatePermissionMixin, UpdateView):
    """
    View untuk MENGEDIT PERMISSION yang sudah ada.

    Hanya field permission flags (can_view/create/edit/delete) dan
    deskripsi yang bisa diubah - role dan module tidak bisa diubah.

    Template: permission_management/role_permission_form.html (shared)
    URL: /access/permissions/<pk>/edit/ (namespace: permission_management:update)
    """
    model = RolePermission
    template_name = 'permission_management/role_permission_form.html'
    fields = ['can_view', 'can_create', 'can_edit', 'can_delete', 'description']
    success_url = reverse_lazy('permission_management:list')
    pk_url_kwarg = 'pk'
    permission_module = 'access_control'
    permission_sub_module = 'role'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = f'Edit Permission: {self.object}'
        context['is_edit'] = True
        context['current_role'] = self.object.role
        context['user_role'] = getattr(self.request.user.profile, 'role', None) if hasattr(self.request.user, 'profile') else None
        return context


    def form_valid(self, form):


        messages.success(self.request, f'Permission untuk {form.instance} berhasil diupdate!')
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class RolePermissionDeleteView(DeletePermissionMixin, DeleteView):
    """
    View untuk MENGHAPUS PERMISSION.

    Menggunakan AJAX delete - return JsonResponse (bukan redirect).
    Frontend menampilkan konfirmasi via SweetAlert sebelum menghapus.
    Hanya SUPERUSER yang bisa menghapus permission.

    URL: /access/permissions/<pk>/delete/ (namespace: permission_management:delete)
    Return: JsonResponse (success/fail)
    """
    model = RolePermission
    success_url = reverse_lazy('permission_management:list')
    pk_url_kwarg = 'pk'
    permission_module = 'access_control'
    permission_sub_module = 'role'


    def post(self, request, *args, **kwargs):


            return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        permission = self.get_object()
        perm_name = str(permission)

        try:
            permission.delete()
            return JsonResponse({
                'success': True,
                'message': f'Permission {perm_name} berhasil dihapus'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Gagal menghapus permission: {str(e)}'
            }, status=400)



    # ==================== AJAX Views untuk Operasi Modal ====================
    # View-view ini TIDAK mengembalikan halaman HTML, melainkan JSON data.
    # Dipanggil via JavaScript AJAX dari frontend.

@method_decorator(login_required, name='dispatch')
class PermissionCreateAjaxView(CreatePermissionMixin, View):
    permission_module = 'access_control'
    permission_sub_module = 'role'
    """
    AJAX endpoint untuk MEMBUAT PERMISSION BARU via modal popup.

    Dipanggil via JavaScript dari modal form di halaman permission list.
    Mengecek duplikasi (role+module) sebelum membuat record baru.

    URL: /access/permissions/ajax/create/ (POST only)
    Return: JsonResponse dengan success status dan ID permission baru
    """


    def post(self, request):


                try:
                    role = request.POST.get('role')
                    module = request.POST.get('module')

                    # Cek apakah permission sudah ada
                    if RolePermission.objects.filter(role=role, module=module).exists():
                        return JsonResponse({
                            'success': False,
                            'message': f'Permission untuk role {role} pada module {module} sudah ada'
                        }, status=400)

                    # Buat permission baru
                    permission = RolePermission.objects.create(
                        role=role,
                        module=module,
                        can_view=request.POST.get('can_view') == 'on',
                        can_create=request.POST.get('can_create') == 'on',
                        can_edit=request.POST.get('can_edit') == 'on',
                        can_delete=request.POST.get('can_delete') == 'on',
                        description=request.POST.get('description', '')
                    )

                    return JsonResponse({
                        'success': True,
                        'message': f'Permission {permission} berhasil ditambahkan',
                        'permission_id': permission.pk
                    })

                except Exception as e:
                    return JsonResponse({
                        'success': False,
                        'message': f'Error: {str(e)}'
                    }, status=500)


@method_decorator(login_required, name='dispatch')
class PermissionUpdateAjaxView(UpdatePermissionMixin, View):
    permission_module = 'access_control'
    permission_sub_module = 'role'
    """
    AJAX endpoint untuk MENGUPDATE PERMISSION via modal popup.

    Dipanggil via JavaScript dari modal edit di halaman permission list.
    Update field: can_view, can_create, can_edit, can_delete, description.

    URL: /access/permissions/ajax/<pk>/update/ (POST only)
    Return: JsonResponse dengan success status
    """

    def post(self, request, pk):
        """Handle HTTP POST request."""
        try:
            permission = RolePermission.objects.get(pk=pk)

            # Update field permission
            permission.can_view = request.POST.get('can_view') == 'on'
            permission.can_create = request.POST.get('can_create') == 'on'
            permission.can_edit = request.POST.get('can_edit') == 'on'
            permission.can_delete = request.POST.get('can_delete') == 'on'
            permission.description = request.POST.get('description', '')
            permission.save()

            return JsonResponse({
                'success': True,
                'message': f'Permission {permission} berhasil diupdate'
            })

        except RolePermission.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Permission tidak ditemukan'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=500)


# ==================== AJAX Views untuk Operasi Modal ====================
# View-view ini TIDAK mengembalikan halaman HTML, melainkan JSON data.
# Dipanggil via JavaScript AJAX dari frontend.

@method_decorator(login_required, name='dispatch')
class PermissionDataAjaxView(ReadPermissionMixin, View):
    permission_module = 'access_control'
    permission_sub_module = 'role'
    """
    AJAX endpoint untuk MENGAMBIL DATA PERMISSION (untuk mengisi modal edit).

    Dipanggil via JavaScript saat user klik tombol "Edit" di tabel.
    Return JSON berisi semua field permission termasuk display names.

    URL: /access/permissions/ajax/<pk>/data/ (GET only)
    Return: JsonResponse dengan data permission lengkap
    """

    def get(self, request, pk):
        """Handle HTTP GET request."""
        try:
            permission = RolePermission.objects.get(pk=pk)

            return JsonResponse({
                'success': True,
                'permission': {
                    'id': permission.pk,
                    'role': permission.role,
                    'role_display': permission.get_role_display(),
                    'module': permission.module,
                    'module_display': permission.get_module_display(),
                    'can_view': permission.can_view,
                    'can_create': permission.can_create,
                    'can_edit': permission.can_edit,
                    'can_delete': permission.can_delete,
                    'description': permission.description or ''
                }
            })

        except RolePermission.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Permission tidak ditemukan'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
            'message': f'Error: {str(e)}'
    }, status=500)
