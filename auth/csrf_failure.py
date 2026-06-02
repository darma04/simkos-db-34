"""
==========================================================================
 CSRF FAILURE HANDLER — Penanganan Token CSRF Kedaluwarsa
==========================================================================
 Menggantikan halaman error 403 bawaan Django saat CSRF token gagal
 dengan redirect ramah ke halaman login beserta pesan informatif.

 Penyebab umum CSRF failure:
 - Halaman login dibiarkan terbuka terlalu lama sebelum submit
 - Tab browser di-resume setelah lama tidak aktif (sleep/hibernate)
 - Cookie browser dihapus/expired saat halaman masih terbuka

 Koneksi:
 - config/settings.py → CSRF_FAILURE_VIEW = "auth.csrf_failure.csrf_failure_view"
 - django.middleware.csrf.CsrfViewMiddleware → memanggil view ini saat gagal
==========================================================================
"""
from django.shortcuts import redirect
from django.contrib import messages


def csrf_failure_view(request, reason=""):
    """
    Handler saat CSRF verification gagal.
    Alih-alih menampilkan error 403 yang membingungkan user,
    redirect kembali ke halaman sebelumnya dengan pesan yang jelas.
    """
    messages.warning(
        request,
        "Sesi formulir Anda telah kedaluwarsa. Silakan coba lagi."
    )

    # Redirect ke halaman yang sedang diakses (referer) atau ke login
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        return redirect(referer)
    return redirect('login')
