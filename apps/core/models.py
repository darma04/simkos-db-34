"""
==========================================================================
 CORE MODELS - Sistem RBAC (Role-Based Access Control)
==========================================================================
 File ini berisi model RolePermission — jantung sistem keamanan proyek.

 Apa itu RBAC?
 - Role-Based Access Control = Kontrol akses berdasarkan peran
 - Setiap user punya 1 role (dari Profile.role)
 - Setiap role punya daftar permission per modul/sub-modul
 - Permission: can_view, can_create, can_edit, can_delete

 Contoh penggunaan:
 - Role 'KASIR' → hanya bisa akses modul 'pos' dan 'penjualan'
 - Role 'ADMIN' → bisa akses semua modul kecuali pengaturan sistem
 - Role 'SUPERUSER' → bypass semua pengecekan (akses penuh)

 Koneksi penting:
 - auth/models.py → Profile.role menyimpan role user
 - apps/core/permissions.py → Fungsi has_permission() membaca model ini
 - apps/core/mixins.py → Mixin menggunakan has_permission() di views
 - apps/core/context_processors.py → Menyuntikkan permission ke template
 - apps/permission_management/ → UI untuk mengelola permissions
 - templates/layout/partials/menu/ → Sidebar difilter berdasarkan permission
==========================================================================
"""

from django.db import models  # Django ORM untuk definisi model database


class RolePermission(models.Model):
    """
    Model untuk menyimpan konfigurasi permission setiap role.

    Setiap record = 1 aturan permission:
    - Role X di Module Y (Sub-module Z) bisa View/Create/Edit/Delete

    Contoh data:
    | role   | module  | sub_module   | can_view | can_create | can_edit | can_delete |
    |--------|---------|--------------|----------|------------|----------|------------|
    | KASIR  | pos     | None         | True     | True       | False    | False      |
    | ADMIN  | produk  | kategori     | True     | True       | True     | True       |
    | USER   | produk  | daftar_produk| True     | False      | False    | False      |

    SUPERUSER tidak perlu record di tabel ini — selalu dapat akses penuh.
    """

    # ==================== DAFTAR ROLE STATIS ====================
    # Role bawaan sistem — untuk referensi dan backward compatibility
    # Role kustom bisa ditambahkan langsung di database
    ROLE_CHOICES = [
        ('SUPERUSER', 'Superuser - Full Access'),    # Akses penuh, bypass semua cek
        ('ADMIN', 'Admin - Limited Access'),          # Admin dengan akses terbatas
        ('USER', 'User - Read & Create Only'),        # User biasa
        ('PENGELOLA', 'Pengelola - Manajemen Kos'),   # Pengelola kos
    ]

    # ==================== DAFTAR MODUL ====================
    # Semua modul yang tersedia di sistem SIMKOS
    # Setiap modul sesuai dengan 1 menu utama di sidebar
    MODULE_CHOICES = [
        ('dashboard', 'Dashboard'),                    # Halaman utama analytics
        ('properti', 'Properti'),                      # Manajemen properti, tipe kamar, kamar
        ('penyewa', 'Penyewa'),                        # Manajemen penyewa
        ('sewa', 'Sewa'),                              # Kontrak, tagihan, pembayaran
        ('biaya', 'Biaya'),                            # Kategori biaya, transaksi biaya
        ('hr', 'Karyawan KOS'),                        # Karyawan, penggajian
        ('laporan', 'Laporan'),                        # Laporan: pemasukan, pengeluaran, hunian, keuangan
        ('automation', 'Automasi Telegram'),            # Notifikasi Telegram
        ('user_management', 'Manajemen User'),         # Kelola user
        ('access_control', 'Access Control'),           # Kelola role & permission
        ('activity_log', 'Log Aktivitas'),             # Riwayat aktivitas user
        ('pengaturan', 'Pengaturan'),                  # Pengaturan perusahaan & sistem
        ('ai', 'AI Assistant'),                          # AI Assistant: chat, dashboard, pengaturan
    ]

    # ==================== DAFTAR SUB-MODUL ====================
    # Sub-modul per modul — setiap sub-modul = 1 submenu di sidebar
    # Dictionary: key = kode modul, value = list of (kode_sub, nama_sub)
    SUB_MODULE_CHOICES = {
        'properti': [
            ('daftar_properti', 'Daftar Properti'),     # List semua properti
            ('tipe_kamar', 'Tipe Kamar'),               # CRUD Tipe Kamar
            ('daftar_kamar', 'Daftar Kamar'),           # List semua kamar
        ],
        'sewa': [
            ('kontrak', 'Kontrak Sewa'),                # CRUD Kontrak Sewa
            ('tagihan', 'Tagihan Sewa'),                # CRUD Tagihan Sewa
            ('pembayaran', 'Pembayaran'),               # CRUD Pembayaran
        ],
        'biaya': [
            ('kategori_biaya', 'Kategori Biaya'),       # CRUD Kategori Biaya
            ('transaksi_biaya', 'Transaksi Biaya'),     # CRUD Transaksi Biaya
        ],
        'hr': [
            ('karyawan', 'Daftar Karyawan'),            # CRUD Karyawan
            ('penggajian', 'Penggajian'),               # CRUD Penggajian
        ],
        'laporan': [
            ('laporan_pemasukan', 'Laporan Pemasukan'),         # Laporan pemasukan
            ('laporan_pengeluaran', 'Laporan Pengeluaran'),     # Laporan pengeluaran
            ('laporan_hunian', 'Laporan Hunian'),               # Laporan hunian
            ('laporan_keuangan', 'Laporan Keuangan'),           # Laporan keuangan
        ],
        'access_control': [
            ('roles', 'Roles'),                         # Daftar role
            ('permissions', 'Permissions'),              # Daftar permission
        ],
        'automation': [
            ('pengaturan_telegram', 'Pengaturan Telegram'),  # Setting bot Telegram
            ('template_pesan', 'Template Pesan'),             # Template pesan notifikasi
            ('log_notifikasi', 'Log Notifikasi'),             # Riwayat notifikasi
        ],
        'pengaturan': [
            ('profil', 'Profil Saya'),                       # Edit profil user
            ('perusahaan', 'Pengaturan Perusahaan'),         # Setting perusahaan
            ('template_cetak', 'Template Cetak'),             # Template cetak dokumen
            ('metode_pembayaran', 'Metode Pembayaran'),       # Setting rekening/pembayaran
            ('manajemen_data', 'Manajemen Data'),             # Manajemen data
        ],
        'ai': [
            ('ai_dashboard', 'Dashboard AI'),                 # Dashboard analytics AI
            ('ai_pengaturan', 'Pengaturan AI'),               # Pengaturan AI Assistant
        ],
    }

    # ==================== MAPPING SUB-MODULE KE SLUG MENU ====================
    # Konversi: kode database → slug sidebar (bagian setelah dash di menu)
    # Contoh:
    #   'daftar_properti' → 'list' (slug sidebar: 'properti-list')
    #   'kontrak' → 'kontrak' (slug sidebar: 'sewa-kontrak')
    #
    # Kenapa perlu mapping?
    # - Di database, sub-module disimpan sebagai 'daftar_properti', 'kontrak'
    # - Di sidebar (vertical_menu.json), slug-nya 'properti-list', 'sewa-kontrak'
    # - Mapping ini menjembatani keduanya
    SUB_MODULE_TO_SLUG = {
        # === Properti ===
        'daftar_properti': 'list',          # sidebar: properti-list
        'tipe_kamar': 'tipe-kamar',         # sidebar: properti-tipe-kamar
        'daftar_kamar': 'kamar',            # sidebar: properti-kamar
        # === Sewa ===
        'kontrak': 'kontrak',               # sidebar: sewa-kontrak
        'tagihan': 'tagihan',               # sidebar: sewa-tagihan
        'pembayaran': 'pembayaran',         # sidebar: sewa-pembayaran
        # === Biaya ===
        'kategori_biaya': 'kategori',       # sidebar: biaya-kategori
        'transaksi_biaya': 'transaksi',     # sidebar: biaya-transaksi
        # === HR / Karyawan KOS ===
        'karyawan': 'karyawan',             # sidebar: hr-karyawan
        'penggajian': 'penggajian',         # sidebar: hr-penggajian
        # === Laporan ===
        'laporan_pemasukan': 'pemasukan',   # sidebar: laporan-pemasukan
        'laporan_pengeluaran': 'pengeluaran', # sidebar: laporan-pengeluaran
        'laporan_hunian': 'hunian',         # sidebar: laporan-hunian
        'laporan_keuangan': 'keuangan',     # sidebar: laporan-keuangan
        # === Access Control ===
        'roles': 'roles',                   # sidebar: access-roles
        'permissions': 'permissions',       # sidebar: access-permissions
        # === Automation ===
        'pengaturan_telegram': 'pengaturan', # sidebar: automation-pengaturan
        'template_pesan': 'template',        # sidebar: automation-template
        'log_notifikasi': 'log',             # sidebar: automation-log
        # === Pengaturan ===
        'profil': 'profil',                          # sidebar: pengaturan-profil
        'perusahaan': 'perusahaan',                  # sidebar: pengaturan-perusahaan
        'template_cetak': 'template-cetak',          # sidebar: pengaturan-template-cetak
        'metode_pembayaran': 'metode-pembayaran',    # sidebar: pengaturan-metode-pembayaran
        'manajemen_data': 'manajemen-data',          # sidebar: pengaturan-manajemen-data
        # === AI Assistant ===
        'ai_dashboard': 'dashboard',                 # sidebar: ai-dashboard
        'ai_pengaturan': 'settings',                 # sidebar: ai-settings
    }

    # ==================== REVERSE MAPPING: SLUG → DB CODE ====================
    # Kebalikan dari SUB_MODULE_TO_SLUG
    # Digunakan untuk konversi dari slug sidebar ke kode database
    # Dibuild otomatis dari mapping di atas menggunakan loop
    SLUG_TO_SUB_MODULE = {}
    for _module_code, _subs in SUB_MODULE_CHOICES.items():
        SLUG_TO_SUB_MODULE[_module_code] = {}
        for _sub_code, _sub_name in _subs:
            _slug = SUB_MODULE_TO_SLUG.get(_sub_code, _sub_code)
            SLUG_TO_SUB_MODULE[_module_code][_slug] = _sub_code

    # ==================== FIELD DATABASE ====================

    # Role user (contoh: 'ADMIN', 'KASIR', 'STAFF_GUDANG')
    # choices dihapus agar bisa menerima role kustom dari database
    role = models.CharField(
        max_length=50,
        verbose_name="Role",
        db_index=True
    )

    # Modul yang diakses (contoh: 'produk', 'inventory', 'pos')
    module = models.CharField(
        max_length=50,
        choices=MODULE_CHOICES,
        verbose_name="Module",
        db_index=True
    )

    # Sub-modul (opsional) — untuk permission lebih detail
    # Contoh: modul 'produk' → sub-modul 'kategori', 'satuan', 'daftar_produk'
    # Jika None → permission berlaku untuk SEMUA sub-modul di modul tersebut
    sub_module = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Sub Module",
        help_text="Specific page/feature within module (e.g., 'kategori', 'satuan', 'daftar_produk')"
    )

    # ==================== FIELD PERMISSION ====================
    # 4 jenis permission (CRUD):

    can_view = models.BooleanField(
        default=True,
        verbose_name="Can View",
        help_text="Dapat melihat/membaca data"
    )
    can_create = models.BooleanField(
        default=False,
        verbose_name="Can Create",
        help_text="Dapat menambah data baru"
    )
    can_edit = models.BooleanField(
        default=False,
        verbose_name="Can Edit",
        help_text="Dapat mengubah data"
    )
    can_delete = models.BooleanField(
        default=False,
        verbose_name="Can Delete",
        help_text="Dapat menghapus data"
    )

    # Catatan/deskripsi tambahan tentang permission ini
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Deskripsi",
        help_text="Catatan tambahan tentang permission ini"
    )

    # ==================== FIELD TRACKING ====================
    created_at = models.DateTimeField(auto_now_add=True)  # Tanggal dibuat (otomatis)
    updated_at = models.DateTimeField(auto_now=True)       # Tanggal terakhir diubah (otomatis)

    # ==================== META CLASS ====================
    class Meta:
        # unique_together: Kombinasi role + module + sub_module harus unik
        # Artinya: 1 role hanya bisa punya 1 record per module per sub_module
        """Konfigurasi metadata model untuk Django."""
        unique_together = ('role', 'module', 'sub_module')
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"
        ordering = ['role', 'module', 'sub_module']  # Urutan default saat query

    # ==================== METHOD ====================

    def get_role_display(self):
        """
        Mendapatkan nama role yang mudah dibaca manusia.

        Kenapa manual? Karena field 'role' tidak pakai choices=
        (agar bisa menerima role kustom), maka Django tidak otomatis
        menyediakan get_role_display().

        Contoh:
        - 'ADMIN' → 'Admin - Limited Access'
        - 'STAFF_GUDANG' → 'Staff Gudang' (format otomatis)
        """
        role_dict = dict(self.ROLE_CHOICES)
        return role_dict.get(self.role, self.role.replace('_', ' ').title())

    def __str__(self):
        """
        Representasi string RolePermission.
        Format: "Admin - Produk > Kategori" atau "Kasir - POS / Kasir"
        """
        base = f"{self.get_role_display()} - {self.get_module_display()}"
        if self.sub_module:
            return f"{base} > {self.sub_module.replace('_', ' ').title()}"
        return base

    def get_permissions_summary(self):
        """
        Menghasilkan ringkasan permission yang mudah dibaca.

        Return: String seperti "View, Create, Edit" atau "No Access"
        Digunakan di admin panel dan halaman permission management.
        """
        perms = []
        if self.can_view:
            perms.append('View')
        if self.can_create:
            perms.append('Create')
        if self.can_edit:
            perms.append('Edit')
        if self.can_delete:
            perms.append('Delete')
        return ', '.join(perms) if perms else 'No Access'

    @classmethod
    def get_all_roles(cls):
        """
        Mendapatkan semua role yang AKTIF di sistem.

        Cara kerja:
        1. Query database: ambil semua role unik yang punya RolePermission records
        2. Untuk role statis (ADMIN, USER, KASIR): hanya tampilkan jika punya records di DB
        3. SUPERUSER selalu ditampilkan (bypass semua permission checks)
        4. Role kustom di-format otomatis: 'STAFF_GUDANG' → 'Staff Gudang'

        PENTING: Jika sebuah role (termasuk statis) sudah dihapus semua
        RolePermission-nya, role tersebut TIDAK akan muncul lagi di daftar.
        Ini memungkinkan admin untuk benar-benar menghapus role statis.

        Return: List of tuples [(kode, nama), ...]
        """
        # Mapping nama untuk role statis (referensi nama saja)
        static_role_names = dict(cls.ROLE_CHOICES)

        # Ambil role unik yang BENAR-BENAR ada di database
        from django.db.models import Count
        db_roles = cls.objects.values('role').annotate(count=Count('role')).order_by('role')

        # Kumpulkan role yang ada di DB
        active_roles = {}
        for item in db_roles:
            role_code = item['role']
            if role_code in static_role_names:
                # Role statis yang punya records di DB → tampilkan dengan nama statis
                active_roles[role_code] = static_role_names[role_code]
            else:
                # Role kustom: format otomatis nama dari kode
                active_roles[role_code] = role_code.replace('_', ' ').title()

        # SUPERUSER selalu ditampilkan (tidak perlu RolePermission records)
        if 'SUPERUSER' not in active_roles:
            active_roles['SUPERUSER'] = static_role_names.get('SUPERUSER', 'Superuser - Full Access')

        # Konversi ke list of tuples dan sort
        result = [(code, name) for code, name in active_roles.items()]
        return sorted(result, key=lambda x: x[1])
