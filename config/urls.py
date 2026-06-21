"""
==========================================================================
 CONFIG URLS - Routing URL Master SIMKOS (Sistem Manajemen Kost)
==========================================================================
 /                   -> Dashboard
 /properti/          -> Properti, Tipe Kamar, Kamar
 /penyewa/           -> Data Penyewa
 /sewa/              -> Kontrak Sewa, Tagihan, Pembayaran
 /biaya/             -> Transaksi Biaya
 /laporan/           -> Laporan Keuangan Kost
 /users/             -> User Management
 /access/            -> Permission & Role Management
 /activity-log/      -> Activity Log
 /pengaturan/        -> Pengaturan Sistem
 /automation/        -> Notifikasi Telegram
==========================================================================
"""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.views.generic.base import RedirectView
from web_project.views import custom_error_404, custom_error_403, custom_error_400, custom_error_500

import logging

logger = logging.getLogger(__name__)



@never_cache
@login_required
def global_search_api(request):
    """API pencarian global — mencari di semua model utama SIMKOS."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    try:
        # 1. Properti
        from apps.properti.models import Properti
        for p in Properti.objects.filter(Q(nama__icontains=query) | Q(alamat__icontains=query))[:5]:
            results.append({
                'title': p.nama,
                'subtitle': f'{p.get_tipe_display()} - {p.kota or ""}',
                'icon': 'ri-building-2-line',
                'category': 'Properti',
                'url': f'/properti/{p.pk}/',
            })

        # 2. Kamar
        from apps.properti.models import Kamar
        for k in Kamar.objects.filter(Q(nomor_kamar__icontains=query) | Q(properti__nama__icontains=query))[:5]:
            results.append({
                'title': f'Kamar {k.nomor_kamar}',
                'subtitle': k.properti.nama,
                'icon': 'ri-door-open-line',
                'category': 'Kamar',
                'url': '/properti/kamar/',
            })

        # 3. Penyewa
        from apps.penyewa.models import Penyewa
        for p in Penyewa.objects.filter(Q(nama__icontains=query) | Q(telepon__icontains=query) | Q(nik__icontains=query))[:5]:
            results.append({
                'title': p.nama,
                'subtitle': p.telepon or 'Penyewa',
                'icon': 'ri-user-heart-line',
                'category': 'Penyewa',
                'url': f'/penyewa/{p.pk}/',
            })

        # 4. Kontrak
        from apps.sewa.models import KontrakSewa
        for k in KontrakSewa.objects.filter(Q(nomor_kontrak__icontains=query))[:3]:
            results.append({
                'title': k.nomor_kontrak,
                'subtitle': k.penyewa.nama,
                'icon': 'ri-file-list-3-line',
                'category': 'Kontrak',
                'url': f'/sewa/kontrak/{k.pk}/',
            })

        # 5. Tagihan
        from apps.sewa.models import TagihanSewa
        for t in TagihanSewa.objects.filter(Q(nomor_tagihan__icontains=query))[:3]:
            results.append({
                'title': t.nomor_tagihan,
                'subtitle': f'Rp {t.jumlah:,.0f}',
                'icon': 'ri-bill-line',
                'category': 'Tagihan',
                'url': '/sewa/tagihan/',
            })

        # 6. User
        from django.contrib.auth.models import User
        for u in User.objects.filter(Q(username__icontains=query) | Q(first_name__icontains=query))[:3]:
            results.append({
                'title': u.get_full_name() or u.username,
                'subtitle': f'@{u.username}',
                'icon': 'ri-user-line',
                'category': 'User',
                'url': f'/users/detail/{u.pk}/',
            })

    except Exception as e:
        logger.warning("Error tidak terduga: %s", e)

    return JsonResponse({'results': results[:20]})


urlpatterns = [
    # Django Admin
    path("admin/", admin.site.urls),

    # Global Search API
    path("api/search/", global_search_api, name='global_search'),

    # License Activation URLs
    path("", include("apps.core.license_urls")),

    # Auth URLs
    path("", include("auth.urls")),

    # SIMKOS Module URLs
    path("", include("apps.dashboard.urls")),
    path("users/", include("apps.user_management.urls")),
    path("properti/", include("apps.properti.urls")),
    path("penyewa/", include("apps.penyewa.urls")),
    path("sewa/", include("apps.sewa.urls")),
    path("biaya/", include("apps.biaya.urls")),
    path("laporan/", include("apps.laporan.urls")),
    path("activity-log/", include("apps.activity_log.urls")),
    path("pengaturan/", include("apps.pengaturan.urls")),
    path("access/", include("apps.permission_management.urls")),
    path("automation/", include("apps.automation.urls")),
    path("hr/", include("apps.hr.urls")),
    path("ai/", include("apps.ai_assistant.urls")),

    # Original URLs
    path("", include("apps.pages.urls")),
    path("", RedirectView.as_view(url='/', permanent=True), name='landing-page'),
]

# Media files — dilayani di semua environment (development & production)
# WhiteNoise hanya menangani static files, bukan media files.
# Agar foto/upload berfungsi di production, Django harus tetap melayani media.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Test Error Routes — only available in DEBUG mode
if settings.DEBUG:
    urlpatterns += [
        path("test-error/404/", lambda request: custom_error_404(request, Exception("Test 404"))),
        path("test-error/403/", lambda request: custom_error_403(request, Exception("Test 403"))),
        path("test-error/400/", lambda request: custom_error_400(request, Exception("Test 400"))),
        path("test-error/500/", lambda request: custom_error_500(request)),
    ]

# Error Handlers
handler404 = custom_error_404
handler403 = custom_error_403
handler400 = custom_error_400
handler500 = custom_error_500
