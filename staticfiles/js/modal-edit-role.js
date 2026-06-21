/**
 * Modal Edit Role — Handler tunggal untuk edit role modal
 * Mengelola: load data, render checkboxes, populate permissions, submit form
 * v2.0 — Optimized: no double render, loading state, guard against re-render
 */

(function() {
    'use strict';

    // Guard: track apakah checkbox sudah di-render untuk mencegah double render
    let checkboxesRendered = false;
    let currentRoleCode = null;

    document.addEventListener('DOMContentLoaded', function() {
        const modal = document.getElementById('editRoleModal');
        const form = document.getElementById('editRoleForm');

        if (!modal || !form) return;

        // Listen for modal show — load data dan render checkboxes
        modal.addEventListener('show.bs.modal', function(event) {
            var button = event.relatedTarget;
            
            if (button) {
                var roleCode = button.getAttribute('data-role-code');
                if (roleCode) {
                    console.log('[EditRole] Loading data for role:', roleCode);
                    loadRoleDataForEdit(roleCode);
                }
            }
        });
        
        // Reset state saat modal ditutup
        modal.addEventListener('hidden.bs.modal', function() {
            currentRoleCode = null;
            // Jangan reset checkboxesRendered — re-use DOM yang sudah ada
        });

        // Handle form submission
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            submitEditRole(form);
        });
    });

    /**
     * Load role data dan render checkboxes di modal edit
     */
    function loadRoleDataForEdit(roleCode) {
        const roleCodeInput = document.getElementById('editRoleCode');
        const roleNameInput = document.getElementById('editRoleName');
        const container = document.getElementById('editPermissionCheckboxContainer');

        if (!roleCodeInput) return;

        // Set role code di hidden input
        roleCodeInput.value = roleCode;
        currentRoleCode = roleCode;

        // Cek apakah checkbox sudah pernah di-render
        const alreadyRendered = container && container.querySelectorAll('input[type="checkbox"]').length > 0;

        if (!alreadyRendered && container) {
            // Pertama kali: tampilkan loading
            container.innerHTML = '<div class="text-center py-4"><span class="spinner-border spinner-border-sm me-2"></span>Memuat permissions...</div>';
        } else if (alreadyRendered) {
            // Sudah ada: uncheck semua dulu
            container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
        }

        // Fetch data role dari server
        fetch(`/access/roles/ajax/${roleCode}/data/`)
            .then(response => response.json())
            .then(data => {
                console.log('[EditRole] Data loaded:', data);

                if (data.success) {
                    // Set nama role
                    if (roleNameInput) {
                        roleNameInput.value = data.role_display || roleCode.replace(/_/g, ' ');
                    }

                    // Render checkbox hanya jika belum ada
                    if (!alreadyRendered && typeof renderPermissionCheckboxes === 'function') {
                        renderPermissionCheckboxes('editPermissionCheckboxContainer', 'edit');
                    }

                    // Populate checkboxes setelah render selesai
                    requestAnimationFrame(function() {
                        populatePermissionCheckboxes(data.permissions || []);
                    });
                } else {
                    showAlert('error', data.message || 'Gagal memuat data role');
                    if (container) {
                        container.innerHTML = '<div class="alert alert-danger">Gagal memuat data permission</div>';
                    }
                }
            })
            .catch(error => {
                console.error('[EditRole] Error loading role data:', error);
                showAlert('error', 'Gagal memuat data role dari server');
                if (container) {
                    container.innerHTML = '<div class="alert alert-danger">Gagal memuat data permission</div>';
                }
            });
    }

    /**
     * Populate checkbox berdasarkan data permission dari server
     */
    function populatePermissionCheckboxes(permissions) {
        if (!Array.isArray(permissions)) return;

        // Uncheck semua checkbox terlebih dahulu
        document.querySelectorAll('#editRoleForm input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });

        permissions.forEach(perm => {
            const module = perm.module;
            const subModule = perm.sub_module;

            if (subModule) {
                // Sub-module: hanya punya 1 checkbox "Tampilkan" (view)
                const cb = document.getElementById(`edit_${module}_${subModule}_view`);
                if (cb && perm.can_view) {
                    cb.checked = true;
                }
            } else {
                // Module-level: punya 4 checkbox CRUD
                const idPrefix = `edit_${module}_`;
                const actions = ['view', 'create', 'edit', 'delete'];
                actions.forEach(action => {
                    const fieldName = action === 'view' ? 'can_view' : 
                                      action === 'create' ? 'can_create' :
                                      action === 'edit' ? 'can_edit' : 'can_delete';
                    if (perm[fieldName]) {
                        const cb = document.getElementById(`${idPrefix}${action}`);
                        if (cb) {
                            cb.checked = true;
                        }
                    }
                });
            }
        });

        console.log(`[EditRole] Populated ${permissions.length} permission records`);
    }

    /**
     * Submit edit role form via AJAX
     */
    function submitEditRole(form) {
        const formData = new FormData(form);
        const roleCode = document.getElementById('editRoleCode').value;
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;

        // Loading state
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Menyimpan...';

        // CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        fetch(`/access/roles/ajax/${roleCode}/update/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('success', data.message || 'Permissions berhasil diupdate!');

                // Tutup modal
                const modalEl = document.getElementById('editRoleModal');
                const modalInstance = bootstrap.Modal.getInstance(modalEl);
                if (modalInstance) modalInstance.hide();

                // Reload halaman setelah delay untuk menampilkan notifikasi
                setTimeout(() => location.reload(), 1500);
            } else {
                showAlert('error', data.message || 'Gagal mengupdate permissions');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        })
        .catch(error => {
            console.error('[EditRole] Error saving role:', error);
            showAlert('error', 'Terjadi kesalahan saat menyimpan. Coba lagi.');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        });
    }

    /**
     * Tampilkan notifikasi — SweetAlert2 atau fallback alert
     */
    function showAlert(type, message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: type === 'success' ? 'success' : 'error',
                title: type === 'success' ? 'Berhasil!' : 'Error!',
                text: message,
                timer: type === 'success' ? 2000 : undefined,
                showConfirmButton: type !== 'success'
            });
        } else {
            alert(message);
        }
    }

})();
