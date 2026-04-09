"""
==========================================================================
 REGISTER VIEW - Halaman Registrasi User Baru
==========================================================================
 File ini menangani proses pendaftaran user baru ke sistem.

 Alur registrasi:
 1. User mengakses /register/ → tampilkan form registrasi (GET)
 2. User mengisi username, email, password → submit (POST)
 3. Validasi: cek duplikasi username dan email
 4. Buat User baru + Profile otomatis (via signal)
 5. Generate token verifikasi email (UUID)
 6. Kirim email verifikasi
 7. Redirect ke halaman verifikasi email

 Koneksi:
 - auth/views.py → AuthView (base class)
 - auth/helpers.py → send_verification_email()
 - auth/models.py → Profile (dibuat otomatis via signal)
 - django.contrib.auth.models.User → Model User bawaan
 - django.contrib.auth.models.Group → Grup 'client' default
==========================================================================
"""

from django.shortcuts import redirect          # Fungsi redirect ke URL lain
from django.contrib.auth.models import User, Group  # Model User & Group bawaan Django
from django.contrib import messages             # Framework pesan flash
from django.conf import settings                # Akses pengaturan Django
from django.utils.decorators import method_decorator  # Decorator untuk CBV
from auth.views import AuthView                 # Base class autentikasi
from auth.helpers import send_verification_email  # Fungsi kirim email verifikasi
from auth.models import Profile                 # Model Profile
from auth.rate_limit import rate_limit_view     # Rate limit decorator
import uuid                                    # Modul untuk generate token unik (UUID v4)


class RegisterView(AuthView):
    """
    View untuk halaman registrasi user baru.

    Mewarisi AuthView → layout_blank.html (tanpa sidebar/navbar).

    Method:
    - get(): Tampilkan form registrasi
    - post(): Proses pendaftaran user baru

    Rate Limit:
    - POST dibatasi 5 percobaan per 1 jam per IP
    - Mencegah pembuatan akun spam secara massal
    """

    def get(self, request):
        """
        Tampilkan halaman registrasi (GET).

        Jika user sudah login → redirect ke dashboard.
        Jika belum → render form registrasi.
        """
        if request.user.is_authenticated:
            return redirect("dashboard:index")
        return super().get(request)

    @method_decorator(rate_limit_view(max_attempts=5, period=3600, redirect_url='register'))
    def post(self, request):
        """
        Proses registrasi user baru (POST).

        Alur detail:
        1. Ambil data dari form (username, email, password)
        2. Validasi duplikasi (username + email, email saja, username saja)
        3. Buat User baru dan set password
        4. Tambahkan user ke grup 'client' (grup default)
        5. Generate token UUID untuk verifikasi email
        6. Simpan token di Profile user
        7. Kirim email verifikasi
        8. Redirect ke halaman verifikasi email

        Kenapa pakai User.objects.create_user()?
        - create_user() otomatis meng-hash password
        - Jangan pakai User.objects.create() → password akan disimpan plain text!
        """
        # Ambil data dari form HTML
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")

        # ===== VALIDASI DUPLIKASI =====
        # Cek kombinasi username + email sudah ada
        if User.objects.filter(username=username, email=email).exists():
            messages.error(request, "User sudah terdaftar, silakan login.")
            return redirect("register")
        # Cek email saja sudah ada
        elif User.objects.filter(email=email).exists():
            messages.error(request, "Email sudah terdaftar.")
            return redirect("register")
        # Cek username saja sudah ada
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Username sudah terdaftar.")
            return redirect("register")

        # ===== BUAT USER BARU =====
        # create_user() → buat user + hash password secara otomatis
        created_user = User.objects.create_user(username=username, email=email, password=password)
        created_user.set_password(password)  # Hash ulang password (redundan tapi aman)
        created_user.save()

        # ===== GRUP DEFAULT =====
        # Tambahkan user ke grup 'client'
        # get_or_create() → ambil grup jika sudah ada, buat jika belum
        # Grup di Django digunakan untuk mengelompokkan user
        user_group, created = Group.objects.get_or_create(name="client")
        created_user.groups.add(user_group)

        # ===== TOKEN VERIFIKASI EMAIL =====
        # Generate UUID v4 sebagai token unik (contoh: 'a1b2c3d4-e5f6-...')
        token = str(uuid.uuid4())

        # Simpan token di Profile user
        # get_or_create() untuk berjaga-jaga jika Profile belum dibuat oleh signal
        user_profile, created = Profile.objects.get_or_create(user=created_user)
        user_profile.email_token = token
        user_profile.email = email
        user_profile.save()

        # ===== KIRIM EMAIL VERIFIKASI =====
        try:
            send_verification_email(email, token)
            messages.success(request, "Email verifikasi berhasil dikirim")
        except Exception as e:
            # Jika pengiriman email gagal (SMTP error, dll), tampilkan error
            # Tapi user tetap terdaftar — bisa kirim ulang nanti
            messages.error(request, f"Gagal mengirim email: {str(e)}")

        # Simpan email di session — digunakan di halaman verifikasi
        request.session['email'] = email

        # Redirect ke halaman "Cek email Anda untuk verifikasi"
        return redirect("verify-email-page")
