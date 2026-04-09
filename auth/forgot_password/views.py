"""
==========================================================================
 FORGOT PASSWORD VIEW - Halaman Lupa Password
==========================================================================
 File ini menangani fitur lupa password (forgot password).

 Alur kerja:
 1. User mengakses /forgot_password/ → tampilkan form email (GET)
 2. User memasukkan email → submit (POST)
 3. Sistem cek apakah email terdaftar
 4. Generate token UUID + set waktu kadaluarsa (24 jam)
 5. Kirim email reset password dengan link berisi token
 6. User klik link di email → diarahkan ke halaman reset password

 Keamanan:
 - Token menggunakan UUID v4 (random, sulit ditebak)
 - Token punya waktu kadaluarsa (24 jam)
 - Setelah digunakan, token dihapus dari database

 Koneksi:
 - auth/views.py → AuthView (base class)
 - auth/helpers.py → send_password_reset_email()
 - auth/models.py → Profile (menyimpan token di field forget_password_token)
 - auth/reset_password/views.py → Halaman reset password yang menggunakan token
==========================================================================
"""

from django.shortcuts import redirect          # Fungsi redirect
from django.contrib.auth.models import User     # Model User bawaan Django
from django.contrib import messages             # Framework pesan flash
from django.conf import settings                # Akses pengaturan Django
from django.utils.decorators import method_decorator  # Decorator untuk CBV
from auth.helpers import send_password_reset_email  # Fungsi kirim email reset
from auth.models import Profile                 # Model Profile
from auth.views import AuthView                 # Base class autentikasi
from auth.rate_limit import rate_limit_view     # Rate limit decorator
from datetime import timedelta, datetime        # Modul untuk kalkulasi waktu
import uuid                                    # Modul generate token unik


class ForgetPasswordView(AuthView):
    """
    View untuk halaman lupa password.

    Method:
    - get(): Tampilkan form input email
    - post(): Proses request reset password

    Rate Limit:
    - POST dibatasi 3 percobaan per 10 menit per IP
    - Mencegah spam pengiriman email reset password
    """

    def get(self, request):
        """
        Tampilkan halaman lupa password (GET).

        Jika user sudah login → redirect ke dashboard.
        """
        if request.user.is_authenticated:
            return redirect("dashboard:index")
        return super().get(request)

    @method_decorator(rate_limit_view(max_attempts=3, period=600, redirect_url='forgot-password'))
    def post(self, request):
        """
        Proses request reset password (POST).

        Alur:
        1. Ambil email dari form
        2. Cari user dengan email tersebut
        3. Jika tidak ditemukan → tampilkan error
        4. Jika ditemukan:
           a. Generate token UUID v4
           b. Set waktu kadaluarsa = sekarang + 24 jam
           c. Simpan token dan expiry di Profile
           d. Kirim email reset password
        5. Redirect kembali ke halaman forgot password
        """
        if request.method == "POST":
            email = request.POST.get("email")

            # Cari user berdasarkan email
            user = User.objects.filter(email=email).first()
            if not user:
                messages.error(request, "Tidak ada akun dengan email tersebut.")
                return redirect("forgot-password")

            # Generate token UUID unik untuk reset password
            token = str(uuid.uuid4())

            # Set waktu kadaluarsa token = 24 jam dari sekarang
            # Setelah 24 jam, link reset password tidak bisa digunakan lagi
            expiration_time = datetime.now() + timedelta(hours=24)

            # Simpan token dan waktu kadaluarsa di Profile user
            user_profile, created = Profile.objects.get_or_create(user=user)
            user_profile.forget_password_token = token
            user_profile.forget_password_token_expiration = expiration_time
            user_profile.save()

            # Kirim email reset password
            try:
                send_password_reset_email(email, token)
                messages.success(request, "Link reset kata sandi telah dikirim ke email Anda.")
            except Exception as e:
                messages.error(request, f"Gagal mengirim email: {str(e)}")

            return redirect("forgot-password")
