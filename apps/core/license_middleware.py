"""
==========================================================================
 LICENSE MIDDLEWARE — Middleware Pengecekan Lisensi Otomatis
==========================================================================
 Middleware ini adalah "jantung" perlindungan software terhadap pembajakan.

 Cara kerja:
 1. Setiap request HTTP masuk, middleware mengecek status lisensi.
 2. Jika belum ada license_key → redirect ke halaman aktivasi.
 3. Jika sudah ada license_key:
    a. Cek cache lokal (24 jam). Jika masih valid → lanjut.
    b. Jika cache expired → ping CLS API /api/v1/license/validate/
    c. Jika CLS bilang valid → update cache 24 jam, lanjut.
    d. Jika CLS bilang invalid → blokir akses, tampilkan pesan.
    e. Jika CLS tidak bisa dihubungi (offline) → toleransi pakai cache lama.

 Koneksi:
 - apps/core/license_models.py → LicenseConfig (data lisensi lokal)
 - apps/core/license_views.py → View untuk halaman aktivasi
 - config/settings.py → LICENSE_SERVER_URL, PRODUCT_CODE
==========================================================================
"""
import json
import logging
import urllib.request
import urllib.error
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.conf import settings

logger = logging.getLogger(__name__)


class LicenseMiddleware:
    """
    Django Middleware untuk memverifikasi lisensi software.

    Skip URL yang dikecualikan:
    - Halaman login dan logout
    - Halaman aktivasi lisensi
    - Static files dan media files
    - Admin panel (opsional)
    """

    # URL yang tidak perlu pengecekan lisensi
    EXEMPT_PATHS = [
        '/login/',
        '/logout/',
        '/license/',           # Halaman aktivasi
        '/static/',
        '/media/',
        '/admin/',
        '/favicon.ico',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip untuk URL yang dikecualikan
        path = request.path
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return self.get_response(request)

        # ============================================================
        # PENGECEKAN LISENSI HARUS TERJADI SEBELUM LOGIN!
        # Pembeli baru yang pertama kali akses aplikasi WAJIB melihat
        # halaman aktivasi lisensi terlebih dahulu, BUKAN halaman login.
        # ============================================================

        # Import model di sini (lazy import untuk menghindari circular import)
        from apps.core.license_models import LicenseConfig, generate_hardware_id

        try:
            config = LicenseConfig.get_config()
        except Exception:
            # Database belum siap (migration belum jalan) — skip
            return self.get_response(request)

        # Jika belum ada license key → redirect ke halaman aktivasi
        # Ini berlaku untuk SEMUA pengunjung (login maupun belum login)
        if not config.license_key or not config.is_activated:
            return HttpResponseRedirect(reverse('license_activation'))

        # Cek cache validasi (24 jam)
        if config.is_cache_valid() and config.validation_cache:
            # Cache masih valid dan lisensi valid → lanjut
            return self.get_response(request)

        # Untuk pengecekan berkala ke CLS, hanya dilakukan jika user sudah login
        # (user yang belum login akan ditangani oleh auth middleware setelah ini)
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return self.get_response(request)

        # Cache expired atau belum ada → ping CLS untuk validasi ulang
        hardware_id = config.hardware_id or generate_hardware_id()
        cls_url = getattr(settings, 'LICENSE_SERVER_URL', config.cls_server_url)
        product_code = getattr(settings, 'PRODUCT_CODE', 'SIMKOS')

        is_valid = self._validate_with_cls(config, hardware_id, cls_url)

        if is_valid:
            return self.get_response(request)

        # Jika validasi gagal TAPI cache lama masih ada (offline tolerance)
        if config.validation_cache and config.last_validated:
            logger.warning("CLS tidak bisa dihubungi, menggunakan cache lama.")
            return self.get_response(request)

        # Benar-benar invalid → redirect ke halaman aktivasi dengan pesan error
        return HttpResponseRedirect(
            reverse('license_activation') + '?error=invalid'
        )

    def _validate_with_cls(self, config, hardware_id, cls_url):
        """
        Mengirim request validasi ke Central License Server.

        Returns:
            bool: True jika lisensi valid, False jika tidak.
        """
        validate_url = f"{cls_url.rstrip('/')}/api/v1/license/validate/"

        payload = json.dumps({
            "license_key": config.license_key,
            "hardware_id": hardware_id,
        }).encode('utf-8')

        req = urllib.request.Request(
            validate_url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                if data.get('is_valid', False):
                    # Validasi berhasil — update cache
                    resp_data = data.get('data', {})
                    config.update_validation_cache(
                        is_valid=True,
                        message="Lisensi valid.",
                        expires_at=resp_data.get('expires_at'),
                        product_name=resp_data.get('product_name'),
                        client_name=resp_data.get('client_name'),
                    )
                    logger.info(f"Validasi lisensi berhasil: {config.license_key}")
                    return True
                else:
                    # CLS mengatakan invalid
                    config.update_validation_cache(
                        is_valid=False,
                        message=data.get('message', 'Lisensi tidak valid.')
                    )
                    logger.warning(f"Validasi gagal: {data.get('message')}")
                    return False

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            # Gagal koneksi ke CLS — kembalikan status cache lama
            logger.error(f"Gagal menghubungi CLS: {e}")
            return False

        except Exception as e:
            logger.error(f"Error saat validasi lisensi: {e}")
            return False
