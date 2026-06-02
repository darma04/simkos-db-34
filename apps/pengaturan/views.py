"""
==========================================================================
PENGATURAN VIEWS - Settings/Konfigurasi Sistem SIMKOS
==========================================================================
ProfilView        â†’ Edit profil pengguna
PerusahaanView    â†’ Pengaturan perusahaan + sistem
TemplateCetak     â†’ Konfigurasi cetak dokumen
ManajemenData     â†’ Statistik DB, backup, restore, reset
==========================================================================
"""
import os
import json
import shutil
import zipfile
import tempfile
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.conf import settings
from django.views.decorators.http import require_POST

from web_project import TemplateLayout
from .models import TemplateCetak, PengaturanPerusahaan, BackupHistory, MetodePembayaran
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from apps.core.permissions import has_permission
from django.db import transaction

User = get_user_model()


class ProfilView(ReadPermissionMixin, TemplateView):
    """Edit Profil User."""
    template_name = 'pengaturan/profil.html'
    permission_module = 'pengaturan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        user = self.request.user
        context['user'] = user
        if not hasattr(user, 'profile'):
            from auth.models import Profile
            Profile.objects.create(user=user, email=user.email)
        context['profile'] = user.profile
        return context


    def post(self, request, *args, **kwargs):
        """Proteksi POST: hanya user dengan permission edit yang bisa menyimpan."""
        if not request.user.is_superuser and not has_permission(request.user, 'update', 'pengaturan'):
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah profil.')
            return redirect('pengaturan:profil')
        user = request.user
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        user.save()
        profile = user.profile
        profile.phone = request.POST.get('phone', '')
        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
        if request.POST.get('remove_avatar') == '1':
            if profile.avatar:
                profile.avatar.delete(save=False)
                profile.avatar = None
        profile.save()
        messages.success(request, 'Profil berhasil diperbarui!')
        return redirect('pengaturan:profil')


class PerusahaanView(ReadPermissionMixin, UpdateView):
    """Pengaturan Perusahaan (singleton). ReadPermissionMixin agar user bisa VIEW form meskipun tanpa edit permission."""
    model = PengaturanPerusahaan
    template_name = 'pengaturan/perusahaan.html'
    permission_module = 'pengaturan'
    fields = [
        'nama_perusahaan', 'logo', 'alamat', 'telepon', 'email', 'website', 'pajak_default',
        'system_title', 'system_description', 'system_keywords', 'system_logo', 'system_favicon',
        'maintenance_mode', 'maintenance_message',
        'email_smtp_host', 'email_smtp_port', 'email_smtp_user', 'email_smtp_password', 'email_use_tls',
        'email_header', 'email_footer',
        'forgot_password_subject', 'forgot_password_message',
        'register_subject', 'register_message',
        'auth_image', 'auth_background_image', 'misc_image', 'misc_background_image'
    ]
    success_url = reverse_lazy('pengaturan:perusahaan')

    def get_object(self):
        return PengaturanPerusahaan.load()

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        return context

    def post(self, request, *args, **kwargs):
        """Proteksi POST: hanya user dengan permission edit yang bisa menyimpan."""
        if not request.user.is_superuser and not has_permission(request.user, 'update', 'pengaturan'):
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah pengaturan perusahaan.')
            return redirect('pengaturan:perusahaan')
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):

        from django.core.cache import cache
        cache.delete('ctx_pengaturan_perusahaan')
        messages.success(self.request, 'Pengaturan perusahaan berhasil diperbarui!')
        return super().form_valid(form)

    def form_invalid(self, form):
        # Tampilkan error validasi form ke user agar tidak gagal diam-diam
        for field, errors in form.errors.items():
            for error in errors:
                field_label = form.fields[field].label if field in form.fields else field
                messages.error(self.request, f'{field_label}: {error}')
        return super().form_invalid(form)


# â”€â”€ TEMPLATE CETAK CRUD â”€â”€

class TemplateCetakListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    model = TemplateCetak
    template_name = 'pengaturan/template_cetak_list.html'
    context_object_name = 'templates'
    ordering = ['jenis']
    permission_module = 'pengaturan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_template'] = TemplateCetak.objects.count()
        context['total_aktif'] = TemplateCetak.objects.filter(aktif=True).count()
        context['total_nonaktif'] = TemplateCetak.objects.filter(aktif=False).count()
        return context


class TemplateCetakUpdateView(ReadPermissionMixin, UpdateView):
    """ReadPermissionMixin agar user bisa VIEW form meskipun tanpa edit permission."""
    model = TemplateCetak
    template_name = 'pengaturan/template_cetak_form.html'
    permission_module = 'pengaturan'
    fields = [
        'nama', 'jenis', 'header_nama_perusahaan', 'header_alamat',
        'header_telepon', 'header_email', 'header_website',
        'footer_ucapan', 'footer_keterangan', 'footer_copyright',
        'signature_kiri_label', 'signature_kanan_label',
        'tampilkan_logo', 'tampilkan_website', 'aktif'
    ]
    success_url = reverse_lazy('pengaturan:template_cetak_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['action'] = 'Edit'
        return context

    def post(self, request, *args, **kwargs):
        """Proteksi POST: hanya user dengan permission edit yang bisa menyimpan."""
        if not request.user.is_superuser and not has_permission(request.user, 'update', 'pengaturan'):
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah template cetak.')
            return redirect('pengaturan:template_cetak_list')
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):

        messages.success(self.request, 'Template cetak berhasil diperbarui!')
        return super().form_valid(form)


class TemplateCetakCreateView(ReadPermissionMixin, CreateView):
    """ReadPermissionMixin agar user bisa VIEW form meskipun tanpa create permission."""
    model = TemplateCetak
    template_name = 'pengaturan/template_cetak_form.html'
    permission_module = 'pengaturan'
    fields = [
        'nama', 'jenis', 'header_nama_perusahaan', 'header_alamat',
        'header_telepon', 'header_email', 'header_website',
        'footer_ucapan', 'footer_keterangan', 'footer_copyright',
        'signature_kiri_label', 'signature_kanan_label',
        'tampilkan_logo', 'tampilkan_website', 'aktif'
    ]
    success_url = reverse_lazy('pengaturan:template_cetak_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['action'] = 'Tambah'
        return context

    def post(self, request, *args, **kwargs):
        """Proteksi POST: hanya user dengan permission create yang bisa menyimpan."""
        if not request.user.is_superuser and not has_permission(request.user, 'create', 'pengaturan'):
            messages.error(request, 'Anda tidak memiliki akses untuk menambah template cetak.')
            return redirect('pengaturan:template_cetak_list')
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):

        messages.success(self.request, 'Template cetak berhasil ditambahkan!')
        return super().form_valid(form)


# â”€â”€ MANAJEMEN DATA â”€â”€

class ManajemenDataView(ReadPermissionMixin, TemplateView):
    """Statistik database + riwayat backup."""
    template_name = 'pengaturan/manajemen_data.html'
    permission_module = 'pengaturan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        try:
            from apps.properti.models import Properti, TipeKamar, Kamar
            from apps.penyewa.models import Penyewa
            from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa
            from apps.biaya.models import KategoriBiaya, TransaksiBiaya
            from apps.activity_log.models import UserActivity
            from apps.automation.models import LogNotifikasi

            # Coba ambil data HR jika ada
            try:
                from apps.hr.models import Karyawan, Departemen
                karyawan_count = Karyawan.objects.count()
                departemen_count = Departemen.objects.count()
            except Exception:
                karyawan_count = 0
                departemen_count = 0

            context['stats'] = {
                'properti': Properti.objects.count(),
                'tipe_kamar': TipeKamar.objects.count(),
                'kamar': Kamar.objects.count(),
                'penyewa': Penyewa.objects.count(),
                'kategori_biaya': KategoriBiaya.objects.count(),
                'kontrak_sewa': KontrakSewa.objects.count(),
                'tagihan_sewa': TagihanSewa.objects.count(),
                'pembayaran_sewa': PembayaranSewa.objects.count(),
                'biaya': TransaksiBiaya.objects.count(),
                'karyawan': karyawan_count,
                'departemen': departemen_count,
                'metode_pembayaran': MetodePembayaran.objects.count(),
                'user': User.objects.count(),
                'activity_log': UserActivity.objects.count(),
                'log_notifikasi': LogNotifikasi.objects.count(),
            }
        except Exception:
            context['stats'] = {}

        context['total_transaksi'] = sum(
            context.get('stats', {}).get(k, 0)
            for k in ['kontrak_sewa', 'tagihan_sewa', 'pembayaran_sewa', 'biaya']
        )
        context['total_master'] = sum(
            context.get('stats', {}).get(k, 0)
            for k in ['properti', 'tipe_kamar', 'kamar', 'penyewa']
        )

        context['riwayat_list'] = BackupHistory.objects.select_related('dibuat_oleh').all()[:50]

        db_path = settings.BASE_DIR / 'db.sqlite3'
        if db_path.exists():
            db_size = os.path.getsize(db_path)
            if db_size < 1024:
                context['db_size'] = f"{db_size} B"
            elif db_size < 1024 * 1024:
                context['db_size'] = f"{db_size / 1024:.1f} KB"
            else:
                context['db_size'] = f"{db_size / (1024 * 1024):.1f} MB"
            context['db_size_bytes'] = db_size
        else:
            context['db_size'] = 'N/A'
            context['db_size_bytes'] = 0

        last_backup = BackupHistory.objects.filter(jenis='backup', status='sukses').first()
        context['last_backup'] = last_backup
        return context


@login_required
@require_POST
def backup_data(request):
    """Export seluruh database ke file ZIP berisi data JSON + folder media (gambar)."""
    if not request.user.is_superuser and not has_permission(request.user, 'create', 'pengaturan'):
        messages.error(request, 'Anda tidak memiliki izin untuk backup data.')
        return redirect('pengaturan:manajemen_data')

    tmp_dir = None
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nama_file = f"backup_{timestamp}.zip"

        # === 1. DUMP DATABASE KE JSON ===
        from io import StringIO
        output = StringIO()
        call_command('dumpdata', '--all', '--natural-foreign',
                    '--exclude=contenttypes', '--exclude=auth.permission',
                    '--exclude=admin.logentry', '--exclude=sessions.session',
                    '--indent=2', stdout=output)
        json_data = output.getvalue()

        # === 2. BUAT FILE ZIP BERISI data.json + media/ ===
        tmp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(tmp_dir, nama_file)
        media_root = str(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') else os.path.join(str(settings.BASE_DIR), 'media')

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Tambahkan data.json
            zf.writestr('data.json', json_data)

            # Tambahkan seluruh isi folder media/ jika ada
            if os.path.exists(media_root):
                for root, dirs, files in os.walk(media_root):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('media', os.path.relpath(file_path, media_root))
                        try:
                            zf.write(file_path, arcname)
                        except (PermissionError, OSError):
                            pass

        file_size = os.path.getsize(zip_path)

        # Hitung jumlah file media
        media_count = 0
        if os.path.exists(media_root):
            for _, _, files in os.walk(media_root):
                media_count += len(files)

        BackupHistory.objects.create(
            nama_file=nama_file, ukuran_file=file_size, jenis='backup',
            status='sukses',
            catatan=f"Backup database + {media_count} file media ({file_size / 1024:.1f} KB)",
            dibuat_oleh=request.user)

        with open(zip_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{nama_file}"'
        return response
    except Exception as e:
        BackupHistory.objects.create(
            nama_file=f"backup_gagal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            ukuran_file=0, jenis='backup', status='gagal',
            catatan=f"Error: {str(e)}", dibuat_oleh=request.user)
        messages.error(request, f'Backup gagal: {str(e)}')
        return redirect('pengaturan:manajemen_data')
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass


@login_required
@require_POST
def restore_data(request):
    """
    Restore data dari file backup ZIP (data.json + media/) atau JSON (backward compatible).
    Strategi:
    1. SIMPAN user admin yang sedang login â†’ agar session tetap valid
    2. Hapus SEMUA data per-model (child dulu, parent terakhir)
    3. Matikan FK constraints saat loaddata â†’ cegah FOREIGN KEY error
    4. Load data dari backup (fallback: item-by-item jika gagal)
    5. Restore file media dari ZIP (jika ada)
    6. Pastikan admin tetap punya profile setelah restore
    7. VACUUM database
    """
    if not request.user.is_superuser and not has_permission(request.user, 'create', 'pengaturan'):
        messages.error(request, 'Anda tidak memiliki izin untuk restore data.')
        return redirect('pengaturan:manajemen_data')

    if 'backup_file' not in request.FILES:
        messages.error(request, 'File backup tidak ditemukan. Pilih file .zip atau .json untuk restore.')
        return redirect('pengaturan:manajemen_data')

    backup_file = request.FILES['backup_file']
    if not backup_file.name.endswith('.json') and not backup_file.name.endswith('.zip'):
        messages.error(request, 'Format file tidak valid. Hanya file .zip atau .json yang diperbolehkan.')
        return redirect('pengaturan:manajemen_data')

    tmp_path = None
    tmp_extract_dir = None
    is_zip = backup_file.name.endswith('.zip')

    try:
        import logging
        logger = logging.getLogger(__name__)
        from django.db import connection
        from io import StringIO

        file_size = backup_file.size
        media_restored = 0

        # === LANGKAH 0: EKSTRAK JSON DARI ZIP ATAU BACA LANGSUNG ===
        if is_zip:
            tmp_extract_dir = tempfile.mkdtemp()
            tmp_zip_path = os.path.join(tmp_extract_dir, 'backup.zip')
            with open(tmp_zip_path, 'wb') as f:
                for chunk in backup_file.chunks():
                    f.write(chunk)

            if not zipfile.is_zipfile(tmp_zip_path):
                messages.error(request, 'File ZIP tidak valid atau rusak.')
                return redirect('pengaturan:manajemen_data')

            with zipfile.ZipFile(tmp_zip_path, 'r') as zf:
                zf.extractall(tmp_extract_dir)

            json_path = os.path.join(tmp_extract_dir, 'data.json')
            if not os.path.exists(json_path):
                messages.error(request, 'File ZIP tidak mengandung data.json. Format backup tidak valid.')
                return redirect('pengaturan:manajemen_data')

            with open(json_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info("[RESTORE] File ZIP diekstrak. Membaca data.json...")
        else:
            content = backup_file.read().decode('utf-8')
            logger.info("[RESTORE] File JSON langsung dibaca.")

        # Validasi JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            messages.error(request, 'File JSON tidak valid atau rusak.')
            return redirect('pengaturan:manajemen_data')

        if not isinstance(data, list):
            messages.error(request, 'Format file backup tidak valid. File harus berisi data dumpdata Django.')
            return redirect('pengaturan:manajemen_data')

        if len(data) == 0:
            messages.error(request, 'File backup kosong, tidak ada data untuk di-restore.')
            return redirect('pengaturan:manajemen_data')

        excluded_models = {'contenttypes.contenttype', 'auth.permission',
                            'admin.logentry', 'sessions.session'}
        filtered_data = [item for item in data if item.get('model') not in excluded_models]

        logger.info("[RESTORE] File: %s, ukuran: %d bytes, total objek: %d, setelah filter: %d",
                    backup_file.name, file_size, len(data), len(filtered_data))

        current_user = request.user
        current_user_pk = current_user.pk
        current_username = current_user.username

        # Filter backup data: skip admin yang sedang login (sudah di-preserve)
        # Ini mencegah duplikat User & Profile yang di-preserve
        safe_data = []
        for item in filtered_data:
            model = item.get('model', '')
            pk = item.get('pk')
            fields = item.get('fields', {})
            # Skip user yang sama dengan admin saat ini
            if model == 'auth.user' and pk == current_user_pk:
                continue
            # Skip Profile milik admin saat ini
            if model == 'auth.profile' and fields.get('user') == current_user_pk:
                continue
            safe_data.append(item)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(safe_data, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name

        # === LANGKAH 1: HAPUS SEMUA DATA LAMA ===
        logger.info("[RESTORE] Langkah 1: Menghapus semua data lama...")

        from apps.sewa.models import PembayaranSewa, TagihanSewa, KontrakSewa
        from apps.biaya.models import TransaksiBiaya, KategoriBiaya
        from apps.activity_log.models import UserActivity
        from apps.automation.models import LogNotifikasi
        from apps.properti.models import Properti, TipeKamar, Kamar
        from apps.penyewa.models import Penyewa
        from auth.models import Profile

        PembayaranSewa.objects.all().delete()
        TagihanSewa.objects.all().delete()
        KontrakSewa.objects.all().delete()
        TransaksiBiaya.objects.all().delete()
        KategoriBiaya.objects.all().delete()
        Penyewa.objects.all().delete()
        Kamar.objects.all().delete()
        TipeKamar.objects.all().delete()
        Properti.objects.all().delete()
        MetodePembayaran.objects.all().delete()

        try:
            from apps.hr.models import Karyawan, Departemen
            Karyawan.objects.all().delete()
            Departemen.objects.all().delete()
        except Exception:
            pass

        UserActivity.objects.all().delete()
        LogNotifikasi.objects.all().delete()
        TemplateCetak.objects.all().delete()
        BackupHistory.objects.all().delete()

        Profile.objects.all().delete()
        User.objects.exclude(pk=current_user_pk).delete()
        PengaturanPerusahaan.objects.all().delete()

        logger.info("[RESTORE] Langkah 1 selesai: Semua data lama berhasil dihapus.")

        # === LANGKAH 2: LOAD DATA DARI BACKUP ===
        logger.info("[RESTORE] Langkah 2: Memuat data dari backup...")
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF")

        load_success = False
        load_error_msg = ""

        # PENTING: Disconnect signal post_save User → auto-create Profile
        from django.db.models.signals import post_save
        from auth.models import Profile as ProfileSignal
        post_save.disconnect(ProfileSignal.create_profile, sender=User)
        logger.info("[RESTORE] Signal create_profile di-disconnect sementara.")

        try:
            stderr_output = StringIO()
            call_command('loaddata', tmp_path, '--ignorenonexistent', verbosity=0, stderr=stderr_output)
            load_success = True
            logger.info("[RESTORE] Langkah 2 sukses: loaddata berhasil.")
        except Exception as load_err:
            load_error_msg = str(load_err)
            logger.error("[RESTORE] Loaddata gagal (percobaan 1): %s", load_err)

        if not load_success:
            logger.info("[RESTORE] Percobaan 2: load item per item")
            success_count = 0
            error_count = 0
            error_models = []

            for item in filtered_data:
                single_tmp = None
                try:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as stmp:
                        json.dump([item], stmp, ensure_ascii=False)
                        single_tmp = stmp.name
                    call_command('loaddata', single_tmp, '--ignorenonexistent', verbosity=0, stderr=StringIO())
                    success_count += 1
                except Exception as item_err:
                    error_count += 1
                    model_name = item.get('model', 'unknown')
                    if model_name not in error_models:
                        error_models.append(model_name)
                        logger.warning("[RESTORE] Gagal memuat model %s: %s", model_name, str(item_err)[:100])
                finally:
                    if single_tmp and os.path.exists(single_tmp):
                        try:
                            os.unlink(single_tmp)
                        except OSError:
                            pass

            if success_count > 0:
                load_success = True
                load_error_msg = f"Dimuat {success_count} objek, {error_count} gagal"
                if error_models:
                    load_error_msg += f" (model gagal: {', '.join(error_models[:5])})"

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = ON")

        # RECONNECT signal create_profile
        post_save.connect(ProfileSignal.create_profile, sender=User)
        logger.info("[RESTORE] Signal create_profile di-reconnect.")

        # === LANGKAH 3: RESTORE FILE MEDIA DARI ZIP ===
        if is_zip and tmp_extract_dir:
            media_source = os.path.join(tmp_extract_dir, 'media')
            media_root = str(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') else os.path.join(str(settings.BASE_DIR), 'media')

            if os.path.exists(media_source):
                logger.info("[RESTORE] Langkah 3: Merestore file media...")

                if os.path.exists(media_root):
                    for item_name in os.listdir(media_root):
                        item_path = os.path.join(media_root, item_name)
                        try:
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            else:
                                os.unlink(item_path)
                        except (PermissionError, OSError) as e:
                            logger.warning("[RESTORE] Gagal hapus media lama %s: %s", item_path, e)
                else:
                    os.makedirs(media_root, exist_ok=True)

                for item_name in os.listdir(media_source):
                    src = os.path.join(media_source, item_name)
                    dst = os.path.join(media_root, item_name)
                    try:
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    except Exception as e:
                        logger.warning("[RESTORE] Gagal copy media %s: %s", item_name, e)

                media_file_count = 0
                for _, _, files in os.walk(media_root):
                    media_file_count += len(files)
                media_restored = media_file_count
                logger.info("[RESTORE] Langkah 3 selesai: %d file media di-restore.", media_restored)

        # === LANGKAH 4: PASTIKAN ADMIN TETAP PUNYA PROFILE ===
        try:
            if not Profile.objects.filter(user=current_user).exists():
                Profile.objects.create(
                    user=current_user,
                    role='pemilik',
                    email=current_user.email or ''
                )
                logger.info("[RESTORE] Profile admin '%s' dibuat ulang.", current_username)
        except Exception as profile_err:
            logger.warning("[RESTORE] Gagal membuat profile admin: %s", profile_err)

        try:
            current_user.refresh_from_db()
            if not current_user.is_superuser:
                current_user.is_superuser = True
                current_user.is_staff = True
                current_user.save(update_fields=['is_superuser', 'is_staff'])
        except Exception:
            pass

        try:
            from django.contrib.auth import login
            login(request, current_user)
        except Exception:
            pass

        # === LANGKAH 5: VACUUM DATABASE ===
        try:
            with connection.cursor() as cursor:
                cursor.execute("VACUUM")
        except Exception:
            pass

        if load_success:
            media_info = f", {media_restored} file media" if media_restored > 0 else ""
            try:
                BackupHistory.objects.create(
                    nama_file=backup_file.name, ukuran_file=file_size, jenis='restore',
                    status='sukses',
                    catatan=f"Restore dari {backup_file.name} ({file_size / 1024:.1f} KB) - {len(filtered_data)} objek{media_info}. {load_error_msg}",
                    dibuat_oleh=current_user)
            except Exception:
                pass
            messages.success(request, f'Data berhasil di-restore dari "{backup_file.name}"! ({len(filtered_data)} objek dimuat{media_info}) {load_error_msg}')
        else:
            raise Exception(f"Semua metode restore gagal: {load_error_msg}")

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("[RESTORE] Error: %s", e, exc_info=True)
        try:
            BackupHistory.objects.create(
                nama_file=backup_file.name, ukuran_file=0, jenis='restore',
                status='gagal', catatan=f"Error: {str(e)}", dibuat_oleh=request.user)
        except Exception:
            pass
        messages.error(request, f'Restore gagal: {str(e)}')
    finally:
        try:
            from django.db import connection as conn
            with conn.cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        # Selalu reconnect signal create_profile (safety net)
        try:
            from django.db.models.signals import post_save as _ps
            from auth.models import Profile as _P
            _ps.connect(_P.create_profile, sender=User)
        except Exception:
            pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if tmp_extract_dir and os.path.exists(tmp_extract_dir):
            try:
                shutil.rmtree(tmp_extract_dir)
            except OSError:
                pass
    return redirect('pengaturan:manajemen_data')

@login_required
@require_POST
def reset_data(request):
    """Reset SEMUA data SIMKOS - hapus seluruh isi database kecuali akun superuser."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'pengaturan'):
        return JsonResponse({'success': False, 'message': 'Tidak memiliki izin.'}, status=403)

    konfirmasi = request.POST.get('konfirmasi', '')
    if konfirmasi != 'HAPUS SEMUA':
        messages.error(request, 'Konfirmasi tidak valid. Ketik "HAPUS SEMUA" untuk melanjutkan.')
        return redirect('pengaturan:manajemen_data')

    try:
        from django.db import connection
        from apps.sewa.models import PembayaranSewa, TagihanSewa, KontrakSewa
        from apps.biaya.models import TransaksiBiaya, KategoriBiaya
        from apps.activity_log.models import UserActivity
        from apps.automation.models import LogNotifikasi
        from apps.properti.models import Properti, TipeKamar, Kamar
        from apps.penyewa.models import Penyewa
        from auth.models import Profile
        from apps.core.models import RolePermission

        # Simpan info user yang sedang login
        current_user = request.user
        current_user_pk = current_user.pk

        counts = {}

        # Transaksi
        counts['Pembayaran Sewa'] = PembayaranSewa.objects.count()
        counts['Tagihan Sewa'] = TagihanSewa.objects.count()
        counts['Kontrak Sewa'] = KontrakSewa.objects.count()
        counts['Transaksi Biaya'] = TransaksiBiaya.objects.count()

        # Master Data
        counts['Penyewa'] = Penyewa.objects.count()
        counts['Kamar'] = Kamar.objects.count()
        counts['Tipe Kamar'] = TipeKamar.objects.count()
        counts['Properti'] = Properti.objects.count()
        counts['Kategori Biaya'] = KategoriBiaya.objects.count()

        # Metode Pembayaran
        counts['Metode Pembayaran'] = MetodePembayaran.objects.count()

        # HR
        try:
            from apps.hr.models import Karyawan, Departemen
            counts['Karyawan'] = Karyawan.objects.count()
            counts['Departemen'] = Departemen.objects.count()
        except Exception:
            pass

        # Log & Riwayat
        counts['Activity Log'] = UserActivity.objects.count()
        counts['Log Notifikasi'] = LogNotifikasi.objects.count()
        counts['Riwayat Backup'] = BackupHistory.objects.count()

        # User & Permissions
        counts['User lain'] = User.objects.exclude(pk=current_user_pk).count()
        counts['Role Permission'] = RolePermission.objects.count()

        total_deleted = sum(counts.values())

        # ===== HAPUS SEMUA DATA (urutan: child dulu, lalu parent) =====

        # 1. Hapus transaksi
        PembayaranSewa.objects.all().delete()
        TagihanSewa.objects.all().delete()
        KontrakSewa.objects.all().delete()
        TransaksiBiaya.objects.all().delete()

        # 2. Hapus master data
        Penyewa.objects.all().delete()
        Kamar.objects.all().delete()
        TipeKamar.objects.all().delete()
        Properti.objects.all().delete()
        KategoriBiaya.objects.all().delete()

        # 3. Hapus metode pembayaran
        MetodePembayaran.objects.all().delete()

        # 4. Hapus HR data
        try:
            from apps.hr.models import Karyawan, Departemen
            Karyawan.objects.all().delete()
            Departemen.objects.all().delete()
        except Exception:
            pass

        # 5. Hapus log & notifikasi
        UserActivity.objects.all().delete()
        LogNotifikasi.objects.all().delete()
        BackupHistory.objects.all().delete()

        # 6. Hapus pengaturan
        try:
            TemplateCetak.objects.all().delete()
        except Exception:
            pass
        RolePermission.objects.all().delete()

        # 7. Hapus user lain & profile (PROTEKSI superuser)
        Profile.objects.exclude(user_id=current_user_pk).delete()
        User.objects.exclude(pk=current_user_pk).delete()

        # Catatan: Pengaturan Perusahaan DIPERTAHANKAN sesuai keterangan di template

        # 8. Hapus file media (gambar, foto, bukti, dll) KECUALI folder system/ untuk logo default
        media_deleted = 0
        media_root = str(settings.MEDIA_ROOT) if hasattr(settings, 'MEDIA_ROOT') else os.path.join(str(settings.BASE_DIR), 'media')
        if os.path.exists(media_root):
            protected_folders = {'system'}
            for item_name in os.listdir(media_root):
                if item_name in protected_folders:
                    continue
                item_path = os.path.join(media_root, item_name)
                try:
                    if os.path.isdir(item_path):
                        for _, _, files in os.walk(item_path):
                            media_deleted += len(files)
                        shutil.rmtree(item_path)
                    else:
                        media_deleted += 1
                        os.unlink(item_path)
                except (PermissionError, OSError):
                    pass

        detail_parts = [f"{name}: {count}" for name, count in counts.items() if count > 0]
        detail_str = ", ".join(detail_parts) if detail_parts else "Tidak ada data"
        media_info = f", {media_deleted} file media dihapus" if media_deleted > 0 else ""

        # Buat record riwayat SETELAH menghapus semua
        BackupHistory.objects.create(
            nama_file='reset_semua_data', ukuran_file=0, jenis='reset', status='sukses',
            catatan=f"Hapus SEMUA data ({total_deleted} record{media_info}). Detail: {detail_str}",
            dibuat_oleh=current_user)
        messages.success(request, f'Semua data berhasil dihapus! {total_deleted} record{media_info}. Hanya akun admin Anda yang dipertahankan.')

        # VACUUM database agar ukuran file SQLite langsung berkurang
        try:
            with connection.cursor() as cursor:
                cursor.execute('VACUUM')
        except Exception:
            pass

    except Exception as e:
        try:
            BackupHistory.objects.create(
                nama_file='reset_semua_data', ukuran_file=0, jenis='reset', status='gagal',
                catatan=f"Error: {str(e)}", dibuat_oleh=request.user)
        except Exception:
            pass
        messages.error(request, f'Reset gagal: {str(e)}')
    return redirect('pengaturan:manajemen_data')



@login_required
@require_POST
def hapus_riwayat_backup(request, pk):
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'pengaturan'):
        return JsonResponse({'success': False, 'message': 'Tidak memiliki izin.'}, status=403)
    riwayat = get_object_or_404(BackupHistory, pk=pk)
    riwayat.delete()
    messages.success(request, 'Riwayat berhasil dihapus.')
    return redirect('pengaturan:manajemen_data')


@login_required
@require_POST
def bersihkan_log_aktivitas(request):
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'pengaturan'):
        messages.error(request, 'Tidak memiliki izin.')
        return redirect('pengaturan:manajemen_data')
    from apps.activity_log.models import UserActivity
    jumlah = UserActivity.objects.count()
    UserActivity.objects.all().delete()
    BackupHistory.objects.create(jenis='reset', nama_file='-', ukuran_file=0, status='sukses',
                                catatan=f'Membersihkan {jumlah} log aktivitas', dibuat_oleh=request.user)
    messages.success(request, f'Berhasil membersihkan {jumlah} log aktivitas.')
    # VACUUM agar ukuran DB langsung berkurang
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('VACUUM')
    except Exception:
        pass
    return redirect('pengaturan:manajemen_data')


@login_required
@require_POST
def bersihkan_log_notifikasi(request):
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'pengaturan'):
        messages.error(request, 'Tidak memiliki izin.')
        return redirect('pengaturan:manajemen_data')
    from apps.automation.models import LogNotifikasi
    jumlah = LogNotifikasi.objects.count()
    LogNotifikasi.objects.all().delete()
    BackupHistory.objects.create(jenis='reset', nama_file='-', ukuran_file=0, status='sukses',
                                catatan=f'Membersihkan {jumlah} log notifikasi', dibuat_oleh=request.user)
    messages.success(request, f'Berhasil membersihkan {jumlah} log notifikasi.')
    # VACUUM agar ukuran DB langsung berkurang
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('VACUUM')
    except Exception:
        pass
    return redirect('pengaturan:manajemen_data')


@login_required
def db_stats_api(request):
    """API endpoint: ukuran database dan statistik real-time (JSON)."""
    data = {'db_size': 'N/A', 'db_size_bytes': 0, 'stats': {}, 'total_master': 0, 'total_transaksi': 0}

    # Ukuran database
    db_path = settings.BASE_DIR / 'db.sqlite3'
    if db_path.exists():
        db_size = os.path.getsize(db_path)
        if db_size < 1024:
            data['db_size'] = f"{db_size} B"
        elif db_size < 1024 * 1024:
            data['db_size'] = f"{db_size / 1024:.1f} KB"
        else:
            data['db_size'] = f"{db_size / (1024 * 1024):.1f} MB"
        data['db_size_bytes'] = db_size

    # Statistik model
    try:
        from apps.properti.models import Properti, TipeKamar, Kamar
        from apps.penyewa.models import Penyewa
        from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa
        from apps.biaya.models import KategoriBiaya, TransaksiBiaya
        from apps.activity_log.models import UserActivity
        from apps.automation.models import LogNotifikasi

        try:
            from apps.hr.models import Karyawan, Departemen
            karyawan_count = Karyawan.objects.count()
            departemen_count = Departemen.objects.count()
        except Exception:
            karyawan_count = 0
            departemen_count = 0

        stats = {
            'properti': Properti.objects.count(),
            'tipe_kamar': TipeKamar.objects.count(),
            'kamar': Kamar.objects.count(),
            'penyewa': Penyewa.objects.count(),
            'kategori_biaya': KategoriBiaya.objects.count(),
            'kontrak_sewa': KontrakSewa.objects.count(),
            'tagihan_sewa': TagihanSewa.objects.count(),
            'pembayaran_sewa': PembayaranSewa.objects.count(),
            'biaya': TransaksiBiaya.objects.count(),
            'karyawan': karyawan_count,
            'departemen': departemen_count,
            'metode_pembayaran': MetodePembayaran.objects.count(),
            'user': User.objects.count(),
            'activity_log': UserActivity.objects.count(),
            'log_notifikasi': LogNotifikasi.objects.count(),
        }
        data['stats'] = stats
        data['total_master'] = sum(stats.get(k, 0) for k in ['properti', 'tipe_kamar', 'kamar', 'penyewa'])
        data['total_transaksi'] = sum(stats.get(k, 0) for k in ['kontrak_sewa', 'tagihan_sewa', 'pembayaran_sewa', 'biaya'])
    except Exception:
        pass

    return JsonResponse(data)


# â”€â”€ METODE PEMBAYARAN CRUD â”€â”€

class MetodePembayaranListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """Daftar semua metode pembayaran."""
    model = MetodePembayaran
    template_name = 'pengaturan/metode_pembayaran_list.html'
    context_object_name = 'metode_list'
    ordering = ['nama']
    permission_module = 'pengaturan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        # Hitung ringkasan
        total_saldo = sum(m.saldo_terhitung for m in qs)
        total_pendapatan = sum(m.total_pendapatan for m in qs)
        total_pengeluaran = sum(m.total_pengeluaran for m in qs)
        total_transaksi = sum(m.total_transaksi_count for m in qs)
        context['ringkasan_saldo'] = total_saldo
        context['ringkasan_pendapatan'] = total_pendapatan
        context['ringkasan_pengeluaran'] = total_pengeluaran
        context['ringkasan_transaksi'] = total_transaksi
        return context


class MetodePembayaranCreateView(ReadPermissionMixin, CreateView):
    """Tambah metode pembayaran baru. ReadPermissionMixin agar user bisa VIEW form."""
    model = MetodePembayaran
    template_name = 'pengaturan/metode_pembayaran_form.html'
    permission_module = 'pengaturan'
    fields = ['nama', 'kode', 'nama_pemilik', 'deskripsi', 'gambar', 'saldo', 'aktif']
    success_url = reverse_lazy('pengaturan:metode_pembayaran_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['action'] = 'Tambah'
        return context

    def post(self, request, *args, **kwargs):
        """Proteksi POST: hanya user dengan permission create yang bisa menyimpan."""
        if not request.user.is_superuser and not has_permission(request.user, 'create', 'pengaturan'):
            messages.error(request, 'Anda tidak memiliki akses untuk menambah metode pembayaran.')
            return redirect('pengaturan:metode_pembayaran_list')
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Metode pembayaran berhasil ditambahkan!')
        return super().form_valid(form)


class MetodePembayaranUpdateView(ReadPermissionMixin, UpdateView):
    """Edit metode pembayaran. ReadPermissionMixin agar user bisa VIEW form."""
    model = MetodePembayaran
    template_name = 'pengaturan/metode_pembayaran_form.html'
    permission_module = 'pengaturan'
    fields = ['nama', 'kode', 'nama_pemilik', 'deskripsi', 'gambar', 'saldo', 'aktif']
    success_url = reverse_lazy('pengaturan:metode_pembayaran_list')

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['action'] = 'Edit'
        return context

    def post(self, request, *args, **kwargs):
        """Proteksi POST: hanya user dengan permission edit yang bisa menyimpan."""
        if not request.user.is_superuser and not has_permission(request.user, 'update', 'pengaturan'):
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah metode pembayaran.')
            return redirect('pengaturan:metode_pembayaran_list')
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, 'Metode pembayaran berhasil diperbarui!')
        return super().form_valid(form)


class MetodePembayaranDetailView(ReadPermissionMixin, DetailView):
    """Detail metode pembayaran."""
    model = MetodePembayaran
    template_name = 'pengaturan/metode_pembayaran_detail.html'
    context_object_name = 'metode'
    permission_module = 'pengaturan'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        from django.db.models import Sum, Max
        from apps.sewa.models import PembayaranSewa
        from apps.biaya.models import TransaksiBiaya

        metode = self.object

        # Riwayat transaksi terbaru
        pembayaran_qs = PembayaranSewa.objects.filter(metode_bayar=metode.kode)
        biaya_qs = TransaksiBiaya.objects.filter(metode_pembayaran=metode.kode, status='approved')

        context['pembayaran_list'] = pembayaran_qs.order_by('-tanggal_bayar')[:10]
        context['biaya_list'] = biaya_qs.order_by('-tanggal')[:10]

        # Data keuangan
        total_pendapatan = pembayaran_qs.aggregate(t=Sum('jumlah_bayar'))['t'] or 0
        total_pengeluaran = biaya_qs.aggregate(t=Sum('jumlah'))['t'] or 0
        context['total_pendapatan'] = total_pendapatan
        context['total_pengeluaran'] = total_pengeluaran
        context['saldo_terhitung'] = metode.saldo + total_pendapatan - total_pengeluaran

        # Pendapatan/pengeluaran tertinggi
        context['pendapatan_tertinggi'] = pembayaran_qs.aggregate(t=Max('jumlah_bayar'))['t'] or 0
        context['pengeluaran_tertinggi'] = biaya_qs.aggregate(t=Max('jumlah'))['t'] or 0

        # Total transaksi
        context['total_transaksi'] = pembayaran_qs.count() + biaya_qs.count()

        # Transaksi lunas (pembayaran yang tagihannya lunas)
        context['transaksi_lunas'] = pembayaran_qs.filter(tagihan__status='lunas').count()

        return context


@login_required
@require_POST
def metode_pembayaran_delete(request, pk):
    """Hapus metode pembayaran via AJAX."""
    if not request.user.is_superuser and not has_permission(request.user, 'delete', 'pengaturan'):
        return JsonResponse({'success': False, 'message': 'Tidak memiliki izin.'}, status=403)
    try:
        metode = MetodePembayaran.objects.get(pk=pk)
        # Cek apakah ada transaksi yang menggunakan metode ini
        from apps.sewa.models import PembayaranSewa
        from apps.biaya.models import TransaksiBiaya
        count_pembayaran = PembayaranSewa.objects.filter(metode_bayar=metode.kode).count()
        count_biaya = TransaksiBiaya.objects.filter(metode_pembayaran=metode.kode).count()
        if count_pembayaran > 0 or count_biaya > 0:
            detail = []
            if count_pembayaran > 0:
                detail.append(f"{count_pembayaran} pembayaran sewa")
            if count_biaya > 0:
                detail.append(f"{count_biaya} transaksi biaya")
            return JsonResponse({
                'success': False,
                'message': f'Tidak dapat menghapus metode "{metode.nama}" karena masih digunakan oleh {", ".join(detail)}. '
                            f'Ubah status menjadi nonaktif sebagai alternatif.'
            })
        metode.delete()
        return JsonResponse({'success': True, 'message': f'Metode pembayaran "{metode.nama}" berhasil dihapus.'})
    except MetodePembayaran.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Metode pembayaran tidak ditemukan.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Gagal menghapus: {str(e)}'}, status=500)

