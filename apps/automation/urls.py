"""
==========================================================================
 AUTOMATION URLS - Routing URL Modul Automasi (Telegram)
==========================================================================
 Peta URL modul automasi:

 Pengaturan Telegram:
 - /automation/telegram/                → Halaman pengaturan bot
 - /automation/telegram/test/           → API test kirim pesan
 - /automation/telegram/deteksi-chat-id/→ API deteksi chat ID

 Template Pesan:
 - /automation/template-pesan/          → Daftar template pesan
 - /automation/template-pesan/<id>/edit/ → Edit template pesan
 - /automation/template-pesan/<id>/reset/→ Reset template ke default

 Log Notifikasi:
 - /automation/log/                     → Riwayat pengiriman notifikasi

 Didaftarkan di config/urls.py: path('automation/', include('apps.automation.urls'))
==========================================================================
"""
from django.urls import path
from . import views

app_name = 'automation'  # Namespace URL — digunakan: {% url 'automation:pengaturan_telegram' %}

urlpatterns = [
    # ── Pengaturan Telegram ──────────────────────────────────
    path('telegram/', views.PengaturanTelegramView.as_view(), name='pengaturan_telegram'),
    path('telegram/test/', views.test_kirim_telegram, name='test_kirim_telegram'),
    path('telegram/deteksi-chat-id/', views.deteksi_chat_id, name='deteksi_chat_id'),

    # ── Template Pesan ───────────────────────────────────────
    path('template-pesan/', views.TemplatePesanListView.as_view(), name='template_pesan_list'),
    path('template-pesan/<int:pk>/edit/', views.TemplatePesanUpdateView.as_view(), name='template_pesan_update'),
    path('template-pesan/<int:pk>/reset/', views.reset_template, name='template_pesan_reset'),

    # ── Log Notifikasi ───────────────────────────────────────
    path('log/', views.LogNotifikasiView.as_view(), name='log_notifikasi'),

    # ── Telegram Webhook (AI Bot) ─────────────────────────
    path('telegram/webhook/', views.telegram_webhook, name='telegram_webhook'),
    path('telegram/set-webhook/', views.set_webhook, name='set_webhook'),
]
