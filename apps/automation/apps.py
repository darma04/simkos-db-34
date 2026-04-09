"""
==========================================================================
 AUTOMATION APPS - Konfigurasi Aplikasi Automasi (Telegram)
==========================================================================
 Konfigurasi Django app untuk modul automasi.
 Method ready() mengimpor signals.py agar signal handler terdaftar
 saat Django startup. Ini diperlukan agar notifikasi otomatis aktif.

 Bot Telegram juga otomatis dimulai (polling) saat server berjalan,
 baik di development (runserver) maupun production (gunicorn).
==========================================================================
"""
import os
from django.apps import AppConfig


class AutomationConfig(AppConfig):
    """Konfigurasi aplikasi Automation — integrasi Telegram dan notifikasi otomatis."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.automation'   # Path app (harus sesuai INSTALLED_APPS)
    verbose_name = 'Automasi'  # Nama tampilan di Django Admin

    def ready(self):
        """
        Import signals.py saat startup agar signal handlers aktif.
        Juga memulai bot Telegram polling otomatis.
        """
        import apps.automation.signals  # noqa: F401

        # Auto-start Telegram Bot polling
        # Hindari saat: migrate, shell, collectstatic, test, dll
        # Hanya jalankan saat server HTTP benar-benar berjalan
        import sys
        argv_str = ' '.join(sys.argv)

        # Daftar command yang TIDAK boleh menjalankan polling
        skip_commands = (
            'migrate', 'makemigrations', 'shell', 'dbshell',
            'collectstatic', 'test', 'check', 'createsuperuser',
            'flush', 'showmigrations', 'inspectdb', 'compilemessages',
            'run_telegram_bot',  # Hindari double polling jika manual
        )
        should_skip = any(cmd in argv_str for cmd in skip_commands)

        if should_skip:
            return

        # Untuk runserver: hanya jalankan di proses utama (RUN_MAIN=true)
        # Ini mencegah double polling karena reloader
        is_runserver = 'runserver' in sys.argv
        if is_runserver:
            is_main_process = os.environ.get('RUN_MAIN') == 'true'
            if not is_main_process:
                return

        # Untuk Gunicorn (VPS): Gunicorn tidak set RUN_MAIN,
        # dan bisa spawn multiple worker. Gunakan file lock untuk
        # memastikan hanya 1 worker yang menjalankan polling.
        if not is_runserver:
            if not self._acquire_polling_lock():
                return

        try:
            from .telegram_bot import start_polling
            start_polling()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[AutomationConfig] Gagal start polling: {e}")

    def _acquire_polling_lock(self):
        """
        Buat file lock untuk memastikan hanya 1 Gunicorn worker
        yang menjalankan polling. Worker lain akan skip.
        Returns True jika lock berhasil di-acquire.
        """
        import tempfile
        lock_file = os.path.join(tempfile.gettempdir(), 'simkos_telegram_polling.lock')

        try:
            if os.path.exists(lock_file):
                # Cek apakah lock masih valid (proses masih berjalan)
                try:
                    with open(lock_file, 'r') as f:
                        pid = int(f.read().strip())
                    # Cek apakah PID masih jalan
                    os.kill(pid, 0)
                    # Proses masih hidup → lock valid → skip
                    return False
                except (OSError, ValueError):
                    # Proses sudah mati → lock stale → ambil alih
                    pass

            # Tulis PID kita ke lock file
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
            return True

        except Exception:
            # Jika gagal membuat lock, tetap jalankan polling
            return True
