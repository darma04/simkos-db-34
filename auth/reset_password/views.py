"""
==========================================================================
 RESET PASSWORD VIEW - Halaman Reset Password
==========================================================================
 File ini menangani proses reset (mengubah) password user.

 Alur kerja:
 1. User klik link reset di email → /reset_password/{token}/ (GET)
 2. Sistem validasi token: ada di database? belum kadaluarsa?
 3. Jika valid → tampilkan form password baru
 4. User mengisi password baru dan konfirmasi → submit (POST)
 5. Validasi ulang token + cek password match
 6. Update password di database → hapus token
 7. Redirect ke halaman login

 Keamanan:
 - Token dicek di GET dan POST (double validation)
 - Token yang kadaluarsa ditolak
 - Setelah password diubah, token dihapus (tidak bisa dipakai ulang)

 Koneksi:
 - auth/views.py → AuthView (base class)
 - auth/models.py → Profile (field forget_password_token)
 - auth/urls.py → path("reset_password/<str:token>/", ...)
==========================================================================
"""

from django.shortcuts import render, redirect      # Fungsi render dan redirect
from django.contrib import messages                 # Framework pesan flash
from django.utils.decorators import method_decorator  # Decorator untuk CBV
from auth.models import Profile                     # Model Profile
from auth.views import AuthView                     # Base class autentikasi
from auth.rate_limit import rate_limit_view         # Rate limit decorator
from django.contrib.auth import authenticate, login  # Autentikasi Django
from datetime import datetime                       # Modul waktu
from django.utils import timezone                   # Timezone-aware datetime Django


class ResetPasswordView(AuthView):
    """
    View untuk halaman reset password.

    URL: /reset_password/{token}/
    Parameter token diterima dari URL dan diteruskan ke get()/post().

    Method:
    - get(token): Validasi token dan tampilkan form password baru
    - post(token): Proses perubahan password

    Rate Limit:
    - POST dibatasi 5 percobaan per 10 menit per IP
    - Mencegah brute-force token reset password
    """

    def get(self, request, token):
        """
        Tampilkan form reset password (GET).

        Validasi:
        1. Cek apakah user sudah login → redirect ke dashboard
        2. Cari Profile dengan token yang sesuai
        3. Cek apakah token sudah kadaluarsa (> 24 jam)
        4. Jika valid → tampilkan form
        5. Jika tidak → redirect ke halaman forgot password

        Parameter:
        - token: String UUID dari URL (contoh: 'a1b2c3d4-...')
        """
        if request.user.is_authenticated:
            return redirect("dashboard:index")

        try:
            # Cari Profile berdasarkan token
            profile = Profile.objects.get(forget_password_token=token)

            # Cek apakah token sudah kadaluarsa
            if profile.forget_password_token_expiration:
                # timezone.now() → waktu sekarang (timezone-aware)
                # Jika waktu sekarang > waktu kadaluarsa → token sudah expired
                if timezone.now() > profile.forget_password_token_expiration:
                    messages.error(request, "Link reset ini sudah kedaluwarsa. Silakan minta yang baru.")
                    return redirect("forgot-password")

            # Token valid → tampilkan form reset password
            return super().get(request)

        except Profile.DoesNotExist:
            # Token tidak ditemukan di database → invalid
            messages.error(request, "Token tidak valid atau sudah kedaluwarsa.")
            return redirect("forgot-password")

    @method_decorator(rate_limit_view(max_attempts=5, period=600, redirect_url='forgot-password'))
    def post(self, request, token):
        """
        Proses perubahan password (POST).

        Alur:
        1. Validasi ulang token (bisa saja kadaluarsa saat user mengisi form)
        2. Ambil password baru dan konfirmasi dari form
        3. Validasi: field tidak kosong dan password cocok
        4. Update password user di database
        5. Hapus token dari Profile (agar tidak bisa dipakai ulang)
        6. Redirect ke halaman login dengan pesan sukses
        """
        # Validasi ulang token di POST (sekuriti tambahan)
        try:
            profile = Profile.objects.get(forget_password_token=token)

            # Cek ulang kadaluarsa
            if profile.forget_password_token_expiration:
                if timezone.now() > profile.forget_password_token_expiration:
                    messages.error(request, "Link reset ini sudah kedaluwarsa. Silakan minta yang baru.")
                    return redirect("forgot-password")

        except Profile.DoesNotExist:
            messages.error(request, "Token tidak valid atau sudah kedaluwarsa.")
            return redirect("forgot-password")

        if request.method == "POST":
            # Ambil password baru dan konfirmasi dari form
            new_password = request.POST.get("password")
            confirm_password = request.POST.get("confirm-password")

            # Validasi: semua field harus terisi
            if not (new_password and confirm_password):
                messages.error(request, "Silakan isi semua field.")
                return redirect("reset-password", token=token)

            # Validasi: password baru harus sama dengan konfirmasi
            if new_password != confirm_password:
                messages.error(request, "Kata sandi tidak cocok.")
                return redirect("reset-password", token=token)

            # ===== UPDATE PASSWORD =====
            # Ambil user dari profile dan set password baru
            # set_password() otomatis meng-hash password
            user = profile.user
            user.set_password(new_password)
            user.save()

            # ===== HAPUS TOKEN =====
            # Bersihkan token agar tidak bisa dipakai ulang (one-time use)
            profile.forget_password_token = ""
            profile.forget_password_token_expiration = None
            profile.save()

            # Redirect ke login dengan pesan sukses
            messages.success(request, "Kata sandi berhasil diubah. Silakan login dengan kata sandi baru.")
            return redirect("login")
