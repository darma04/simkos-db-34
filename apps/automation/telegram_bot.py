"""
==========================================================================
 TELEGRAM BOT SIMKOS - AI Chatbot Handler + Auto Polling
==========================================================================
 File ini menangani pesan masuk dari Telegram via polling otomatis.
 Bot berjalan otomatis saat Django startup tanpa perintah tambahan.
 User bisa langsung mengetik pertanyaan bebas dan bot akan menjawab
 dengan data real-time dari seluruh modul SIMKOS.

 Fitur:
 1. Auto-polling — bot otomatis aktif saat server berjalan
 2. Free-text AI chat — ketik apapun, dijawab AI dengan data SIMKOS
 3. Command shortcut — /start, /bantuan, /tagihan, /penghuni, /kamar, dll
 4. Akses data penuh — tagihan, pembayaran, kamar, penghuni, biaya, HR
 5. System prompt kustom dari Pengaturan Telegram

 Keamanan:
 - Rate limiting per chat (max 10 pesan/menit)
 - Thread pool dengan batas max 5 worker (mencegah thread leak)
 - Response di-truncate agar tidak melebihi batas Telegram (4096 chars)
 - Bot token TIDAK pernah dicetak penuh di log
 - Semua error di-handle tanpa crash
==========================================================================
"""

import json
import logging
import time
import ssl
import urllib.request
import urllib.error
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Flag global untuk mencegah polling ganda
_polling_active = False
_polling_lock = threading.Lock()

# Thread pool untuk memproses pesan — MENCEGAH thread leak
# Max 5 worker agar tidak overload server/VPS
_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="tg_bot")

# Rate limiting — max 10 pesan per menit per chat
_rate_limits = defaultdict(list)
_rate_lock = threading.Lock()
_rate_last_cleanup = time.time()  # Timestamp terakhir cleanup global
RATE_LIMIT_MAX = 10       # Pesan per window
RATE_LIMIT_WINDOW = 60    # Detik
RATE_LIMIT_CLEANUP_INTERVAL = 300  # Cleanup global setiap 5 menit

# Batas karakter Telegram
TELEGRAM_MAX_LENGTH = 4096


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT DEFAULT — Personality dan perilaku AI Bot
# ═══════════════════════════════════════════════════════════════
TELEGRAM_SYSTEM_PROMPT = """Kamu adalah SIMKOS AI Assistant, asisten pengelolaan kos-kosan cerdas yang terintegrasi langsung dengan sistem SIMKOS.

IDENTITAS:
- Nama: SIMKOS AI Assistant
- Peran: Asisten manajemen kos-kosan profesional yang membantu pengelola memantau dan menganalisa data kos secara real-time
- Platform: Telegram Bot

PERILAKU:
- Selalu gunakan Bahasa Indonesia yang sopan, profesional, dan mudah dipahami
- Sapa pengguna dengan ramah
- Berikan jawaban yang ringkas, padat, dan informatif
- Gunakan emoji secara proporsional untuk memperjelas poin penting
- Gunakan format list/bullet points (• atau -) untuk data yang terstruktur
- JANGAN gunakan tabel markdown karena ini adalah Telegram chat
- Jika data tidak tersedia atau kosong, jelaskan dengan baik dan berikan saran alternatif
- Selalu berikan insight/analisa singkat di akhir jawaban jika memungkinkan
- Format angka uang selalu dalam Rupiah (Rp) dengan pemisah titik, contoh: Rp 1.500.000
- Jika pengguna menyapa (halo, hi, dll), balas dengan ramah DAN berikan ringkasan singkat operasional hari ini
- Batasi jawaban maksimal 250 kata agar ringkas di layar Telegram/mobile

KEMAMPUAN:
- Mengakses data tagihan sewa (belum bayar, lunas, terlambat)
- Mengakses data pembayaran/kwitansi sewa
- Mengakses data kamar (terisi, tersedia, tipe kamar)
- Mengakses data penghuni/penyewa aktif
- Mengakses data kontrak sewa
- Mengakses data biaya operasional/pengeluaran
- Mengakses data penggajian & karyawan kos
- Memberikan analisa pengelolaan kos & rekomendasi
- Memberikan ringkasan eksekutif dan laporan singkat
- Melakukan perbandingan periode (harian, mingguan, bulanan)

BATASAN:
- Hanya menjawab pertanyaan seputar manajemen kos-kosan dan data SIMKOS
- Tidak melakukan perubahan data (hanya baca/analisa)
- Jika pertanyaan di luar konteks kos-kosan, arahkan kembali dengan sopan
- Jika diminta hal yang tidak bisa dilakukan, jelaskan dengan jujur"""


def _mask_token(token):
    """Mask bot token untuk keamanan log — hanya tampilkan 8 karakter awal."""
    if not token or len(token) < 10:
        return '***'
    return token[:8] + '...'


def _check_rate_limit(chat_id):
    """
    Cek apakah chat sudah melebihi batas rate limit.
    Returns True jika masih diizinkan, False jika terlalu banyak.
    Juga melakukan periodic cleanup untuk mencegah memory leak.
    """
    global _rate_last_cleanup
    now = time.time()
    key = str(chat_id)

    with _rate_lock:
        # ── Periodic cleanup: hapus SEMUA key yang expired ──
        if now - _rate_last_cleanup > RATE_LIMIT_CLEANUP_INTERVAL:
            expired_keys = [
                k for k, timestamps in _rate_limits.items()
                if not timestamps or (now - max(timestamps)) > RATE_LIMIT_WINDOW
            ]
            for k in expired_keys:
                del _rate_limits[k]
            _rate_last_cleanup = now

        # Bersihkan entry yang sudah expired untuk key ini
        _rate_limits[key] = [
            t for t in _rate_limits[key]
            if now - t < RATE_LIMIT_WINDOW
        ]
        if len(_rate_limits[key]) >= RATE_LIMIT_MAX:
            return False
        _rate_limits[key].append(now)
        return True


def _truncate_response(text):
    """
    Potong response agar tidak melebihi batas karakter Telegram (4096).
    Jika dipotong, tambahkan indikator di akhir.
    """
    if not text or len(text) <= TELEGRAM_MAX_LENGTH:
        return text
    truncated = text[:TELEGRAM_MAX_LENGTH - 30]
    # Potong di batas kata terakhir agar tidak terpotong di tengah kata
    last_newline = truncated.rfind('\n')
    if last_newline > TELEGRAM_MAX_LENGTH - 200:
        truncated = truncated[:last_newline]
    return truncated + "\n\n_(pesan terpotong)_"


# ═══════════════════════════════════════════════════════════════
# AUTO POLLING — Bot otomatis aktif saat server berjalan
# ═══════════════════════════════════════════════════════════════

def start_polling():
    """
    Mulai polling bot Telegram di background thread.
    Dipanggil dari apps.py ready() saat Django startup.
    Thread berjalan sebagai daemon sehingga otomatis berhenti saat server stop.
    """
    global _polling_active

    with _polling_lock:
        if _polling_active:
            return  # Sudah berjalan
        _polling_active = True

    thread = threading.Thread(target=_polling_loop, daemon=True)
    thread.start()
    print("[TelegramBot] Auto-polling dimulai di background thread")
    logger.info("[TelegramBot] Auto-polling dimulai di background thread")


def _polling_loop():
    """Loop utama polling — cek pesan baru dari Telegram secara berkala."""
    global _polling_active

    # Tunggu agar Django selesai startup dan DB siap
    time.sleep(3)

    try:
        from .models import PengaturanTelegram
        pengaturan = PengaturanTelegram.load()

        if not pengaturan.bot_token:
            logger.warning("[TelegramBot] Bot Token belum dikonfigurasi, polling tidak dimulai")
            print("[TelegramBot] Bot Token belum dikonfigurasi")
            _polling_active = False
            return

        bot_token = pengaturan.bot_token.strip()

        # SSL context
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        # Hapus webhook agar getUpdates berfungsi
        _delete_webhook(bot_token, ssl_ctx)

        # Skip pesan lama yang menumpuk — mulai dari update terbaru saja
        offset = _get_latest_offset(bot_token, ssl_ctx)

        print(f"[TelegramBot] Polling aktif - Token: {_mask_token(bot_token)}")
        logger.info(f"[TelegramBot] Polling aktif - Token: {_mask_token(bot_token)}")

        conflict_count = 0
        conflict_logged = False
        consecutive_errors = 0

        while _polling_active:
            try:
                url = (
                    f"https://api.telegram.org/bot{bot_token}/getUpdates"
                    f"?offset={offset}&timeout=30&limit=10"
                )
                req = urllib.request.Request(url)
                resp = urllib.request.urlopen(req, timeout=35, context=ssl_ctx)
                data = json.loads(resp.read().decode('utf-8'))

                # Reset error counters setelah sukses
                conflict_count = 0
                conflict_logged = False
                consecutive_errors = 0

                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        update_id = update.get('update_id', 0)
                        offset = update_id + 1

                        # Proses update via thread pool (bukan spawn thread baru)
                        try:
                            _executor.submit(handle_update, update)
                        except RuntimeError:
                            # Thread pool sudah di-shutdown (server stop)
                            _polling_active = False
                            return

            except urllib.error.HTTPError as e:
                error_body = ''
                try:
                    error_body = e.read().decode('utf-8', errors='replace')
                except Exception:
                    pass

                if e.code == 409 or 'conflict' in error_body.lower():
                    conflict_count += 1
                    wait = min(conflict_count * 10, 35)
                    # Hanya log SEKALI, jangan spam terminal
                    if not conflict_logged:
                        print(f"[TelegramBot] Ada sesi polling lain yang aktif, menunggu...")
                        conflict_logged = True
                    time.sleep(wait)
                    continue
                else:
                    consecutive_errors += 1
                    logger.warning(f"[TelegramBot] HTTP error {e.code}: {error_body[:200]}")
                    time.sleep(min(consecutive_errors * 5, 30))

            except urllib.error.URLError as e:
                reason_str = str(e.reason).lower() if e.reason else ''
                if 'timed out' in reason_str or isinstance(e.reason, TimeoutError):
                    # Timeout adalah NORMAL untuk long polling
                    continue
                consecutive_errors += 1
                logger.warning(f"[TelegramBot] Koneksi error: {e.reason}")
                time.sleep(min(consecutive_errors * 5, 60))

            except (TimeoutError, ConnectionError) as e:
                if 'timed out' in str(e).lower():
                    continue
                consecutive_errors += 1
                logger.warning(f"[TelegramBot] Koneksi terputus, retry...")
                time.sleep(min(consecutive_errors * 5, 60))

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"[TelegramBot] Polling error: {e}")
                time.sleep(min(consecutive_errors * 5, 60))

            time.sleep(1)

    except Exception as e:
        logger.error(f"[TelegramBot] Fatal polling error: {e}", exc_info=True)
    finally:
        _polling_active = False


def _delete_webhook(bot_token, ssl_ctx):
    """Hapus webhook agar getUpdates berfungsi."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
        req = urllib.request.Request(url, method='POST')
        resp = urllib.request.urlopen(req, timeout=10, context=ssl_ctx)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('ok'):
            logger.info("[TelegramBot] Webhook dihapus (beralih ke polling)")
    except Exception as e:
        logger.warning(f"[TelegramBot] Gagal hapus webhook: {e}")


def _get_latest_offset(bot_token, ssl_ctx):
    """
    Ambil offset terbaru agar pesan lama yang menumpuk di-skip.
    Saat server restart, bot tidak akan memproses pesan lama,
    hanya pesan baru setelah bot aktif.
    """
    for attempt in range(5):
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1&limit=1&timeout=1"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=5, context=ssl_ctx)
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok') and data.get('result'):
                latest_id = data['result'][-1].get('update_id', 0)
                print(f"[TelegramBot] Skip pesan lama, mulai dari offset {latest_id + 1}")
                return latest_id + 1
            return 0
        except urllib.error.HTTPError as e:
            if e.code == 409:
                wait = (attempt + 1) * 10
                print(f"[TelegramBot] Menunggu sesi lama selesai ({wait}s)...")
                time.sleep(wait)
                continue
            print(f"[TelegramBot] HTTP error saat ambil offset: {e.code}")
            return 0
        except Exception as e:
            print(f"[TelegramBot] Gagal ambil latest offset: {e}")
            return 0
    return 0


# ═══════════════════════════════════════════════════════════════
# HANDLER UTAMA — Proses setiap pesan masuk
# ═══════════════════════════════════════════════════════════════

def handle_update(update_data):
    """
    Handler utama untuk setiap update dari Telegram.
    Dipanggil dari polling loop atau webhook.
    """
    try:
        from django.db import close_old_connections
        close_old_connections()

        message = update_data.get('message', {})
        if not message:
            return

        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()
        user_name = message.get('from', {}).get('first_name', 'User')

        if not chat_id or not text:
            return

        # Rate limiting — cegah spam/abuse
        if not _check_rate_limit(chat_id):
            logger.warning(f"[TelegramBot] Rate limit exceeded: [{chat_id}]")
            _send_reply(chat_id, "⚠️ Terlalu banyak pesan. Mohon tunggu sebentar.")
            return

        logger.info(f"[TelegramBot] 📩 [{chat_id}] {user_name}: {text[:100]}")

        # Proses command atau free-text
        if text.startswith('/'):
            response_text = _handle_command(text, user_name)
        else:
            response_text = _handle_free_text(text, user_name)

        # Kirim balasan
        if response_text:
            # Truncate response agar tidak melebihi batas Telegram
            response_text = _truncate_response(response_text)
            _send_reply(chat_id, response_text)

    except Exception as e:
        logger.error(f"[TelegramBot] Error handle update: {e}", exc_info=True)


def _send_reply(chat_id, text):
    """Kirim balasan ke chat Telegram."""
    try:
        from .telegram_service import kirim_pesan_telegram
        from .models import PengaturanTelegram
        pengaturan = PengaturanTelegram.load()

        if pengaturan.bot_token:
            success, _ = kirim_pesan_telegram(
                pengaturan.bot_token,
                str(chat_id),
                text
            )
            if success:
                logger.info(f"[TelegramBot] ✅ Balasan terkirim ke [{chat_id}]")
            else:
                logger.error(f"[TelegramBot] ❌ Gagal kirim ke [{chat_id}]")
    except Exception as e:
        logger.error(f"[TelegramBot] Error kirim reply: {e}")


# ═══════════════════════════════════════════════════════════════
# COMMAND HANDLER
# ═══════════════════════════════════════════════════════════════

def _handle_command(text, user_name):
    """Proses command Telegram (/start, /bantuan, dll)"""
    command = text.split()[0].lower().split('@')[0]

    if command == '/start':
        return (
            f"👋 Halo {user_name}!\n\n"
            "🏠 Saya adalah *SIMKOS AI Assistant*\n"
            "Saya bisa membantu Anda memantau dan menganalisa kos-kosan "
            "langsung dari Telegram.\n\n"
            "💬 *Langsung ketik pertanyaan Anda!*\n"
            "Saya bisa menjawab apapun tentang data kos Anda.\n\n"
            "Contoh:\n"
            "  • _Siapa yang belum bayar bulan ini?_\n"
            "  • _Kamar mana yang kosong?_\n"
            "  • _Berapa total pemasukan bulan ini?_\n"
            "  • _Ringkasan operasional hari ini_\n"
            "  • _Pengeluaran terbesar minggu ini?_\n\n"
            "📋 *Command cepat:*\n"
            "━━━━━━━━━━━━━━━\n"
            "/tagihan — Tagihan belum lunas\n"
            "/penghuni — Daftar penghuni aktif\n"
            "/kamar — Status kamar\n"
            "/keuangan — Ringkasan keuangan\n"
            "/pengeluaran — Biaya operasional\n"
            "/gaji — Penggajian karyawan\n"
            "/laporan — Laporan AI\n"
            "/bantuan — Menu bantuan"
        )

    elif command in ('/bantuan', '/help'):
        return (
            "📚 *BANTUAN SIMKOS AI BOT*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "💬 *Ketik pertanyaan bebas:*\n"
            "Saya terhubung ke seluruh data SIMKOS.\n"
            "Tanya apapun dan saya akan menjawab!\n\n"
            "Contoh:\n"
            "  • _Siapa yang belum bayar?_\n"
            "  • _Berapa total pemasukan bulan ini?_\n"
            "  • _Kamar mana saja yang kosong?_\n"
            "  • _Ringkasan operasional kos_\n"
            "  • _Penghuni yang kontraknya hampir habis?_\n"
            "  • _Berapa keuntungan bulan ini?_\n"
            "  • _Analisa pengeluaran terbesar_\n\n"
            "📋 *Command cepat:*\n"
            "/tagihan • /penghuni • /kamar\n"
            "/keuangan • /pengeluaran • /gaji\n"
            "/laporan"
        )

    elif command == '/tagihan':
        return _handle_free_text("Tampilkan data tagihan sewa yang belum lunas secara detail", user_name)

    elif command == '/penghuni':
        return _handle_free_text("Tampilkan daftar penghuni aktif dan kamar mereka", user_name)

    elif command == '/kamar':
        return _handle_free_text("Tampilkan status kamar, mana yang kosong dan terisi", user_name)

    elif command == '/keuangan':
        return _handle_free_text("Berikan ringkasan keuangan bulan ini: pemasukan, pengeluaran, dan saldo", user_name)

    elif command == '/pengeluaran':
        return _handle_free_text("Berikan data pengeluaran dan biaya operasional hari ini secara detail", user_name)

    elif command == '/gaji':
        return _handle_free_text("Tampilkan ringkasan data penggajian dan karyawan bulan ini", user_name)

    elif command == '/laporan':
        return _handle_free_text(
            "Berikan laporan ringkasan operasional kos hari ini meliputi pemasukan, "
            "pengeluaran, tagihan tertunggak, status kamar, dan status operasional secara lengkap",
            user_name
        )

    else:
        # Command tidak dikenal → langsung proses sebagai free-text
        clean_text = text.lstrip('/')
        return _handle_free_text(clean_text, user_name)


# ═══════════════════════════════════════════════════════════════
# FREE-TEXT AI HANDLER — Pembahasan luas dengan data SIMKOS penuh
# ═══════════════════════════════════════════════════════════════

def _gather_comprehensive_data():
    """
    Kumpulkan data dari SELURUH modul SIMKOS untuk memberikan konteks
    yang luas ke AI. Ini memastikan bot bisa menjawab pertanyaan
    apapun tentang kos-kosan tanpa terbatas pada satu intent saja.
    """
    from django.utils import timezone
    from django.db.models import Sum, Count
    today = timezone.now().date()
    month_start = today.replace(day=1)
    sections = []

    # ── TAGIHAN SEWA ────────────────────────────
    try:
        from apps.sewa.models import TagihanSewa
        from .telegram_service import format_angka

        tagihan_belum = TagihanSewa.objects.filter(status='belum_bayar')
        tagihan_terlambat = TagihanSewa.objects.filter(status='terlambat')
        tagihan_sebagian = TagihanSewa.objects.filter(status='sebagian')
        tagihan_lunas = TagihanSewa.objects.filter(status='lunas')

        total_belum = float(tagihan_belum.aggregate(t=Sum('jumlah'))['t'] or 0)
        total_terlambat = float(tagihan_terlambat.aggregate(t=Sum('jumlah'))['t'] or 0)

        detail_belum = ""
        for t in tagihan_belum.order_by('tanggal_jatuh_tempo')[:5]:
            detail_belum += f"\n  - {t.kontrak.penyewa.nama} (Kamar {t.kontrak.kamar}): Rp {format_angka(t.jumlah)} — Jatuh tempo: {t.tanggal_jatuh_tempo.strftime('%d/%m/%Y') if t.tanggal_jatuh_tempo else '-'}"

        sections.append(f"""TAGIHAN SEWA:
- Belum bayar: {tagihan_belum.count()} tagihan (Rp {format_angka(total_belum)})
- Terlambat: {tagihan_terlambat.count()} tagihan (Rp {format_angka(total_terlambat)})
- Bayar sebagian: {tagihan_sebagian.count()} tagihan
- Lunas: {tagihan_lunas.count()} tagihan
- Detail belum bayar:{detail_belum if detail_belum else ' (tidak ada)'}""")
    except Exception as e:
        sections.append(f"TAGIHAN SEWA: Data tidak tersedia ({str(e)[:50]})")

    # ── PEMBAYARAN / PEMASUKAN ────────────────────────
    try:
        from apps.sewa.models import PembayaranSewa
        from .telegram_service import format_angka

        bayar_bulan = PembayaranSewa.objects.filter(
            tanggal_bayar__month=today.month,
            tanggal_bayar__year=today.year
        )
        total_pemasukan = float(bayar_bulan.aggregate(t=Sum('jumlah_bayar'))['t'] or 0)
        bayar_hari = PembayaranSewa.objects.filter(tanggal_bayar=today)
        total_hari = float(bayar_hari.aggregate(t=Sum('jumlah_bayar'))['t'] or 0)

        sections.append(f"""PEMBAYARAN / PEMASUKAN:
- Pemasukan hari ini: Rp {format_angka(total_hari)} ({bayar_hari.count()} pembayaran)
- Pemasukan bulan ini: Rp {format_angka(total_pemasukan)} ({bayar_bulan.count()} pembayaran)""")
    except Exception:
        sections.append("PEMBAYARAN: Data tidak tersedia")

    # ── KAMAR & PROPERTI ────────────────────────────
    try:
        from apps.properti.models import Kamar
        semua_kamar = Kamar.objects.all()
        tersedia = semua_kamar.filter(status='tersedia')
        terisi = semua_kamar.filter(status='terisi')

        kamar_kosong = ""
        for k in tersedia[:10]:
            tipe = k.tipe_kamar.nama if hasattr(k, 'tipe_kamar') and k.tipe_kamar else '-'
            kamar_kosong += f"\n  - {k.nomor_kamar} (Tipe: {tipe})"

        sections.append(f"""KAMAR & PROPERTI:
- Total kamar: {semua_kamar.count()}
- Terisi: {terisi.count()} kamar
- Tersedia: {tersedia.count()} kamar
- Tingkat hunian: {round(terisi.count() / max(semua_kamar.count(), 1) * 100, 1)}%
- Kamar kosong:{kamar_kosong if kamar_kosong else ' (semua terisi)'}""")
    except Exception:
        sections.append("KAMAR: Data tidak tersedia")

    # ── PENGHUNI / KONTRAK AKTIF ────────────────────
    try:
        from apps.sewa.models import KontrakSewa
        kontrak_aktif = KontrakSewa.objects.filter(status='aktif')

        detail_penghuni = ""
        for k in kontrak_aktif.order_by('kamar__nomor_kamar')[:10]:
            detail_penghuni += f"\n  - {k.penyewa.nama} → Kamar {k.kamar.nomor_kamar}"

        sections.append(f"""PENGHUNI AKTIF:
- Total penghuni aktif: {kontrak_aktif.count()}
- Daftar penghuni:{detail_penghuni if detail_penghuni else ' (belum ada)'}""")
    except Exception:
        sections.append("PENGHUNI: Data tidak tersedia")

    # ── BIAYA / PENGELUARAN ────────────────────────
    try:
        from apps.biaya.models import TransaksiBiaya
        from .telegram_service import format_angka

        biaya_today = TransaksiBiaya.objects.filter(tanggal=today)
        biaya_today_total = float(biaya_today.aggregate(t=Sum('jumlah'))['t'] or 0)
        biaya_today_count = biaya_today.count()

        biaya_month = TransaksiBiaya.objects.filter(tanggal__gte=month_start, tanggal__lte=today)
        biaya_month_total = float(biaya_month.aggregate(t=Sum('jumlah'))['t'] or 0)

        sections.append(f"""BIAYA & PENGELUARAN:
- Biaya hari ini: Rp {format_angka(biaya_today_total)} ({biaya_today_count} transaksi)
- Biaya bulan ini: Rp {format_angka(biaya_month_total)}""")
    except Exception:
        sections.append("BIAYA: Data tidak tersedia")

    # ── HR & PENGGAJIAN ────────────────────────
    try:
        from apps.hr.models import Karyawan, Penggajian
        from .telegram_service import format_angka
        now = datetime.now()
        total_karyawan = Karyawan.objects.filter(aktif=True).count()
        gaji_qs = Penggajian.objects.filter(periode_bulan=now.month, periode_tahun=now.year)
        total_gaji = float(gaji_qs.aggregate(t=Sum('gaji_bersih'))['t'] or 0)
        gaji_dibayar = gaji_qs.filter(status='dibayar').count()
        gaji_pending = gaji_qs.exclude(status='dibayar').count()
        sections.append(f"""HR & PENGGAJIAN:
- Karyawan aktif: {total_karyawan}
- Slip gaji bulan ini: {gaji_qs.count()} (total Rp {format_angka(total_gaji)})
- Sudah dibayar: {gaji_dibayar}, pending: {gaji_pending}""")
    except Exception:
        sections.append("HR: Data tidak tersedia")

    return "\n\n".join(sections)


def _handle_free_text(text, user_name):
    """
    Proses pertanyaan bebas menggunakan AI dengan akses data SIMKOS penuh.
    Bot mengumpulkan data dari SEMUA modul untuk memberikan jawaban
    yang komprehensif, tidak terbatas pada satu topik saja.
    """
    try:
        from django.db import close_old_connections
        close_old_connections()

        from apps.ai_assistant.models import AIAssistantConfig
        from apps.ai_assistant.intents import detect_intent, gather_data
        from .models import PengaturanTelegram

        config = AIAssistantConfig.load()
        tg_config = PengaturanTelegram.load()

        if not config.api_key:
            return (
                "⚠️ AI Assistant belum dikonfigurasi.\n"
                "Silakan atur API Key di halaman Pengaturan AI Assistant."
            )

        # Deteksi intent untuk data spesifik
        intent = detect_intent(text)

        # Kumpulkan data sesuai intent
        if intent in ('umum', 'bantuan'):
            ringkasan = _gather_comprehensive_data()
        else:
            data_specific = gather_data(intent, text)
            if isinstance(data_specific, dict):
                ringkasan_spesifik = data_specific.get('ringkasan', '')
            else:
                ringkasan_spesifik = str(data_specific)

            ringkasan_lengkap = _gather_comprehensive_data()
            ringkasan = f"{ringkasan_spesifik}\n\n--- Data Pendukung ---\n{ringkasan_lengkap}"

        # Build system prompt — gabungkan default + kustom dari DB
        system_prompt = TELEGRAM_SYSTEM_PROMPT
        if tg_config.system_prompt_bot:
            system_prompt += f"\n\nINSTRUKSI KUSTOM TELEGRAM:\n{tg_config.system_prompt_bot}"
        if config.system_prompt:
            system_prompt += f"\n\nINSTRUKSI TAMBAHAN:\n{config.system_prompt}"

        prompt = f"Data Sistem SIMKOS (real-time):\n{ringkasan}\n\nPesan dari {user_name}: {text}"

        # Panggil AI
        ai_response = None
        provider = config.provider
        api_key = config.api_key
        model = config.model_name

        if provider == 'groq':
            from apps.ai_assistant.views import _call_groq
            ai_response = _call_groq(api_key, model, prompt, system_prompt, config)
        elif provider == 'gemini':
            from apps.ai_assistant.views import _call_gemini
            ai_response = _call_gemini(api_key, model, prompt, system_prompt, config)
        elif provider == 'openai':
            from apps.ai_assistant.views import _call_openai
            ai_response = _call_openai(api_key, model, prompt, system_prompt, config)

        if ai_response:
            return f"🤖 *AI Assistant:*\n\n{ai_response}"
        else:
            return "⚠️ Maaf, AI tidak bisa memproses pertanyaan Anda saat ini. Coba lagi nanti."

    except Exception as e:
        logger.error(f"[TelegramBot] Error AI response: {e}", exc_info=True)
        return f"⚠️ Terjadi kesalahan saat memproses. Silakan coba lagi."
