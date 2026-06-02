"""
==========================================================================
HR VIEWS - View untuk Human Resources (SDM)
==========================================================================
File ini berisi views untuk modul HR (1292 baris - modul terbesar):

DASHBOARD HR:
    DashboardHRView → Statistik karyawan, absensi, penggajian

DEPARTEMEN CRUD (SubModulePermissionMixin):
    DepartemenListView/Create/Update/Delete

JABATAN CRUD:
    JabatanListView/Create/Update/Delete

KARYAWAN CRUD:
    KaryawanListView/Create/Update/Detail/Delete
    - Detail menampilkan riwayat absensi + penggajian

ABSENSI:
    AbsensiListView/Create/Update/Delete → CRUD manual
    AbsensiDeteksiWajahView → Halaman absensi deteksi wajah
    absensi_clock_in/clock_out → API clock in/out manual
    absensi_face_clock_in/out → API clock in/out via face recognition

PENGGAJIAN:
    PenggajianListView/Create/Update/Detail/Delete
    GeneratePenggajianView → Generate slip gaji massal untuk semua karyawan
    PenggajianUpdateStatusView → Update status bayar

FACE RECOGNITION:
    RegistrasiWajahView → Halaman registrasi wajah karyawan
    save_face_encoding() → API simpan encoding wajah
    delete_face() → API hapus foto wajah
    detect_face_api() → API deteksi & matching wajah

PENGATURAN ABSENSI:
    PengaturanAbsensiView → Kelola pengaturan (jam, lokasi, radius)
    PengaturanAbsensiCreateView/UpdateView
    pengaturan_absensi_delete/activate → Hapus/aktifkan pengaturan

⚠ FITUR KHUSUS:
- Face recognition opsional (FACE_RECOGNITION_ENABLED flag)
- Validasi lokasi GPS (radius kantor) untuk absensi
- Generate slip gaji massal dengan skip duplikasi
- Toleransi keterlambatan dari PengaturanAbsensi
==========================================================================
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, DetailView
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.db.models import Sum, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta, date
from decimal import Decimal
import base64
from io import BytesIO

from web_project import TemplateLayout
from apps.hr.models import Departemen, Jabatan, Karyawan, FotoWajah, Absensi, Penggajian, PengaturanAbsensi
from apps.hr.forms import (
    DepartemenForm, JabatanForm, KaryawanForm, 
    AbsensiForm, PenggajianForm, FotoWajahForm, GeneratePenggajianForm,
    PengaturanAbsensiForm
)
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin, SubModulePermissionMixin



# ╔══════════════════════════════════════════════════════════════╗
# ║  DASHBOARD HR - Statistik karyawan, absensi, penggajian       ║
# ╚══════════════════════════════════════════════════════════════╝
class DashboardHRView(ReadPermissionMixin, TemplateView):
    """
    Dashboard utama modul HR - menampilkan ringkasan statistik SDM.

    URL: /hr/
    Permission: hr.dashboard_hr.read (SubCRUD)
    Template: hr/dashboard.html

    Data yang ditampilkan:
    - Statistik karyawan (total, aktif, cuti)
    - Statistik departemen dan jabatan
    - Absensi hari ini (hadir, terlambat, izin, alpha)
    - Tingkat kehadiran (persentase)
    - Total penggajian bulan ini
    - Daftar karyawan terbaru (5 terakhir)
    - Riwayat absensi terbaru (10 terakhir)
    """
    template_name = 'hr/dashboard.html'          # Template halaman dashboard HR
    permission_module = 'hr'                      # Modul permission: HR
    permission_sub_module = 'dashboard_hr'        # Sub-modul: dashboard_hr (SubCRUD permission)

    def get_context_data(self, **kwargs):
        """
        Mengumpulkan semua data statistik HR untuk ditampilkan di dashboard.
        Menghitung: total karyawan, absensi hari ini, penggajian bulan ini,
        dan daftar karyawan/absensi terbaru.
        """
        # Inisialisasi layout global (sidebar, header, tema)
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        today = timezone.now().date()  # Tanggal hari ini untuk filter absensi
        context['today'] = today

# ── Statistik Karyawan ─────────────────────────────────
        # Hitung total karyawan yang masih aktif (belum resign/nonaktif)
        total_karyawan = Karyawan.objects.filter(aktif=True).count()
        context['total_karyawan'] = total_karyawan
        context['total_departemen'] = Departemen.objects.filter(aktif=True).count()  # Departemen aktif
        context['total_jabatan'] = Jabatan.objects.filter(aktif=True).count()        # Jabatan aktif

# ── Statistik Status Karyawan ──────────────────────────
        # Status 'aktif' = sedang bekerja, 'cuti' = sedang cuti
        context['karyawan_aktif'] = Karyawan.objects.filter(status='aktif').count()
        context['karyawan_cuti'] = Karyawan.objects.filter(status='cuti').count()

# ── Absensi Hari Ini (detail per status) ──────────────
        # Query absensi untuk tanggal hari ini saja
        absensi_hari_ini = Absensi.objects.filter(tanggal=today)
        context['absensi_hadir'] = absensi_hari_ini.filter(status='hadir').count()           # Hadir tepat waktu
        context['absensi_terlambat'] = absensi_hari_ini.filter(status='terlambat').count()   # Hadir tapi terlambat
        context['absensi_izin'] = absensi_hari_ini.filter(status__in=['izin', 'sakit', 'cuti']).count()  # Izin/sakit/cuti
        # Alpha = karyawan yang TIDAK absen sama sekali (total - yang sudah absen)
        context['absensi_alpha'] = max(0, total_karyawan - absensi_hari_ini.count()) if total_karyawan > 0 else 0

# ── Tingkat Kehadiran ──────────────────────────────────
        # Persentase kehadiran = (yang absen / total karyawan) × 100
        total_absen_hari_ini = absensi_hari_ini.count()
        context['tingkat_kehadiran'] = round((total_absen_hari_ini / total_karyawan * 100), 1) if total_karyawan > 0 else 0

# ── Penggajian Bulan Ini ───────────────────────────────
        # Aggregate total gaji bersih dan jumlah slip untuk bulan & tahun ini
        bulan_ini = today.month
        tahun_ini = today.year
        penggajian_bulan_ini = Penggajian.objects.filter(
            periode_bulan=bulan_ini, 
            periode_tahun=tahun_ini
        ).aggregate(
            total=Sum('gaji_bersih'),   # Total semua gaji bersih
            count=Count('id')           # Jumlah slip gaji
        )
        context['total_gaji_bulan_ini'] = penggajian_bulan_ini['total'] or 0

# ── Daftar Karyawan Terbaru (5 terakhir ditambahkan) ──
        # select_related() untuk menghindari N+1 query (join jabatan & departemen)
        context['karyawan_terbaru'] = Karyawan.objects.filter(aktif=True).select_related('jabatan', 'departemen').order_by('-dibuat_pada')[:5]

# ── Riwayat Absensi Terbaru (10 terakhir) ─────────────
        # Diurutkan berdasarkan tanggal terbaru, lalu jam masuk terbaru
        context['absensi_terbaru'] = Absensi.objects.select_related('karyawan').order_by('-tanggal', '-jam_masuk')[:10]

        return context


# ╔══════════════════════════════════════════════════════════════╗
# ║  DEPARTEMEN CRUD - Menggunakan SubModulePermissionMixin       ║
# ║  (berbeda dari modul lain yang pakai ReadPermissionMixin)     ║
# ╚══════════════════════════════════════════════════════════════╝
class DepartemenListView(SubModulePermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua departemen.

    URL: /hr/departemen/
    Permission: hr.departemen.read (SubCRUD - menggunakan SubModulePermissionMixin)
    Template: hr/departemen_list.html
    """
    model = Departemen                              # Model: Departemen
    template_name = 'hr/departemen_list.html'       # Template daftar departemen
    context_object_name = 'departemen_list'         # Nama variabel di template
    permission_module = 'hr'                        # Modul permission: HR
    permission_sub_module = 'departemen'            # Sub-modul: departemen
    permission_action = 'read'                      # Aksi: read (lihat data)

    def get_context_data(self, **kwargs):
        """Menambahkan total departemen dan karyawan untuk ringkasan di template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_departemen'] = self.get_queryset().count()           # Jumlah total departemen
        context['total_karyawan'] = Karyawan.objects.filter(aktif=True).count()  # Jumlah karyawan aktif
        return context



class DepartemenCreateView(SubModulePermissionMixin, CreateView):
    """
    Form untuk menambahkan departemen baru.

    URL: /hr/departemen/add/
    Permission: hr.departemen.create
    Template: hr/departemen_form.html
    Redirect: /hr/departemen/ setelah berhasil simpan
    """
    model = Departemen                              # Model: Departemen
    form_class = DepartemenForm                     # Form: DepartemenForm (kode, nama, kepala)
    template_name = 'hr/departemen_form.html'       # Template form create/edit
    success_url = reverse_lazy('hr:departemen')     # Redirect ke daftar setelah simpan
    permission_module = 'hr'
    permission_sub_module = 'departemen'
    permission_action = 'create'                    # Aksi: create (tambah data)

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Tambah Departemen' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Departemen'  # Judul di header form
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Departemen berhasil ditambahkan')
        return super().form_valid(form)  # Simpan ke database dan redirect



class DepartemenUpdateView(SubModulePermissionMixin, UpdateView):
    """
    Form untuk mengedit departemen yang sudah ada.

    URL: /hr/departemen/<pk>/edit/
    Permission: hr.departemen.write
    Template: hr/departemen_form.html (sama dengan create)
    Redirect: /hr/departemen/ setelah berhasil update
    """
    model = Departemen
    form_class = DepartemenForm
    template_name = 'hr/departemen_form.html'
    success_url = reverse_lazy('hr:departemen')
    permission_module = 'hr'
    permission_sub_module = 'departemen'
    permission_action = 'write'                     # Aksi: write (edit data)

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Edit Departemen' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Departemen'
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Departemen berhasil diupdate')
        return super().form_valid(form)



class DepartemenDeleteView(SubModulePermissionMixin, DeleteView):
    """
    Hapus departemen - dipanggil via AJAX dari frontend.

    URL: /hr/departemen/<pk>/delete/
    Permission: hr.departemen.delete
    Response: JSON {success: bool, message: string}
    """
    model = Departemen
    success_url = reverse_lazy('hr:departemen')
    permission_module = 'hr'
    permission_sub_module = 'departemen'
    permission_action = 'delete'                    # Aksi: delete (hapus data)

    def delete(self, request, *args, **kwargs):
        """
        Override method delete untuk mengembalikan JSON response (bukan redirect).
        Frontend memanggil endpoint ini via AJAX dan mengharapkan JSON.
        Jika gagal (misal: ada karyawan terkait), tangkap exception dan kembalikan error.
        """
        self.object = self.get_object()  # Ambil objek departemen berdasarkan pk dari URL
        try:
            nama = self.object.nama       # Simpan nama sebelum dihapus (untuk pesan)
            self.object.delete()          # Hapus dari database
            return JsonResponse({'success': True, 'message': f'Departemen {nama} berhasil dihapus'})
        except Exception as e:
            # Gagal hapus - biasanya karena ada relasi yang masih terkait
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus data ini karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
        # ║  JABATAN CRUD - Posisi/jabatan + gaji pokok per jabatan       ║
# ╚══════════════════════════════════════════════════════════════╝
class JabatanListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua jabatan beserta gaji pokok.

    URL: /hr/jabatan/
    Permission: hr.jabatan.read (SubCRUD)
    Template: hr/jabatan_list.html
    """
    model = Jabatan                                 # Model: Jabatan
    template_name = 'hr/jabatan_list.html'          # Template daftar jabatan
    context_object_name = 'jabatan_list'            # Nama variabel di template
    permission_module = 'hr'
    permission_sub_module = 'jabatan'               # Sub-modul: jabatan

    def get_queryset(self):
        """
        Query semua jabatan dengan select_related('departemen').
        select_related() melakukan JOIN SQL untuk menghindari N+1 query
        saat template mengakses jabatan.departemen.nama.
        """
        return Jabatan.objects.select_related('departemen').all()

    def get_context_data(self, **kwargs):
        """
        Menambahkan ringkasan jabatan ke context:
        - total_jabatan: jumlah semua jabatan
        - total_gaji: total keseluruhan gaji pokok (untuk summary card)
        - departemen_list: daftar departemen aktif (untuk filter dropdown)
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        queryset = self.get_queryset()
        context['total_jabatan'] = queryset.count()                                         # Jumlah total jabatan
        context['total_gaji'] = queryset.aggregate(total=Sum('gaji_pokok'))['total'] or 0   # Total gaji pokok semua jabatan
        context['departemen_list'] = Departemen.objects.filter(aktif=True).order_by('nama') # Departemen untuk filter
        return context



class JabatanCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk menambahkan jabatan baru.

    URL: /hr/jabatan/add/
    Permission: hr.create (menggunakan CreatePermissionMixin)
    Template: hr/jabatan_form.html
    Redirect: /hr/jabatan/ setelah berhasil simpan
    """
    model = Jabatan
    form_class = JabatanForm                        # Form: kode, nama, gaji_pokok, tunjangan
    template_name = 'hr/jabatan_form.html'
    success_url = reverse_lazy('hr:jabatan')        # Redirect ke daftar jabatan
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Tambah Jabatan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Jabatan'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Jabatan berhasil ditambahkan')
        return super().form_valid(form)



class JabatanUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit jabatan yang sudah ada.

    URL: /hr/jabatan/<pk>/edit/
    Permission: hr.edit (menggunakan UpdatePermissionMixin)
    Template: hr/jabatan_form.html
    """
    model = Jabatan
    form_class = JabatanForm
    template_name = 'hr/jabatan_form.html'
    success_url = reverse_lazy('hr:jabatan')
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul halaman 'Edit Jabatan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Jabatan'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Jabatan berhasil diupdate')
        return super().form_valid(form)



class JabatanDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus jabatan - dipanggil via AJAX dari frontend.

    URL: /hr/jabatan/<pk>/delete/
    Permission: hr.delete
    Response: JSON {success, message}
    """
    model = Jabatan
    success_url = reverse_lazy('hr:jabatan')
    permission_module = 'hr'

    def delete(self, request, *args, **kwargs):
        """
        Override delete untuk return JSON (AJAX).
        Jika jabatan masih dipakai karyawan, exception akan ditangkap.
        """
        self.object = self.get_object()
        try:
            nama = self.object.nama
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Jabatan {nama} berhasil dihapus'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus data ini karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)
        # ║  Detail: absensi 30 hari terakhir + penggajian 12 bulan       ║
# ╚══════════════════════════════════════════════════════════════╝
class KaryawanListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua karyawan dengan data jabatan dan departemen.

    URL: /hr/karyawan/
    Permission: hr.karyawan.read (SubCRUD)
    Template: hr/karyawan_list.html

    Context tambahan:
    - total_karyawan: jumlah seluruh karyawan
    - karyawan_aktif: jumlah karyawan berstatus 'aktif'
    - departemen_struktur: data departemen + karyawan + jabatan (untuk org chart)
    """
    model = Karyawan                                # Model: Karyawan
    template_name = 'hr/karyawan_list.html'         # Template daftar karyawan
    context_object_name = 'karyawan_list'           # Nama variabel di template
    permission_module = 'hr'
    permission_sub_module = 'karyawan'              # Sub-modul: karyawan

    def get_queryset(self):
        """
        Query semua karyawan dengan JOIN ke jabatan dan departemen.
        select_related() menghindari N+1 query saat template akses relasi.
        """
        return Karyawan.objects.select_related('jabatan', 'departemen').all()

    def get_context_data(self, **kwargs):
        """
        Menambahkan statistik karyawan dan struktur organisasi ke context.
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_karyawan'] = self.get_queryset().count()                    # Total karyawan
        context['karyawan_aktif'] = self.get_queryset().filter(status='aktif').count()  # Yang berstatus aktif

        # Struktur organisasi - prefetch_related() untuk menghindari N+1
        # saat iterasi departemen → karyawan & jabatan di template
        context['departemen_struktur'] = Departemen.objects.filter(aktif=True).prefetch_related(
            'karyawan_set', 'jabatan_set'
        )
        return context



class KaryawanCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk menambahkan karyawan baru.

    URL: /hr/karyawan/add/
    Permission: hr.create
    Template: hr/karyawan_form.html
    Redirect: /hr/karyawan/ setelah sukses

    Catatan: field 'dibuat_oleh' diisi otomatis dengan user yang login
    melalui form_valid() - bukan dari form input.
    """
    model = Karyawan
    form_class = KaryawanForm                       # Form: nama, NIK, jabatan, departemen, dll
    template_name = 'hr/karyawan_form.html'
    success_url = reverse_lazy('hr:karyawan')
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Tambah Karyawan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Karyawan'
        return context


    def form_valid(self, form):
        """
        Dipanggil saat form valid. Set field 'dibuat_oleh' dengan user
        yang sedang login sebelum menyimpan ke database.
        """
        form.instance.dibuat_oleh = self.request.user  # Set user pembuat otomatis
        messages.success(self.request, 'Karyawan berhasil ditambahkan')
        return super().form_valid(form)



class KaryawanUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit data karyawan.

    URL: /hr/karyawan/<pk>/edit/
    Permission: hr.edit
    Template: hr/karyawan_form.html (sama dengan create)
    """
    model = Karyawan
    form_class = KaryawanForm
    template_name = 'hr/karyawan_form.html'
    success_url = reverse_lazy('hr:karyawan')
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Edit Karyawan' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Karyawan'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Data karyawan berhasil diupdate')
        return super().form_valid(form)



class KaryawanDetailView(ReadPermissionMixin, DetailView):
    """
    Halaman detail karyawan - menampilkan profil lengkap + riwayat.

    URL: /hr/karyawan/<pk>/
    Permission: hr.read
    Template: hr/karyawan_detail.html

    Context tambahan:
    - absensi_list: riwayat absensi 30 hari terakhir
    - penggajian_list: riwayat slip gaji 12 bulan terakhir
    """
    model = Karyawan
    template_name = 'hr/karyawan_detail.html'
    context_object_name = 'karyawan'                # Nama variabel di template
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """
        Menambahkan riwayat absensi dan penggajian karyawan ke context.
        self.object = karyawan yang sedang dilihat (diambil berdasarkan pk URL).
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Riwayat absensi 30 hari terakhir (latest first)
        context['absensi_list'] = self.object.absensi_set.order_by('-tanggal')[:30]
        # Riwayat penggajian 12 bulan terakhir (latest first)
        context['penggajian_list'] = self.object.penggajian_set.order_by('-periode_tahun', '-periode_bulan')[:12]
        return context



class KaryawanDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus karyawan - dipanggil via AJAX dari frontend.

    URL: /hr/karyawan/<pk>/delete/
    Permission: hr.delete
    Response: JSON {success, message}

    ⚠ PERHATIAN: Menghapus karyawan akan menghapus semua data terkait
    (absensi, penggajian, foto wajah) jika menggunakan CASCADE.
    """
    model = Karyawan
    success_url = reverse_lazy('hr:karyawan')
    permission_module = 'hr'

    def delete(self, request, *args, **kwargs):
        """Override delete untuk return JSON (bukan redirect HTML)."""
        self.object = self.get_object()  # Ambil karyawan berdasarkan pk
        try:
            nama = self.object.nama       # Simpan nama sebelum dihapus
            self.object.delete()          # Hapus karyawan + data terkait
            return JsonResponse({'success': True, 'message': f'Karyawan {nama} berhasil dihapus'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus data ini karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
                            # ║  ABSENSI - CRUD manual + clock in/out + face recognition      ║
                            # ║  Filter by date range, status hadir/terlambat                 ║
# ╚══════════════════════════════════════════════════════════════╝
class AbsensiListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar absensi karyawan dengan filter tanggal.

    URL: /hr/absensi/
    Permission: hr.absensi.read (SubCRUD)
    Template: hr/absensi_list.html

    Fitur filter via GET params:
    - ?tanggal_dari=YYYY-MM-DD → filter absensi mulai dari tanggal ini
    - ?tanggal_sampai=YYYY-MM-DD → filter absensi sampai tanggal ini
    """
    model = Absensi                                 # Model: Absensi (kehadiran karyawan)
    template_name = 'hr/absensi_list.html'          # Template daftar absensi
    context_object_name = 'absensi_list'            # Nama variabel di template
    permission_module = 'hr'
    permission_sub_module = 'absensi'               # Sub-modul: absensi

    def get_queryset(self):
        """
        Query absensi dengan filter tanggal dari GET params.
        Urutkan dari tanggal terbaru, lalu jam masuk terbaru.
        select_related('karyawan') untuk JOIN dan hindari N+1 query.
        """
        queryset = Absensi.objects.select_related('karyawan').order_by('-tanggal', '-jam_masuk')

        # Ambil parameter filter tanggal dari URL query string
        tanggal_dari = self.request.GET.get('tanggal_dari')      # Format: YYYY-MM-DD
        tanggal_sampai = self.request.GET.get('tanggal_sampai')  # Format: YYYY-MM-DD

        # Terapkan filter tanggal jika diberikan
        if tanggal_dari:
            queryset = queryset.filter(tanggal__gte=tanggal_dari)    # Tanggal >= dari
        if tanggal_sampai:
            queryset = queryset.filter(tanggal__lte=tanggal_sampai)  # Tanggal <= sampai

        return queryset

    def get_context_data(self, **kwargs):
        """
        Menambahkan statistik absensi ke context:
        - total_absensi: jumlah record absensi (setelah filter)
        - today: tanggal hari ini untuk default filter
        - karyawan_list: dropdown filter karyawan
        - total_hadir/total_terlambat: hitungan per status
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_absensi'] = self.get_queryset().count()                         # Total record
        context['today'] = timezone.now().date()                                       # Tanggal hari ini
        context['karyawan_list'] = Karyawan.objects.filter(aktif=True).order_by('nama') # Untuk filter dropdown
        context['total_hadir'] = self.get_queryset().filter(status='hadir').count()         # Jumlah hadir tepat waktu
        context['total_terlambat'] = self.get_queryset().filter(status='terlambat').count() # Jumlah terlambat
        return context



class AbsensiCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk menambah absensi secara manual.

    URL: /hr/absensi/add/
    Permission: hr.create
    Template: hr/absensi_form.html

    Catatan: ini untuk input absensi manual oleh admin/HR.
    Untuk clock in/out otomatis, gunakan API absensi_clock_in/out.
    """
    model = Absensi
    form_class = AbsensiForm                        # Form: karyawan, tanggal, jam, status
    template_name = 'hr/absensi_form.html'
    success_url = reverse_lazy('hr:absensi')
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Tambah Absensi Manual' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Absensi Manual'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Absensi berhasil ditambahkan')
        return super().form_valid(form)



class AbsensiDeteksiWajahView(ReadPermissionMixin, TemplateView):
    """
    Halaman absensi dengan deteksi wajah (face recognition).

    URL: /hr/absensi/deteksi-wajah/
    Permission: hr.read
    Template: hr/absensi_deteksi.html

    Halaman ini menyediakan antarmuka kamera untuk:
    - Mendeteksi wajah karyawan secara real-time
    - Melakukan clock in/out otomatis berdasarkan matching wajah
    """
    template_name = 'hr/absensi_deteksi.html'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menyediakan data karyawan aktif dan waktu saat ini untuk form absensi."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['karyawan_list'] = Karyawan.objects.filter(aktif=True, status='aktif')  # Hanya karyawan aktif
        context['today'] = timezone.now().date()  # Tanggal hari ini
        context['now'] = timezone.now()           # Waktu saat ini (untuk tampilan jam)
        return context


@login_required
def absensi_clock_in(request):
    """
    API endpoint untuk melakukan Clock In karyawan.

    URL: /hr/absensi/clock-in/  (POST only)
    Input: karyawan_id (POST), foto (FILES, opsional)
    Response: JSON {success, message}

    Alur kerja:
    1. Cari karyawan berdasarkan ID
    2. Cek apakah sudah clock in hari ini (get_or_create)
    3. Jika belum → buat record absensi baru
        - Jam masuk < 09:00 → status 'hadir'
        - Jam masuk >= 09:00 → status 'terlambat'
    4. Jika sudah → return error (tidak boleh clock in 2x)
    """
    if request.method == 'POST':
        karyawan_id = request.POST.get('karyawan_id')  # ID karyawan dari form
        foto = request.FILES.get('foto')                # Foto opsional (selfie saat clock in)

        try:
            # Cari karyawan - harus aktif
            karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
            today = timezone.now().date()   # Tanggal hari ini
            now = timezone.now().time()     # Jam saat ini

            # get_or_create() = cari record, jika tidak ada maka buat baru
            # Lookup: karyawan + tanggal hari ini
            # defaults: nilai yang diset HANYA jika record BARU dibuat
            absensi, created = Absensi.objects.get_or_create(
                karyawan=karyawan,
                tanggal=today,
                defaults={
                    'jam_masuk': now,
                    'status': 'hadir' if now.hour < 9 else 'terlambat',  # Jam 9 = batas tepat waktu
                    'foto_masuk': foto  # Simpan foto selfie (jika ada)
                }
            )

            # Jika record sudah ada (created=False), tolak clock in duplikat
            if not created:
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} sudah melakukan clock in hari ini'
                })

            # Berhasil clock in - return success dengan nama dan jam
            return JsonResponse({
                'success': True,
                'message': f'Clock In berhasil untuk {karyawan.nama} pada {now.strftime("%H:%M")}'
            })

        except Karyawan.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Karyawan tidak ditemukan'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    # Hanya menerima method POST
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)


@login_required
def absensi_clock_out(request):
    """
    API endpoint untuk melakukan Clock Out karyawan.

    URL: /hr/absensi/clock-out/  (POST only)
    Input: karyawan_id (POST), foto (FILES, opsional)
    Response: JSON {success, message}

    Alur kerja:
    1. Cari karyawan berdasarkan ID
    2. Cari record absensi hari ini (harus sudah clock in)
    3. Cek apakah sudah clock out (jam_keluar sudah terisi)
    4. Jika belum → isi jam_keluar dan simpan
    5. Jika sudah → return error (tidak boleh clock out 2x)
    """
    if request.method == 'POST':
        karyawan_id = request.POST.get('karyawan_id')  # ID karyawan dari form
        foto = request.FILES.get('foto')                # Foto opsional (selfie saat clock out)

        try:
            karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
            today = timezone.now().date()
            now = timezone.now().time()

            # Cari record absensi hari ini - harus sudah clock in
            try:
                absensi = Absensi.objects.get(karyawan=karyawan, tanggal=today)

                # Cek apakah sudah clock out (jam_keluar sudah terisi)
                if absensi.jam_keluar:
                    return JsonResponse({
                        'success': False,
                        'message': f'{karyawan.nama} sudah melakukan clock out hari ini'
                    })

                # Isi jam keluar dan foto, lalu simpan
                absensi.jam_keluar = now          # Set jam keluar = waktu sekarang
                absensi.foto_keluar = foto        # Simpan foto clock out
                absensi.save()                    # Update ke database

                return JsonResponse({
                    'success': True,
                    'message': f'Clock Out berhasil untuk {karyawan.nama} pada {now.strftime("%H:%M")}'
                })

            except Absensi.DoesNotExist:
                # Belum clock in hari ini - tidak bisa clock out
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} belum melakukan clock in hari ini'
                })

        except Karyawan.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Karyawan tidak ditemukan'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    # Hanya menerima method POST
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)



class AbsensiUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit record absensi yang sudah ada.

    URL: /hr/absensi/<pk>/edit/
    Permission: hr.edit
    Template: hr/absensi_form.html
    """
    model = Absensi
    form_class = AbsensiForm
    template_name = 'hr/absensi_form.html'
    success_url = reverse_lazy('hr:absensi')
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Edit Absensi' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Absensi'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Absensi berhasil diupdate')
        return super().form_valid(form)



class AbsensiDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus record absensi - dipanggil via AJAX.

    URL: /hr/absensi/<pk>/delete/
    Permission: hr.delete
    Response: JSON {success, message}
    """
    model = Absensi
    success_url = reverse_lazy('hr:absensi')
    permission_module = 'hr'

    def delete(self, request, *args, **kwargs):
        """Override delete untuk return JSON - sertakan nama karyawan dan tanggal."""
        self.object = self.get_object()
        try:
            karyawan_nama = self.object.karyawan.nama  # Nama karyawan untuk pesan
            tanggal = self.object.tanggal               # Tanggal absensi untuk pesan
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Absensi {karyawan_nama} tanggal {tanggal} berhasil dihapus'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus data ini karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)


# ╔══════════════════════════════════════════════════════════════╗
                                        # ║  PENGGAJIAN - Slip gaji + generate massal                     ║
                                        # ║  GeneratePenggajianView: buat slip untuk SEMUA karyawan aktif ║
                                        # ║  PenggajianUpdateStatusView: update status bayar              ║
# ╚══════════════════════════════════════════════════════════════╝
class PenggajianListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Menampilkan daftar semua slip gaji karyawan.

    URL: /hr/penggajian/
    Permission: hr.penggajian.read (SubCRUD)
    Template: hr/penggajian_list.html

    Context tambahan:
    - total_slip: jumlah total slip gaji
    - grand_total: total seluruh gaji bersih
    - total_dibayar/total_diproses: hitungan per status
    - karyawan_list: untuk filter dropdown
    """
    model = Penggajian                              # Model: Penggajian (slip gaji)
    template_name = 'hr/penggajian_list.html'       # Template daftar slip gaji
    context_object_name = 'penggajian_list'         # Nama variabel di template
    permission_module = 'hr'
    permission_sub_module = 'penggajian'            # Sub-modul: penggajian

    def get_queryset(self):
        """
        Query slip gaji dengan JOIN ke karyawan.
        Urutkan dari periode terbaru (tahun desc, bulan desc).
        """
        return Penggajian.objects.select_related('karyawan').order_by('-periode_tahun', '-periode_bulan')

    def get_context_data(self, **kwargs):
        """
        Menambahkan statistik penggajian untuk summary card dan filter.
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        queryset = self.get_queryset()
        context['total_slip'] = queryset.count()                                          # Jumlah slip
        context['grand_total'] = queryset.aggregate(total=Sum('gaji_bersih'))['total'] or 0  # Total gaji bersih
        context['total_gaji_pokok'] = queryset.aggregate(total=Sum('gaji_pokok'))['total'] or 0  # Total gaji pokok
        # Total tunjangan = total_pendapatan - gaji_pokok (karena total_pendapatan = gaji_pokok + semua tunjangan + lembur + bonus)
        total_pendapatan_all = queryset.aggregate(total=Sum('total_pendapatan'))['total'] or 0
        total_gaji_pokok_all = context['total_gaji_pokok']
        context['total_tunjangan'] = total_pendapatan_all - total_gaji_pokok_all  # Selisih = tunjangan+lembur+bonus
        context['total_potongan'] = queryset.aggregate(total=Sum('total_potongan'))['total'] or 0  # Total potongan
        context['total_dibayar'] = queryset.filter(status='dibayar').count()               # Sudah dibayar
        context['total_diproses'] = queryset.filter(status='diproses').count()             # Masih diproses
        context['karyawan_list'] = Karyawan.objects.filter(aktif=True).order_by('nama')    # Dropdown filter
        return context



class PenggajianCreateView(CreatePermissionMixin, CreateView):
    """
    Form untuk membuat slip gaji individual untuk satu karyawan.

    URL: /hr/penggajian/add/
    Permission: hr.penggajian.create
    Template: hr/penggajian_form.html

    Catatan: Untuk generate slip gaji massal (semua karyawan sekaligus),
    gunakan GeneratePenggajianView.
    """
    model = Penggajian
    form_class = PenggajianForm                     # Form: karyawan, periode, gaji_pokok, tunjangan, potongan
    template_name = 'hr/penggajian_form.html'
    success_url = reverse_lazy('hr:penggajian')
    permission_module = 'hr'
    permission_sub_module = 'penggajian'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Tambah Slip Gaji' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Slip Gaji'
        return context


    def form_valid(self, form):
        form.instance.dibuat_oleh = self.request.user  # User yang membuat slip
        response = super().form_valid(form)
        from apps.automation.signals import kirim_notifikasi_penggajian
        try:
            kirim_notifikasi_penggajian(self.object)
        except Exception as e:
            print('Gagal kirim notifikasi telegram:', e)
        messages.success(self.request, 'Slip gaji berhasil dibuat')
        return response



class PenggajianUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Form untuk mengedit slip gaji yang sudah ada.

    URL: /hr/penggajian/<pk>/edit/
    Permission: hr.penggajian.edit
    Template: hr/penggajian_form.html
    """
    model = Penggajian
    form_class = PenggajianForm
    template_name = 'hr/penggajian_form.html'
    success_url = reverse_lazy('hr:penggajian')
    permission_module = 'hr'
    permission_sub_module = 'penggajian'

    def get_context_data(self, **kwargs):
        """Menambahkan judul 'Edit Slip Gaji' ke context."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Slip Gaji'
        return context


    def form_valid(self, form):

        messages.success(self.request, 'Slip gaji berhasil diupdate')
        return super().form_valid(form)



class PenggajianDetailView(ReadPermissionMixin, DetailView):
    """
    Halaman detail slip gaji - menampilkan rincian gaji lengkap.

    URL: /hr/penggajian/<pk>/
    Permission: hr.read
    Template: hr/penggajian_detail.html

    Menampilkan: gaji pokok, tunjangan, potongan, gaji bersih, status bayar.
    """
    model = Penggajian
    template_name = 'hr/penggajian_detail.html'
    context_object_name = 'slip'                    # Nama variabel di template = 'slip'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Inisialisasi layout. Data slip sudah tersedia via self.object."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        return context


class PenggajianPrintView(ReadPermissionMixin, DetailView):
    """
    Cetak slip gaji - template standalone A4 (tanpa layout dashboard).

    URL: /hr/penggajian/<pk>/print/
    Permission: hr.read
    Template: hr/penggajian_print.html (standalone, auto window.print())

    Menggunakan TemplateCetak.get_template('slip_gaji') untuk header,
    footer, dan signature - sama seperti PO/SO/Invoice print.
    """
    model = Penggajian
    template_name = 'hr/penggajian_print.html'
    context_object_name = 'slip'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menambahkan template cetak ke context."""
        context = super().get_context_data(**kwargs)
        from apps.pengaturan.models import TemplateCetak
        context['template'] = TemplateCetak.get_template('slip_gaji')
        return context


class PenggajianDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus slip gaji - dipanggil via AJAX.

    URL: /hr/penggajian/<pk>/delete/
    Permission: hr.penggajian.delete
    Response: JSON {success, message}
    """
    model = Penggajian
    success_url = reverse_lazy('hr:penggajian')
    permission_module = 'hr'
    permission_sub_module = 'penggajian'

    def delete(self, request, *args, **kwargs):
        """Override delete untuk return JSON - sertakan nama karyawan dan periode."""
        self.object = self.get_object()
        try:
            karyawan_nama = self.object.karyawan.nama  # Nama karyawan untuk pesan
            periode = self.object.periode               # Periode slip untuk pesan
            self.object.delete()
            return JsonResponse({'success': True, 'message': f'Slip gaji {karyawan_nama} {periode} berhasil dihapus'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Tidak dapat menghapus data ini karena masih memiliki data terkait. Silakan hapus data terkait terlebih dahulu.'})


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)



class GeneratePenggajianView(CreatePermissionMixin, TemplateView):
    """
    Generate slip gaji massal untuk SEMUA karyawan aktif dalam satu periode.

    URL: /hr/penggajian/generate/
    Permission: hr.create
    Template: hr/penggajian_generate.html

    Alur kerja (POST):
    1. Validasi form (bulan, tahun, tunjangan_makan, tunjangan_transport)
    2. Loop semua karyawan aktif
    3. Cek duplikasi - skip jika slip sudah ada untuk periode tersebut
    4. Buat slip gaji baru dengan gaji_pokok dari karyawan/jabatan
    5. Report: berapa yang dibuat vs dilewati
    """
    template_name = 'hr/penggajian_generate.html'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """Menyediakan form generate dan jumlah karyawan yang akan diproses."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = GeneratePenggajianForm()                                          # Form: bulan, tahun, tunjangan
        context['karyawan_count'] = Karyawan.objects.filter(aktif=True, status='aktif').count()  # Jumlah karyawan aktif
        return context


    def post(self, request, *args, **kwargs):
        """
        Proses generate slip gaji massal.
        Iterasi semua karyawan aktif, cek duplikasi, buat slip baru.
        """
        form = GeneratePenggajianForm(request.POST)

        if form.is_valid():
            # Ambil data dari form yang sudah divalidasi
            bulan = int(form.cleaned_data['periode_bulan'])           # Bulan (1-12)
            tahun = int(form.cleaned_data['periode_tahun'])           # Tahun (YYYY)
            tunjangan_makan = form.cleaned_data['tunjangan_makan']       # Tunjangan makan per bulan
            tunjangan_transport = form.cleaned_data['tunjangan_transport'] # Tunjangan transport per bulan

            # Ambil semua karyawan aktif untuk dibuatkan slip
            karyawan_list = Karyawan.objects.filter(aktif=True, status='aktif')
            created_count = 0   # Counter slip yang berhasil dibuat
            skipped_count = 0   # Counter slip yang dilewati (sudah ada)

            for karyawan in karyawan_list:
                # Cek apakah slip sudah ada untuk karyawan + periode ini
                exists = Penggajian.objects.filter(
                    karyawan=karyawan,
                    periode_bulan=bulan,
                    periode_tahun=tahun
                ).exists()

                if exists:
                    skipped_count += 1  # Lewati, jangan buat duplikat
                    continue

                # Buat slip gaji baru
                # gaji_pokok: prioritas dari karyawan, fallback ke jabatan
                # tunjangan_jabatan: dari jabatan karyawan (jika ada)
                new_slip = Penggajian.objects.create(
                    karyawan=karyawan,
                    periode_bulan=bulan,
                    periode_tahun=tahun,
                    gaji_pokok=karyawan.gaji_pokok or (karyawan.jabatan.gaji_pokok if karyawan.jabatan else 0),
                    tunjangan_jabatan=karyawan.jabatan.tunjangan_jabatan if karyawan.jabatan else 0,
                    tunjangan_makan=tunjangan_makan,
                    tunjangan_transport=tunjangan_transport,
                    dibuat_oleh=request.user  # User yang menjalankan generate
                )
                from apps.automation.signals import kirim_notifikasi_penggajian
                try:
                    kirim_notifikasi_penggajian(new_slip)
                except Exception as e:
                    print('Gagal telegram massal:', e)
                created_count += 1

            # Tampilkan ringkasan hasil generate
            messages.success(
                request,
                f'Berhasil generate {created_count} slip gaji. {skipped_count} dilewati (sudah ada).'
            )
            return redirect('hr:penggajian')

        # Form tidak valid - tampilkan ulang dengan error
        context = self.get_context_data()
        context['form'] = form
        return render(request, self.template_name, context)



class PenggajianUpdateStatusView(UpdatePermissionMixin, UpdateView):
    """
    Update status pembayaran slip gaji (diproses → dibayar).

    URL: /hr/penggajian/<pk>/update-status/
    Permission: hr.edit
    Fields: status, tanggal_bayar, metode_pembayaran
    Redirect: /hr/penggajian/

    ⚠ PENTING: Saat status diubah ke 'dibayar', metode_pembayaran WAJIB diisi
    agar saldo MetodePembayaran berkurang dan masuk ke laporan keuangan.
    """
    model = Penggajian
    fields = ['status', 'tanggal_bayar', 'metode_pembayaran']  # 3 field yang bisa diubah
    success_url = reverse_lazy('hr:penggajian')
    permission_module = 'hr'


    def form_valid(self, form):
        """Update status penggajian. Validasi metode_pembayaran wajib jika status='dibayar'."""
        instance = form.save(commit=False)

        # Validasi: jika status 'dibayar', metode_pembayaran wajib diisi
        if instance.status == 'dibayar' and not instance.metode_pembayaran:
            form.add_error(
                'metode_pembayaran',
                'Metode pembayaran wajib diisi saat status diubah ke Dibayar.'
            )
            return self.form_invalid(form)

        # Validasi: jika status 'dibayar', tanggal_bayar wajib diisi
        if instance.status == 'dibayar' and not instance.tanggal_bayar:
            from datetime import date
            instance.tanggal_bayar = date.today()

        instance.save()
        messages.success(self.request, 'Status penggajian berhasil diupdate')
        return super().form_valid(form)


# ╔══════════════════════════════════════════════════════════════╗
# ║  FACE RECOGNITION - registrasi, deteksi, clock in/out wajah  ║
# ║  Opsional: tergantung FACE_RECOGNITION_ENABLED flag          ║
# ╚══════════════════════════════════════════════════════════════╝
# Import face utilities
try:
    from apps.hr import face_utils
    FACE_RECOGNITION_ENABLED = True
except ImportError:
    FACE_RECOGNITION_ENABLED = False



class RegistrasiWajahView(CreatePermissionMixin, TemplateView):
    """
    Halaman registrasi wajah karyawan untuk face recognition.

    URL: /hr/registrasi-wajah/
    Permission: hr.create
    Template: hr/registrasi_wajah.html

    Menampilkan daftar karyawan aktif dan foto wajah yang sudah terdaftar.
    User dapat mengambil foto baru dari kamera untuk didaftarkan.
    """
    template_name = 'hr/registrasi_wajah.html'
    permission_module = 'hr'

    def get_context_data(self, **kwargs):
        """
        Menyediakan data karyawan dan foto wajah terdaftar.
        foto_wajah_per_karyawan: dict {karyawan_pk: queryset_foto}
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        karyawan_list = Karyawan.objects.filter(aktif=True, status='aktif')  # Hanya karyawan aktif
        context['karyawan_list'] = karyawan_list
        context['face_recognition_enabled'] = FACE_RECOGNITION_ENABLED  # Flag: apakah lib tersedia

        # Muat foto wajah terdaftar, grouped by karyawan
        # Hanya foto yang masih aktif, diurutkan terbaru dulu
        foto_wajah_per_karyawan = {}
        for karyawan in karyawan_list:
            fotos = karyawan.foto_wajah_set.filter(aktif=True).order_by('-dibuat_pada')
            if fotos.exists():
                foto_wajah_per_karyawan[karyawan.pk] = fotos
        context['foto_wajah_per_karyawan'] = foto_wajah_per_karyawan
        return context


@login_required
def save_face_encoding(request):
    """
    API endpoint untuk menyimpan encoding wajah karyawan.

    URL: /hr/face/save-encoding/  (POST only)
    Input: karyawan_id (POST), foto_base64 atau foto (FILES)
    Response: JSON {success, message, foto_id, total_foto}

    Alur kerja:
    1. Cek apakah face recognition tersedia (library terinstall)
    2. Ambil foto dari base64 atau file upload
    3. Encode wajah menggunakan face_utils
    4. Simpan FotoWajah dengan encoding ke database
    5. Return jumlah total foto terdaftar
    """
    if request.method == 'POST':
        # Cek apakah library face_recognition tersedia
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        karyawan_id = request.POST.get('karyawan_id')   # ID karyawan target
        foto_base64 = request.POST.get('foto_base64')   # Foto dari kamera (base64)
        foto_file = request.FILES.get('foto')            # Foto dari file upload

        # Validasi: karyawan harus dipilih
        if not karyawan_id:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak dipilih'
            })

        try:
            karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)

            # Encode wajah dari foto yang diberikan
            if foto_base64:
                # Dari kamera browser (base64 string)
                encoding = face_utils.encode_face_from_base64(foto_base64)
                # Konversi base64 ke file Django untuk disimpan di storage
                if ',' in foto_base64:
                    foto_base64 = foto_base64.split(',')[1]  # Hapus header "data:image/...;base64,"
                foto_data = base64.b64decode(foto_base64)
                from django.core.files.base import ContentFile
                foto_file = ContentFile(foto_data, name=f'wajah_{karyawan_id}_{timezone.now().timestamp()}.jpg')
            elif foto_file:
                # Dari file upload langsung
                encoding = face_utils.encode_face_from_file(foto_file)
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Foto tidak ditemukan'
                })

            # Validasi: wajah harus terdeteksi dalam foto
            if not encoding:
                return JsonResponse({
                    'success': False,
                    'message': 'Tidak dapat mendeteksi wajah dalam foto. Pastikan wajah terlihat jelas dan menghadap kamera.'
                })

            # Simpan foto wajah + encoding ke database
            foto_wajah = FotoWajah.objects.create(
                karyawan=karyawan,
                foto=foto_file,       # File foto yang disimpan di storage
                encoding=encoding,    # Vector encoding wajah (untuk matching)
                aktif=True
            )

            # Hitung total foto wajah yang terdaftar aktif
            total_foto = karyawan.foto_wajah_set.filter(aktif=True).count()

            return JsonResponse({
                'success': True,
                'message': f'Wajah {karyawan.nama} berhasil didaftarkan! ({total_foto} foto terdaftar)',
                'foto_id': foto_wajah.pk,
                'total_foto': total_foto
            })

        except Karyawan.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak ditemukan'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)

@login_required
def delete_face(request, pk):
    """
    API untuk menghapus foto wajah terdaftar (soft delete).

    URL: /hr/face/<pk>/delete/  (DELETE atau POST)
    Response: JSON {success, message}

    Catatan: Tidak menghapus record dari database,
    hanya mengubah field aktif menjadi False (soft delete).
    """
    if request.method == 'DELETE' or request.method == 'POST':
        try:
            foto = FotoWajah.objects.get(pk=pk)
            karyawan_nama = foto.karyawan.nama
            foto.aktif = False    # Soft delete: nonaktifkan, jangan hapus
            foto.save()
            return JsonResponse({
                'success': True,
                'message': f'Foto wajah {karyawan_nama} berhasil dihapus'
            })
        except FotoWajah.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Foto tidak ditemukan'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


@login_required
def detect_face_api(request):
    """
    API endpoint untuk mendeteksi wajah dan mencocokkan dengan karyawan terdaftar.

    URL: /hr/face/detect/  (POST only)
    Input: foto_base64 atau foto (FILES)
    Response: JSON {success, has_face, karyawan_id, confidence, ...}

    Alur kerja:
    1. Konversi foto ke array numpy
    2. Validasi apakah ada wajah dalam foto
    3. Bandingkan encoding wajah dengan semua karyawan terdaftar
    4. Return karyawan yang paling cocok (jika confidence > threshold=0.55)
    """
    if request.method == 'POST':
        # Cek library face_recognition
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        foto_base64 = request.POST.get('foto_base64')  # Dari kamera browser
        foto_file = request.FILES.get('foto')           # Dari file upload

        try:
            # Konversi foto ke numpy array untuk diproses
            if foto_base64:
                img = face_utils.base64_to_array(foto_base64)
            elif foto_file:
                img = face_utils.image_to_array(foto_file)
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Foto tidak ditemukan'
                })

            # Validasi: apakah ada wajah terdeteksi dalam foto
            has_face, face_rect = face_utils.validate_face_exists(img)
            if not has_face:
                return JsonResponse({
                    'success': False,
                    'message': 'Tidak dapat mendeteksi wajah dalam foto',
                    'has_face': False
                })

            # Cari karyawan yang cocok dari database
            # prefetch_related() untuk load foto_wajah dalam 1 query
            karyawan_list = Karyawan.objects.filter(
                aktif=True,
                status='aktif'
            ).prefetch_related('foto_wajah_set')

            # Bandingkan wajah dengan semua encoding terdaftar
            # threshold=0.55 = batas minimal kemiripan untuk dianggap cocok
            matched_karyawan, confidence = face_utils.find_matching_karyawan(
                img,
                karyawan_list,
                threshold=0.55
            )

            if matched_karyawan:
                # Wajah cocok - return data karyawan yang ditemukan
                return JsonResponse({
                    'success': True,
                    'message': f'Wajah dikenali: {matched_karyawan.nama}',
                    'has_face': True,
                    'karyawan_id': matched_karyawan.pk,
                    'karyawan_nama': matched_karyawan.nama,
                    'karyawan_nik': matched_karyawan.nik,
                    'confidence': round(confidence * 100, 1),  # Persentase kemiripan
                    'jabatan': matched_karyawan.jabatan.nama if matched_karyawan.jabatan else '-',
                    'departemen': matched_karyawan.departemen.nama if matched_karyawan.departemen else '-'
                })
            else:
                # Wajah tidak dikenali - tidak ada yang cocok
                return JsonResponse({
                    'success': False,
                    'message': 'Wajah tidak dikenali. Pastikan karyawan sudah terdaftar.',
                    'has_face': True,
                    'karyawan_id': None
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


@login_required
def absensi_face_clock_in(request):
    """
    API untuk clock in menggunakan face recognition.

    URL: /hr/absensi/face-clock-in/  (POST only)
    Input: foto_base64 (POST), karyawan_id (opsional), latitude, longitude (opsional)
    Response: JSON {success, karyawan_nama, jam_masuk, status, confidence}

    Alur kerja:
    1. Cek apakah face recognition tersedia
    2. Validasi lokasi (jika fitur wajib_lokasi aktif di pengaturan)
    3. Jika karyawan_id tidak diberikan → deteksi wajah otomatis
    4. Tentukan status hadir/terlambat berdasarkan pengaturan jam masuk
    5. Simpan record absensi dengan foto selfie dan confidence score
    """
    if request.method == 'POST':
        # Cek library face_recognition
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        foto_base64 = request.POST.get('foto_base64')                  # Foto dari kamera
        karyawan_id = request.POST.get('karyawan_id')                  # Opsional: dari auto-detect

        # Ambil lokasi GPS user (untuk validasi radius kantor)
        user_latitude = request.POST.get('latitude')
        user_longitude = request.POST.get('longitude')

        try:
            # Ambil pengaturan absensi yang aktif (jam masuk, toleransi, lokasi)
            pengaturan = PengaturanAbsensi.get_active()

            # ===== VALIDASI LOKASI =====
            # Jika pengaturan wajib_lokasi diaktifkan, cek GPS user
            if pengaturan and pengaturan.wajib_lokasi:
                if not user_latitude or not user_longitude:
                    return JsonResponse({
                        'success': False,
                        'message': 'Lokasi diperlukan. Silakan aktifkan GPS dan berikan izin lokasi.'
                    })

                # Cek jarak user ke lokasi kantor
                if pengaturan.latitude and pengaturan.longitude and pengaturan.radius_lokasi:
                    is_valid, distance, msg = face_utils.validate_location(
                        user_latitude, user_longitude,
                        pengaturan.latitude, pengaturan.longitude,
                        pengaturan.radius_lokasi
                    )

                    # Jika di luar radius → tolak absensi
                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'message': f'Absensi gagal! {msg}. Anda harus berada dalam radius {pengaturan.radius_lokasi}m dari kantor.'
                        })

            # ===== DETEKSI WAJAH =====
            # Jika karyawan_id tidak diberikan, deteksi wajah otomatis
            if not karyawan_id:
                if not foto_base64:
                    return JsonResponse({
                        'success': False,
                        'message': 'Foto diperlukan untuk absensi'
                    })

                img = face_utils.base64_to_array(foto_base64)

                # Cari karyawan yang cocok dari semua yang terdaftar
                karyawan_list = Karyawan.objects.filter(
                    aktif=True,
                    status='aktif'
                ).prefetch_related('foto_wajah_set')

                karyawan, confidence = face_utils.find_matching_karyawan(
                    img,
                    karyawan_list,
                    threshold=0.55  # Batas minimal kemiripan
                )

                if not karyawan:
                    return JsonResponse({
                        'success': False,
                        'message': 'Wajah tidak dikenali. Pastikan wajah sudah terdaftar.'
                    })
            else:
                # karyawan_id diberikan langsung (dari auto-detect sebelumnya)
                karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
                confidence = 1.0  # Tidak perlu matching lagi

            today = timezone.now().date()
            now = timezone.now().time()

            # ===== TENTUKAN STATUS ABSENSI =====
            # Gunakan pengaturan jam masuk + toleransi untuk menentukan hadir/terlambat
            jam_masuk_pengaturan = pengaturan.jam_masuk if pengaturan else None
            toleransi = pengaturan.toleransi_terlambat if pengaturan else 0

            if jam_masuk_pengaturan:
                # Hitung batas toleransi: jam_masuk + toleransi menit
                batas_terlambat = datetime.combine(today, jam_masuk_pengaturan) + timedelta(minutes=toleransi)
                waktu_sekarang = datetime.combine(today, now)
                status_absensi = 'hadir' if waktu_sekarang <= batas_terlambat else 'terlambat'
            else:
                # Fallback: jam 9 pagi sebagai batas default
                status_absensi = 'hadir' if now.hour < 9 else 'terlambat'

            # ===== SIMPAN FOTO =====
            # Konversi base64 ke file Django untuk disimpan
            foto_file = None
            if foto_base64:
                if ',' in foto_base64:
                    foto_base64 = foto_base64.split(',')[1]  # Hapus header data:image/...
                foto_data = base64.b64decode(foto_base64)
                from django.core.files.base import ContentFile
                foto_file = ContentFile(foto_data, name=f'clockin_{karyawan.pk}_{today}.jpg')

            # ===== BUAT RECORD ABSENSI =====
            # get_or_create: cek duplikasi (1 karyawan = 1 absensi/hari)
            absensi, created = Absensi.objects.get_or_create(
                karyawan=karyawan,
                tanggal=today,
                defaults={
                    'jam_masuk': now,
                    'status': status_absensi,
                    'foto_masuk': foto_file,
                    'persentase_kemiripan': round(confidence * 100, 1) if confidence else None  # Simpan confidence
                }
            )

            # Jika sudah clock in hari ini → tolak
            if not created:
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} sudah melakukan clock in hari ini pada {absensi.jam_masuk.strftime("%H:%M")}'
                })

            # Berhasil clock in
            return JsonResponse({
                'success': True,
                'message': f'Clock In berhasil untuk {karyawan.nama}',
                'karyawan_nama': karyawan.nama,
                'jam_masuk': now.strftime("%H:%M"),
                'status': absensi.status,
                'confidence': round(confidence * 100, 1)
            })

        except Karyawan.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak ditemukan'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


@login_required
def absensi_face_clock_out(request):
    """
    API untuk clock out menggunakan face recognition.

    URL: /hr/absensi/face-clock-out/  (POST only)
    Input: foto_base64 (POST), karyawan_id (opsional), latitude, longitude (opsional)
    Response: JSON {success, karyawan_nama, jam_keluar, confidence}

    Alur kerja mirip face_clock_in:
    1. Validasi lokasi (jika wajib)
    2. Deteksi wajah (jika karyawan_id tidak diberikan)
    3. Cari record absensi hari ini (harus sudah clock in)
    4. Update jam_keluar dan simpan foto clock out
    """
    if request.method == 'POST':
        # Cek library face_recognition
        if not FACE_RECOGNITION_ENABLED:
            return JsonResponse({
                'success': False,
                'message': 'Face recognition tidak tersedia'
            }, status=500)

        foto_base64 = request.POST.get('foto_base64')                  # Foto dari kamera
        karyawan_id = request.POST.get('karyawan_id')                  # Opsional

        # Ambil lokasi GPS user
        user_latitude = request.POST.get('latitude')
        user_longitude = request.POST.get('longitude')

        try:
            # Ambil pengaturan absensi yang aktif
            pengaturan = PengaturanAbsensi.get_active()

            # ===== VALIDASI LOKASI =====
            if pengaturan and pengaturan.wajib_lokasi:
                if not user_latitude or not user_longitude:
                    return JsonResponse({
                        'success': False,
                        'message': 'Lokasi diperlukan. Silakan aktifkan GPS dan berikan izin lokasi.'
                    })

                if pengaturan.latitude and pengaturan.longitude and pengaturan.radius_lokasi:
                    is_valid, distance, msg = face_utils.validate_location(
                        user_latitude, user_longitude,
                        pengaturan.latitude, pengaturan.longitude,
                        pengaturan.radius_lokasi
                    )

                    if not is_valid:
                        return JsonResponse({
                            'success': False,
                            'message': f'Absensi gagal! {msg}. Anda harus berada dalam radius {pengaturan.radius_lokasi}m dari kantor.'
                        })

            # ===== DETEKSI WAJAH =====
            if not karyawan_id:
                if not foto_base64:
                    return JsonResponse({
                        'success': False,
                        'message': 'Foto diperlukan untuk absensi'
                    })

                img = face_utils.base64_to_array(foto_base64)

                # Cari karyawan yang cocok
                karyawan_list = Karyawan.objects.filter(
                    aktif=True,
                    status='aktif'
                ).prefetch_related('foto_wajah_set')

                karyawan, confidence = face_utils.find_matching_karyawan(
                    img,
                    karyawan_list,
                    threshold=0.55
                )

                if not karyawan:
                    return JsonResponse({
                        'success': False,
                        'message': 'Wajah tidak dikenali. Pastikan wajah sudah terdaftar.'
                    })
            else:
                karyawan = Karyawan.objects.get(pk=karyawan_id, aktif=True)
                confidence = 1.0

            today = timezone.now().date()
            now = timezone.now().time()

            # ===== SIMPAN FOTO CLOCK OUT =====
            foto_file = None
            if foto_base64:
                if ',' in foto_base64:
                    foto_base64 = foto_base64.split(',')[1]
                foto_data = base64.b64decode(foto_base64)
                from django.core.files.base import ContentFile
                foto_file = ContentFile(foto_data, name=f'clockout_{karyawan.pk}_{today}.jpg')

            # ===== UPDATE ABSENSI =====
            # Cari record absensi hari ini - harus sudah clock in
            try:
                absensi = Absensi.objects.get(karyawan=karyawan, tanggal=today)

                # Cek apakah sudah clock out
                if absensi.jam_keluar:
                    return JsonResponse({
                        'success': False,
                        'message': f'{karyawan.nama} sudah melakukan clock out hari ini pada {absensi.jam_keluar.strftime("%H:%M")}'
                    })

                # Update jam keluar dan foto
                absensi.jam_keluar = now
                absensi.foto_keluar = foto_file
                # Update persentase kemiripan jika belum ada
                if not absensi.persentase_kemiripan and confidence:
                    absensi.persentase_kemiripan = round(confidence * 100, 1)
                absensi.save()

                return JsonResponse({
                    'success': True,
                    'message': f'Clock Out berhasil untuk {karyawan.nama}',
                    'karyawan_nama': karyawan.nama,
                    'jam_keluar': now.strftime("%H:%M"),
                    'confidence': round(confidence * 100, 1)
                })

            except Absensi.DoesNotExist:
                # Belum clock in → tidak bisa clock out
                return JsonResponse({
                    'success': False,
                    'message': f'{karyawan.nama} belum melakukan clock in hari ini'
                })

        except Karyawan.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Karyawan tidak ditemukan'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)

    # Hanya menerima method POST
    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)


# ╔══════════════════════════════════════════════════════════════╗
# ║  PENGATURAN ABSENSI - jam masuk/pulang, lokasi, toleransi     ║
# ║  Mendukung multiple pengaturan, hanya 1 yang aktif            ║
# ╚══════════════════════════════════════════════════════════════╝
@method_decorator(login_required, name='dispatch')
class PengaturanAbsensiView(TemplateView):
    """
    Halaman pengaturan absensi - kelola jam masuk/pulang, lokasi, toleransi.

    URL: /hr/pengaturan-absensi/
    Template: hr/pengaturan_absensi.html

    Mendukung multiple pengaturan (preset), tapi hanya 1 yang aktif.
    Menampilkan form edit pengaturan aktif + daftar semua pengaturan.
    """
    template_name = 'hr/pengaturan_absensi.html'

    def get_context_data(self, **kwargs):
        """
        Menyediakan form pengaturan dan daftar semua preset.
        Jika ada pengaturan aktif, form diisi dengan data tersebut.
        Jika tidak, tampilkan form kosong.
        """
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Ambil pengaturan yang aktif (atau yang pertama sebagai fallback)
        pengaturan = PengaturanAbsensi.get_active()
        if not pengaturan:
            pengaturan = PengaturanAbsensi.objects.first()

        # Daftar semua pengaturan (untuk tab/dropdown)
        context['pengaturan_list'] = PengaturanAbsensi.objects.all()
        context['pengaturan_aktif'] = PengaturanAbsensi.get_active()

        # Form - pre-fill jika ada pengaturan yang dipilih
        if pengaturan:
            context['form'] = PengaturanAbsensiForm(instance=pengaturan)
            context['pengaturan'] = pengaturan
        else:
            context['form'] = PengaturanAbsensiForm()
            context['pengaturan'] = None

        return context


    def post(self, request, *args, **kwargs):
        """
        Simpan perubahan pengaturan absensi.
        Jika pengaturan_id diberikan → update existing,
        jika tidak → buat baru.
        """
        pengaturan_id = request.POST.get('pengaturan_id')  # ID pengaturan yang diedit

        if pengaturan_id:
            # Update pengaturan yang sudah ada
            pengaturan = get_object_or_404(PengaturanAbsensi, pk=pengaturan_id)
            form = PengaturanAbsensiForm(request.POST, instance=pengaturan)
        else:
            # Buat pengaturan baru
            form = PengaturanAbsensiForm(request.POST)

        if form.is_valid():
            pengaturan = form.save()
            messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil disimpan!')
            return redirect('hr:pengaturan-absensi')
        else:
            # Form tidak valid - tampilkan ulang dengan error
            context = self.get_context_data()
            context['form'] = form
            messages.error(request, 'Terjadi kesalahan. Silakan periksa form.')
            return self.render_to_response(context)


@method_decorator(login_required, name='dispatch')
class PengaturanAbsensiCreateView(TemplateView):
    """
    Form untuk membuat pengaturan absensi baru (preset baru).

    URL: /hr/pengaturan-absensi/add/
    Template: hr/pengaturan_absensi_form.html
    """
    template_name = 'hr/pengaturan_absensi_form.html'

    def get_context_data(self, **kwargs):
        """Menyediakan form kosong dan flag is_new=True."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['form'] = PengaturanAbsensiForm()  # Form kosong
        context['is_new'] = True                   # Flag: buat baru (bukan edit)
        return context


    def post(self, request, *args, **kwargs):

        form = PengaturanAbsensiForm(request.POST)
        if form.is_valid():
            pengaturan = form.save()
            messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil dibuat!')
            return redirect('hr:pengaturan-absensi')

        # Form tidak valid - tampilkan ulang
        context = self.get_context_data()
        context['form'] = form
        messages.error(request, 'Terjadi kesalahan. Silakan periksa form.')
        return self.render_to_response(context)


@method_decorator(login_required, name='dispatch')
class PengaturanAbsensiUpdateView(TemplateView):
    """
    Form untuk mengedit pengaturan absensi yang sudah ada.

    URL: /hr/pengaturan-absensi/<pk>/edit/
    Template: hr/pengaturan_absensi_form.html
    """
    template_name = 'hr/pengaturan_absensi_form.html'

    def get_context_data(self, **kwargs):
        """Menyediakan form yang diisi dengan data pengaturan yang diedit."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        pengaturan = get_object_or_404(PengaturanAbsensi, pk=self.kwargs['pk'])  # Ambil berdasarkan pk
        context['form'] = PengaturanAbsensiForm(instance=pengaturan)  # Pre-fill form
        context['pengaturan'] = pengaturan
        context['is_new'] = False                   # Flag: edit (bukan buat baru)
        return context


    def post(self, request, *args, **kwargs):

        pengaturan = get_object_or_404(PengaturanAbsensi, pk=kwargs['pk'])
        form = PengaturanAbsensiForm(request.POST, instance=pengaturan)
        if form.is_valid():
            pengaturan = form.save()
            messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil diupdate!')
            return redirect('hr:pengaturan-absensi')

        # Form tidak valid - tampilkan ulang
        context = self.get_context_data()
        context['form'] = form
        messages.error(request, 'Terjadi kesalahan. Silakan periksa form.')
        return self.render_to_response(context)


@login_required
def pengaturan_absensi_delete(request, pk):
    """
    Hapus pengaturan absensi berdasarkan pk.

    URL: /hr/pengaturan-absensi/<pk>/delete/  (POST only)
    Redirect: /hr/pengaturan-absensi/
    """
    pengaturan = get_object_or_404(PengaturanAbsensi, pk=pk)

    if request.method == 'POST':
        nama = pengaturan.nama            # Simpan nama sebelum dihapus
        pengaturan.delete()               # Hapus dari database
        messages.success(request, f'Pengaturan "{nama}" berhasil dihapus!')
        return redirect('hr:pengaturan-absensi')

    # GET request → redirect tanpa aksi
    return redirect('hr:pengaturan-absensi')


@login_required
def pengaturan_absensi_activate(request, pk):
    """
    Aktifkan pengaturan absensi tertentu.

    URL: /hr/pengaturan-absensi/<pk>/activate/

    Catatan: Model PengaturanAbsensi.save() otomatis nonaktifkan
    semua pengaturan lain saat satu diaktifkan (single active).
    """
    pengaturan = get_object_or_404(PengaturanAbsensi, pk=pk)

    pengaturan.aktif = True
    pengaturan.save()  # save() akan otomatis nonaktifkan yang lain (single active)

    messages.success(request, f'Pengaturan "{pengaturan.nama}" berhasil diaktifkan!')
    return redirect('hr:pengaturan-absensi')
