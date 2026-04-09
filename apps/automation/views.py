"""
==========================================================================
 AUTOMATION VIEWS - Views Pengaturan & Monitoring Notifikasi Telegram
==========================================================================
 Views untuk mengelola notifikasi Telegram dari antarmuka web:

 Class-Based Views (CBV):
 ┌────────────────────────┬──────────────────────────────────────────────┐
 │ View                   │ Penjelasan                                   │
 ├────────────────────────┼──────────────────────────────────────────────┤
 │ PengaturanTelegramView │ Halaman pengaturan bot (token, chat_id, dll) │
 │ TemplatePesanListView  │ Daftar template pesan notifikasi              │
 │ TemplatePesanUpdateView│ Edit template pesan (placeholder {{var}})     │
 │ LogNotifikasiView      │ Riwayat + statistik pengiriman notifikasi    │
 └────────────────────────┴──────────────────────────────────────────────┘

 Function-Based Views (FBV) — API Endpoints:
 ┌────────────────────┬────────────────────────────────────────────────┐
 │ Fungsi             │ Penjelasan                                      │
 ├────────────────────┼────────────────────────────────────────────────┤
 │ test_kirim_telegram│ POST API — Kirim pesan test untuk cek koneksi   │
 │ deteksi_chat_id    │ POST API — Auto-detect Chat ID via getUpdates   │
 │ reset_template     │ POST API — Reset template ke default            │
 └────────────────────┴────────────────────────────────────────────────┘

 Terhubung dengan:
 - models.py → PengaturanTelegram, TemplatePesan, LogNotifikasi
 - telegram_service.py → kirim_pesan_telegram() untuk test
 - urls.py → Routing URL modul automation
 - apps/core/mixins.py → ReadPermissionMixin, UpdatePermissionMixin
==========================================================================
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, UpdateView
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from web_project import TemplateLayout

from .models import PengaturanTelegram, TemplatePesan, LogNotifikasi
from .telegram_service import kirim_pesan_telegram

from apps.core.permissions import has_permission, get_user_role
from apps.core.mixins import ReadPermissionMixin, UpdatePermissionMixin
from apps.pengaturan.models import TemplateCetak
from django.db import transaction


class PengaturanTelegramView(ReadPermissionMixin, TemplateView):
    """View untuk pengaturan bot Telegram"""
    template_name = 'automation/pengaturan_telegram.html'
    permission_module = 'automation'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['pengaturan'] = PengaturanTelegram.load()
        # Statistik log
        context['total_terkirim'] = LogNotifikasi.objects.filter(status='sukses').count()
        context['total_gagal'] = LogNotifikasi.objects.filter(status='gagal').count()
        context['log_terbaru'] = LogNotifikasi.objects.all()[:5]
        return context

    def post(self, request, *args, **kwargs):
        """Handle HTTP POST request — simpan pengaturan Telegram."""
        # Cek permission edit
        if not has_permission(request.user, 'update', 'automation'):
            messages.error(request, 'Anda tidak memiliki akses untuk mengubah pengaturan ini.')
            return redirect('automation:pengaturan_telegram')

        pengaturan = PengaturanTelegram.load()
        pengaturan.bot_token = request.POST.get('bot_token', '').strip()
        pengaturan.chat_id = request.POST.get('chat_id', '').strip()
        pengaturan.aktif = request.POST.get('aktif') == 'on'
        pengaturan.notif_tagihan = request.POST.get('notif_tagihan') == 'on'
        pengaturan.notif_kwitansi = request.POST.get('notif_kwitansi') == 'on'
        pengaturan.notif_biaya = request.POST.get('notif_biaya') == 'on'
        pengaturan.notif_gaji = request.POST.get('notif_gaji') == 'on'
        pengaturan.kirim_pdf = request.POST.get('kirim_pdf') == 'on'
        pengaturan.system_prompt_bot = request.POST.get('system_prompt_bot', '').strip()
        pengaturan.save()

        messages.success(request, 'Pengaturan Telegram berhasil disimpan!')
        return redirect('automation:pengaturan_telegram')


class TemplatePesanListView(ReadPermissionMixin, ListView):
    """View untuk daftar template pesan"""
    model = TemplatePesan
    template_name = 'automation/template_pesan_list.html'
    context_object_name = 'templates'
    ordering = ['jenis']
    permission_module = 'automation'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Pastikan semua template default ada
        for jenis, label in TemplatePesan.JENIS_CHOICES:
            TemplatePesan.get_template(jenis)
        context['templates'] = TemplatePesan.objects.all().order_by('jenis')
        return context


class TemplatePesanUpdateView(UpdatePermissionMixin, UpdateView):
    """View untuk edit template pesan"""
    model = TemplatePesan
    template_name = 'automation/template_pesan_form.html'
    fields = ['nama', 'template_pesan', 'aktif']
    success_url = reverse_lazy('automation:template_pesan_list')
    permission_module = 'automation'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Variabel yang tersedia per jenis
        variabel_map = {
            'tagihan': ['nomor_tagihan', 'periode', 'penyewa', 'kamar', 'jumlah', 'jatuh_tempo', 'status'],
            'kwitansi': ['nomor_pembayaran', 'tanggal', 'penyewa', 'jumlah', 'metode', 'keterangan'],
            'biaya': ['nomor_transaksi', 'tanggal', 'kategori', 'jumlah', 'deskripsi', 'dibuat_oleh'],
            'gaji': ['nama_karyawan', 'periode', 'gaji_pokok', 'tunjangan', 'potongan', 'gaji_bersih', 'status'],
        }
        context['variabel_tersedia'] = variabel_map.get(self.object.jenis, [])
        return context

    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        messages.success(self.request, f'Template "{form.instance.nama}" berhasil diupdate!')
        return super().form_valid(form)


class LogNotifikasiView(ReadPermissionMixin, ListView):
    """View untuk log pengiriman notifikasi"""
    model = LogNotifikasi
    template_name = 'automation/log_notifikasi.html'
    context_object_name = 'logs'
    paginate_by = 50
    permission_module = 'automation'

    def get_queryset(self):
        """Override queryset — filter atau optimasi query data."""
        qs = super().get_queryset()
        # Filter berdasarkan jenis transaksi
        jenis = self.request.GET.get('jenis')
        if jenis:
            qs = qs.filter(jenis_transaksi=jenis)
        # Filter berdasarkan status
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['total_sukses'] = LogNotifikasi.objects.filter(status='sukses').count()
        context['total_gagal'] = LogNotifikasi.objects.filter(status='gagal').count()
        context['total_semua'] = LogNotifikasi.objects.count()
        context['jenis_filter'] = self.request.GET.get('jenis', '')
        context['status_filter'] = self.request.GET.get('status', '')
        # Context untuk export PDF
        try:
            context['export_pdf_template'] = TemplateCetak.objects.first()
        except Exception:
            context['export_pdf_template'] = None
        return context


@login_required
def test_kirim_telegram(request):
    """API untuk test kirim pesan ke Telegram"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    pengaturan = PengaturanTelegram.load()

    if not pengaturan.bot_token or not pengaturan.chat_id:
        return JsonResponse({
            'success': False,
            'message': 'Bot Token dan Chat ID harus diisi terlebih dahulu!'
        })

    pesan_test = (
        "✅ *Test Koneksi Berhasil!*\n"
        "━━━━━━━━━━━━━━━\n"
        "🤖 Bot Telegram terhubung dengan SIMKOS\n"
        "📊 Notifikasi otomatis siap digunakan\n\n"
        "Pengaturan Aktif:\n"
        f"  • Tagihan Sewa: {'✅' if pengaturan.notif_tagihan else '❌'}\n"
        f"  • Kwitansi: {'✅' if pengaturan.notif_kwitansi else '❌'}\n"
        f"  • Biaya Operasional: {'✅' if pengaturan.notif_biaya else '❌'}\n"
        f"  • Gaji Karyawan: {'✅' if pengaturan.notif_gaji else '❌'}\n"
    )

    success, response = kirim_pesan_telegram(
        pengaturan.bot_token,
        pengaturan.chat_id,
        pesan_test
    )

    # Simpan log
    LogNotifikasi.objects.create(
        jenis_transaksi='tagihan',
        nomor_referensi='TEST',
        pesan=pesan_test,
        status='sukses' if success else 'gagal',
        respons=json.dumps(response) if isinstance(response, dict) else None,
        error_message=response if not success and isinstance(response, str) else None,
    )

    if success:
        return JsonResponse({
            'success': True,
            'message': 'Pesan test berhasil dikirim ke Telegram! Cek chat Anda.'
        })
    else:
        return JsonResponse({
            'success': False,
            'message': f'Gagal mengirim: {response}'
        })


@login_required
def deteksi_chat_id(request):
    """API untuk mendeteksi chat_id dari pesan yang masuk ke bot via getUpdates"""
    import urllib.request
    import urllib.error
    import ssl

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    pengaturan = PengaturanTelegram.load()

    if not pengaturan.bot_token:
        return JsonResponse({
            'success': False,
            'message': 'Bot Token harus diisi terlebih dahulu!'
        })

    bot_token = pengaturan.bot_token.strip()
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=10&offset=-10"

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))

        if result.get('ok') and result.get('result'):
            updates = result['result']
            chat_ids_found = []

            for update in updates:
                msg = update.get('message') or update.get('channel_post') or {}
                chat = msg.get('chat', {})
                chat_id = chat.get('id')
                chat_type = chat.get('type', '')
                chat_title = chat.get('title') or chat.get('first_name') or chat.get('username') or str(chat_id)

                if chat_id:
                    entry = {
                        'chat_id': str(chat_id),
                        'title': chat_title,
                        'type': chat_type
                    }
                    # Hindari duplikat
                    if not any(c['chat_id'] == entry['chat_id'] for c in chat_ids_found):
                        chat_ids_found.append(entry)

            if chat_ids_found:
                # Tampilkan chat_id yang ditemukan (TIDAK auto-save ke DB)
                # User harus klik "Simpan Pengaturan" untuk menyimpannya
                first_chat_id = chat_ids_found[0]['chat_id']

                return JsonResponse({
                    'success': True,
                    'message': f'Chat ID berhasil dideteksi: {first_chat_id} ({chat_ids_found[0]["title"]})',
                    'chat_id': first_chat_id,
                    'all_chats': chat_ids_found
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Tidak ditemukan pesan masuk. Kirim pesan /start ke bot Anda terlebih dahulu, lalu klik "Deteksi Chat ID" lagi.'
                })
        elif result.get('ok') and not result.get('result'):
            return JsonResponse({
                'success': False,
                'message': 'Bot belum menerima pesan dari siapapun. Kirim pesan /start ke bot Anda terlebih dahulu.'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Error: {result.get("description", "Unknown error")}'
            })

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('description', str(e))
        except:
            error_msg = f"HTTP {e.code}: {error_body[:200]}"

        if e.code == 401:
            error_msg = "Bot Token tidak valid. Pastikan token benar dari @BotFather."
        return JsonResponse({'success': False, 'message': error_msg})

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })


@login_required
def reset_template(request, pk):
    """Reset template ke default"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        messages.error(request, 'Anda tidak memiliki akses untuk mereset template.')
        return redirect('automation:template_pesan_list')

    template = get_object_or_404(TemplatePesan, pk=pk)
    template.template_pesan = TemplatePesan._get_default_template(template.jenis)
    template.save()

    messages.success(request, f'Template "{template.nama}" berhasil direset ke default!')
    return redirect('automation:template_pesan_list')


# ╔══════════════════════════════════════════════════════════════╗
# ║          TELEGRAM WEBHOOK & AI BOT                            ║
# ╚══════════════════════════════════════════════════════════════╝

from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def telegram_webhook(request):
    """
    Endpoint webhook yang dipanggil oleh Telegram saat ada pesan masuk.
    URL: POST /automation/telegram/webhook/

    Keamanan:
    - csrf_exempt karena Telegram mengirim POST tanpa CSRF token
    - Validasi secret token via header X-Telegram-Bot-Api-Secret-Token
    - Menggunakan thread pool (max 5 worker) untuk mencegah thread leak
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'ok'})

    try:
        # ── VALIDASI SECRET TOKEN ──────────────────────────────
        # Telegram mengirim header ini jika secret_token di-set saat setWebhook
        # Ini mencegah siapapun mengirim request palsu ke endpoint ini
        pengaturan = PengaturanTelegram.load()
        expected_token = _generate_webhook_secret(pengaturan.bot_token)

        received_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if expected_token and received_token != expected_token:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[Webhook] Request ditolak — secret token tidak valid")
            return JsonResponse({'status': 'unauthorized'}, status=403)

        body = json.loads(request.body.decode('utf-8'))

        # ── PROSES VIA THREAD POOL ─────────────────────────────
        # Gunakan thread pool dari telegram_bot (max 5 worker)
        # agar tidak terjadi thread leak saat banyak request masuk
        from .telegram_bot import handle_update, _executor
        try:
            _executor.submit(handle_update, body)
        except RuntimeError:
            # Thread pool sudah shutdown — proses langsung
            handle_update(body)

        return JsonResponse({'status': 'ok'})

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[Webhook] Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error'}, status=500)


def _generate_webhook_secret(bot_token):
    """
    Generate secret token dari bot_token untuk validasi webhook.
    Menggunakan hash SHA-256 agar token asli tidak terexpose.
    Secret ini harus di-set saat memanggil setWebhook API.
    """
    if not bot_token:
        return ''
    import hashlib
    return hashlib.sha256(f"simkos_webhook_{bot_token}".encode()).hexdigest()[:32]


@login_required
def set_webhook(request):
    """
    Mendaftarkan webhook URL ke Telegram Bot API.
    URL: POST /automation/telegram/set-webhook/
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    if not has_permission(request.user, 'update', 'automation'):
        return JsonResponse({'success': False, 'message': 'Anda tidak memiliki akses.'}, status=403)

    import urllib.request
    import urllib.error
    import ssl

    pengaturan = PengaturanTelegram.load()

    if not pengaturan.bot_token:
        return JsonResponse({
            'success': False,
            'message': 'Bot Token harus diisi terlebih dahulu!'
        })

    webhook_url = request.POST.get('webhook_url', '').strip()
    if not webhook_url:
        webhook_url = f"https://simkos.serpgroup.cloud/automation/telegram/webhook/"

    bot_token = pengaturan.bot_token.strip()
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        import urllib.parse
        # Kirim secret_token agar Telegram menyertakannya di setiap webhook request
        secret_token = _generate_webhook_secret(bot_token)
        params = {'url': webhook_url, 'secret_token': secret_token}
        data = urllib.parse.urlencode(params).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))

        if result.get('ok'):
            return JsonResponse({
                'success': True,
                'message': f'Webhook berhasil terdaftar: {webhook_url}'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': f'Gagal: {result.get("description", "Unknown error")}'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })
