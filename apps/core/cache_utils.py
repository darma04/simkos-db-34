"""
==========================================================================
 CORE CACHE UTILS - Utilitas Cache untuk Sistem Permission
==========================================================================
 File ini berisi utilitas caching untuk meningkatkan performa
 pengecekan permission.

 Apa itu Caching?
 - Menyimpan hasil query database di memori (RAM)
 - Request berikutnya mengambil dari CACHE (cepat), bukan dari DATABASE (lambat)
 - Contoh: has_permission() dipanggil 50x per request (setiap submenu di sidebar)
   → Tanpa cache: 50 query database
   → Dengan cache: 1 query + 49 cache hit

 Konsep:
 - Cache Key: Identitas unik data yang di-cache (contoh: 'user_perms_1_has_permission_read-produk')
 - Cache Timeout: Berapa lama data disimpan di cache (default: 5 menit)
 - Cache Invalidation: Menghapus cache saat data berubah

 Kapan cache HARUS di-invalidate?
 - Saat role user diubah
 - Saat permission role diupdate
 - Saat user dipindahkan ke role lain

 Koneksi:
 - django.core.cache → Backend cache (default: LocMemCache di settings.py)
 - apps/core/permissions.py → _get_role_permissions_cache() menggunakan get_role_permissions_cache_key()
 - auth/models.py → Profile (untuk mendapatkan user_id per role)
==========================================================================
"""

# Import dari framework Django
from django.core.cache import cache  # Framework cache bawaan Django
from functools import wraps          # Untuk decorator yang mempertahankan metadata


def normalize_role_code(role_code):
    """Normalisasi kode role agar cache key konsisten lintas UI, mixin, dan gating."""
    return str(role_code or '').strip().upper()


def get_user_permissions_cache_version(user_id):
    """Ambil versi cache permission user untuk membuat cache key yang bisa di-invalidasi."""
    return cache.get(f'user_perms_version_{user_id}', 1)


def bump_user_permissions_cache_version(user_id):
    """Naikkan versi cache permission user tanpa perlu delete by pattern."""
    cache_version_key = f'user_perms_version_{user_id}'
    current_version = cache.get(cache_version_key, 1)
    cache.set(cache_version_key, current_version + 1, None)


def get_role_permissions_cache_version(role_code):
    """Ambil versi cache permission role."""
    role = normalize_role_code(role_code)
    return cache.get(f'role_perms_version_{role}', 1)


def bump_role_permissions_cache_version(role_code):
    """Naikkan versi cache permission role agar permission/menu gating langsung refresh."""
    role = normalize_role_code(role_code)
    cache_version_key = f'role_perms_version_{role}'
    current_version = cache.get(cache_version_key, 1)
    cache.set(cache_version_key, current_version + 1, None)


def get_role_permissions_cache_key(role_code):
    """Cache key utama RolePermission yang dipakai has_permission dan sidebar gating."""
    role = normalize_role_code(role_code)
    version = get_role_permissions_cache_version(role)
    return f'role_perms_{role}_v{version}'


def cache_user_permissions(timeout=300):  # 300 detik = 5 menit
    """
    Decorator untuk meng-cache hasil pengecekan permission per user.
    Mengurangi jumlah query database secara SIGNIFIKAN.

    Parameter:
    - timeout: Berapa lama cache valid dalam detik (default: 300 = 5 menit)

    Cara pakai:
        @cache_user_permissions()
        # Fungsi get_user_permissions
        def get_user_permissions(user):
            # Query database yang mahal
            ...

    Cara kerja:
    1. Buat cache key unik berdasarkan: user ID + versi + nama fungsi + arguments
    2. Cek apakah hasil sudah ada di cache
    3. Jika ada (cache hit) → kembalikan langsung (tanpa query DB)
    4. Jika tidak ada (cache miss) → jalankan fungsi, simpan hasilnya di cache
    """
    def decorator(func):
        """Fungsi decorator — membungkus view function."""
        @wraps(func)  # Mempertahankan __name__ dan __doc__ dari fungsi asli
        def wrapper(user, *args, **kwargs):
            """Fungsi wrapper — logika pengecekan sebelum view dijalankan."""
            # User yang belum login → jangan cache
            if not user or not user.is_authenticated:
                return func(user, *args, **kwargs)

            # Buat cache key unik dengan versioning
            # Format: 'user_perms_{user_id}_v{version}_{nama_fungsi}_{arg1-arg2-...}'
            # Contoh: 'user_perms_1_v3_has_permission_read-produk-kategori'
            version = get_user_permissions_cache_version(user.id)
            cache_key = f'user_perms_{user.id}_v{version}_{func.__name__}_{"-".join(map(str, args))}'

            # Cek cache
            result = cache.get(cache_key)
            if result is not None:
                # Cache HIT → kembalikan langsung tanpa query
                return result

            # Cache MISS → jalankan fungsi dan simpan hasilnya
            result = func(user, *args, **kwargs)
            cache.set(cache_key, result, timeout)
            return result

        return wrapper
    return decorator


def invalidate_user_permissions_cache(user_id):
    """
    Menghapus semua cache permission untuk user tertentu.
    Harus dipanggil saat:
    - Role user diubah
    - User dipindahkan ke role lain

    Cara kerja:
    - Menggunakan pendekatan "version number"
    - Setiap user punya nomor versi cache
    - Saat di-invalidate → versi naik → cache key lama tidak valid lagi

    Kenapa tidak hapus langsung?
    - Django cache (LocMemCache) tidak mendukung penghapusan berdasarkan pattern
    - Contoh: tidak bisa hapus semua key yang dimulai dengan 'user_perms_1_*'
    - Jadi kita gunakan version number sebagai workaround
    """
    if user_id:
        bump_user_permissions_cache_version(user_id)


def invalidate_role_permissions_cache(role_code):
    """
    Menghapus cache permission untuk SEMUA user yang punya role tertentu.
    Harus dipanggil saat:
    - Permission role diupdate (contoh: ADMIN sekarang bisa akses modul baru)

    Alur:
    1. Bump versi cache role → cache key lama invalid
    2. Hapus cache key lama (kompatibilitas)
    3. Cari semua user yang punya role ini (dari Profile.role)
    4. Invalidate cache masing-masing user

    Parameter:
    - role_code: Kode role (contoh: 'ADMIN', 'KASIR')
    """
    from auth.models import Profile

    role = normalize_role_code(role_code)

    # Putus cache role-level lama dan baru. Delete key lama menjaga kompatibilitas
    # dengan cache yang dibuat sebelum versi cache diperkenalkan.
    bump_role_permissions_cache_version(role)
    for candidate in {role, role.lower(), str(role_code or '').strip()}:
        if candidate:
            cache.delete(f'role_perms_{candidate}')

    # Invalidate cache untuk setiap user
    # Cari semua user_id yang punya role ini
    user_ids = Profile.objects.filter(role__iexact=role).values_list('user_id', flat=True)
    for user_id in user_ids:
        invalidate_user_permissions_cache(user_id)
