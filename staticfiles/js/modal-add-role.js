/**
 * Modal Add Role - Handle new role creation with permissions
 * Uses event delegation for reliable checkbox and form handling
 */

(function() {
    'use strict';

    // Use event delegation on document for reliable event handling
    document.addEventListener('DOMContentLoaded', function() {
        // Event delegation for Select All checkbox
        document.addEventListener('change', function(e) {
            if (e.target && e.target.id === 'selectAll') {
                handleSelectAllChange(e.target);
            }
            // Update Select All state when individual checkboxes change
            if (e.target && e.target.classList.contains('permission-checkbox')) {
                updateSelectAllState();
            }
        });

        // Event delegation for form submission
        document.addEventListener('submit', function(e) {
            if (e.target && e.target.id === 'addRoleForm') {
                e.preventDefault();
                handleAddRoleSubmission(e.target);
            }
        });

        // Reset form when modal is hidden
        const addRoleModal = document.getElementById('addRoleModal');
        if (addRoleModal) {
            addRoleModal.addEventListener('hidden.bs.modal', function() {
                const form = document.getElementById('addRoleForm');
                if (form) {
                    form.reset();
                    const selectAll = document.getElementById('selectAll');
                    if (selectAll) selectAll.checked = false;
                }
            });
        }
    });

    /**
     * Handle Select All checkbox change
     */
    function handleSelectAllChange(selectAllCheckbox) {
        const isChecked = selectAllCheckbox.checked;
        const form = document.getElementById('addRoleForm');
        if (!form) return;
        
        const checkboxes = form.querySelectorAll('.permission-checkbox');
        checkboxes.forEach(function(checkbox) {
            checkbox.checked = isChecked;
        });
    }

    /**
     * Update select all checkbox state based on individual checkboxes
     */
    function updateSelectAllState() {
        const selectAllCheckbox = document.getElementById('selectAll');
        if (!selectAllCheckbox) return;

        const allCheckboxes = document.querySelectorAll('#addRoleForm .permission-checkbox');
        const checkedCheckboxes = document.querySelectorAll('#addRoleForm .permission-checkbox:checked');

        if (allCheckboxes.length === 0) return;

        selectAllCheckbox.checked = allCheckboxes.length === checkedCheckboxes.length;
        selectAllCheckbox.indeterminate = checkedCheckboxes.length > 0 && checkedCheckboxes.length < allCheckboxes.length;
    }

    /**
     * Handle add role form submission via AJAX
     */
    function handleAddRoleSubmission(form) {
        const roleNameInput = document.getElementById('role_name');
        const roleName = roleNameInput ? roleNameInput.value.trim() : '';
        const submitBtn = form.querySelector('button[type="submit"]');
        
        if (!roleName) {
            showToast('error', 'Nama role harus diisi!');
            return;
        }

        if (!submitBtn) return;
        
        const originalBtnText = submitBtn.innerHTML;

        // Show loading state
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Menyimpan...';

        // Get CSRF token
        const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
        const csrfToken = csrfInput ? csrfInput.value : '';

        // Build form data as URLSearchParams for proper encoding
        const data = new URLSearchParams();
        data.append('role_name', roleName); // Changed from modalRoleName to role_name
        data.append('csrfmiddlewaretoken', csrfToken);

        // Get all checked permission checkboxes (module-level and sub-module-level)
        const moduleCheckboxes = form.querySelectorAll('.module-perm:checked');
        moduleCheckboxes.forEach(function(checkbox) {
            // Checkbox name format: perms[module][action]
            if (checkbox.name) {
                data.append(checkbox.name, 'on');
            }
        });
        
        const subCheckboxes = form.querySelectorAll('.sub-perm:checked');
        subCheckboxes.forEach(function(checkbox) {
            // Checkbox name format: perms[module][subs][sub_code][action]
            if (checkbox.name) {
                data.append(checkbox.name, 'on');
            }
        });

        // Send AJAX POST request
        fetch('/access/roles/ajax/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': csrfToken,
            },
            body: data.toString()
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(responseData) {
            if (responseData.success) {
                // Show success message
                showToast('success', responseData.message || 'Role berhasil ditambahkan!');

                // Close modal
                var modalEl = document.getElementById('addRoleModal');
                var modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();

                // Reload page to show new role
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            } else {
                showToast('error', responseData.message || 'Gagal menambahkan role!');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        })
        .catch(function(error) {
            console.error('Error:', error);
            showToast('error', 'Terjadi kesalahan pada server!');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        });
    }

    /**
     * Show toast notification using SweetAlert2
     */
    function showToast(type, message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: type === 'success' ? 'success' : 'error',
                title: type === 'success' ? 'Sukses!' : 'Error!',
                text: message,
                timer: 3000,
                showConfirmButton: false,
                toast: true,
                position: 'top-end'
            });
        } else {
            alert(message);
        }
    }

})();
