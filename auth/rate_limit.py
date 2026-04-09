"""
==========================================================================
 RATE LIMIT DECORATOR - Pembatasan Akses Halaman Autentikasi
==========================================================================
 File ini berisi decorator untuk membatasi jumlah percobaan akses
 pada halaman autentikasi (login, register, forgot password, dll).

 Tujuan:
 - Mencegah serangan brute-force (tebak password)
 - Mencegah spam pendaftaran akun palsu
 - Mencegah spam pengiriman email (reset password / verifikasi)

 Cara kerja:
 - Menggunakan Django cache framework untuk menyimpan hitungan percobaan
 - Setiap IP address memiliki counter sendiri
 - Jika counter melebihi batas → request ditolak dengan pesan error
 - Counter otomatis reset setelah periode waktu tertentu

 Penggunaan:
 - Import: from auth.rate_limit import rate_limit_view
 - Pasang di method post() atau get() menggunakan @method_decorator

 Contoh:
   from django.utils.decorators import method_decorator
   from auth.rate_limit import rate_limit_view

   class LoginView(AuthView):
       @method_decorator(rate_limit_view(max_attempts=5, period=300))
       def post(self, request):
           ...

 Koneksi:
 - config/settings.py → CACHES (backend penyimpanan counter)
 - auth/login/views.py → LoginView.post()
 - auth/register/views.py → RegisterView.post()
 - auth/forgot_password/views.py → ForgetPasswordView.post()
 - auth/reset_password/views.py → ResetPasswordView.post()
 - auth/verify_email/views.py → SendVerificationView.get()
==========================================================================
"""

import functools
from django.core.cache import cache
from django.contrib import messages
from django.shortcuts import redirect


def get_client_ip(request):
    """
    Mendapatkan IP address asli dari client/pengguna.

    Kenapa tidak langsung pakai request.META['REMOTE_ADDR']?
    - Jika server di belakang reverse proxy (Nginx, Cloudflare),
      REMOTE_ADDR berisi IP proxy, bukan IP asli pengguna
    - Header HTTP_X_FORWARDED_FOR berisi IP asli dari chain proxy
    - Format: "IP_client, IP_proxy1, IP_proxy2" → ambil yang pertama

    Return:
    - String IP address (contoh: "192.168.1.100")
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Ambil IP pertama (IP asli client)
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        # Tidak ada proxy → langsung ambil REMOTE_ADDR
        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
    return ip


def rate_limit_view(max_attempts=5, period=300, redirect_url=None):
    """
    Decorator untuk membatasi jumlah percobaan akses pada view.

    Parameter:
    - max_attempts (int): Jumlah maksimal percobaan yang diizinkan
      Default: 5 kali
    - period (int): Periode waktu dalam detik sebelum counter reset
      Default: 300 detik (5 menit)
    - redirect_url (str): URL tujuan redirect saat rate limit tercapai
      Default: None (redirect ke URL yang sama / halaman sebelumnya)

    Cara kerja:
    1. Buat cache key unik berdasarkan: nama view + IP address
    2. Ambil counter dari cache (default 0 jika belum ada)
    3. Jika counter >= max_attempts → tolak request, tampilkan pesan error
    4. Jika belum → increment counter dan lanjutkan ke view asli
    5. Cache key akan otomatis expire setelah 'period' detik

    Contoh cache key: "rate_limit_LoginView_post_192.168.1.100"
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(self_or_request, *args, **kwargs):
            # Tentukan object request
            # CBV: parameter pertama adalah self, kedua adalah request
            # FBV: parameter pertama langsung request
            if hasattr(self_or_request, 'request'):
                # Class-Based View (CBV) → self_or_request = self
                request = self_or_request.request
                view_self = self_or_request
            elif hasattr(self_or_request, 'META'):
                # Function-Based View (FBV) → self_or_request = request
                request = self_or_request
                view_self = None
            else:
                # CBV dengan method_decorator → args[0] = request
                request = args[0] if args else self_or_request
                view_self = self_or_request

            # Buat cache key unik: nama_view + ip_address
            ip = get_client_ip(request)
            view_name = view_func.__qualname__  # Contoh: "LoginView.post"
            cache_key = f"rate_limit_{view_name}_{ip}"

            # Ambil jumlah percobaan saat ini dari cache
            attempts = cache.get(cache_key, 0)

            # Cek apakah sudah melebihi batas
            if attempts >= max_attempts:
                # Hitung sisa waktu tunggu
                ttl = cache.ttl(cache_key) if hasattr(cache, 'ttl') else period
                if ttl is None or ttl == 0:
                    ttl = period

                # Konversi detik ke menit untuk pesan yang lebih mudah dibaca
                menit = max(1, ttl // 60)

                messages.error(
                    request,
                    f"Terlalu banyak percobaan. Silakan tunggu {menit} menit sebelum mencoba lagi."
                )

                # Redirect ke URL yang ditentukan atau halaman sebelumnya
                if redirect_url:
                    return redirect(redirect_url)
                else:
                    # Redirect ke halaman yang sama (referer) atau login
                    referer = request.META.get('HTTP_REFERER')
                    if referer:
                        return redirect(referer)
                    return redirect('login')

            # Belum melebihi batas → increment counter
            # cache.set() dengan timeout → otomatis hapus setelah 'period' detik
            cache.set(cache_key, attempts + 1, timeout=period)

            # Lanjutkan ke view asli
            if view_self is not None:
                return view_func(view_self, *args, **kwargs)
            else:
                return view_func(self_or_request, *args, **kwargs)

        return wrapper
    return decorator
