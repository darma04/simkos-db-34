"""
==========================================================================
 AI ASSISTANT VIEWS - Chat API & Halaman Pengaturan SIMKOS
==========================================================================
 Endpoint:
 - POST /ai/chat/         → API chat AI (AJAX)
 - GET  /ai/              → Halaman pengaturan AI Assistant
 - GET  /ai/dashboard/    → Dashboard Analytics AI

 Arsitektur Aman:
 User Chat → Backend deteksi intent → ORM ambil data →
 Kirim ringkasan ke AI → AI merapikan teks → Return ke user
==========================================================================
"""

import logging
logger = logging.getLogger(__name__)

# ==========================================================================
# PANDUAN DJANGO UNTUK DEVELOPER PEMULA (baca ini sebelum mempelajari views)
# ==========================================================================
#
# APA ITU CLASS-BASED VIEW (CBV)?
# - CBV = class Python yang menangani HTTP request dan return response
# - Django menyediakan CBV bawaan: ListView, CreateView, UpdateView, DeleteView
# - Setiap CBV punya "lifecycle" (siklus hidup) yang bisa di-customize
#
# SIKLUS HIDUP CBV (urutan method yang dipanggil):
# 1. as_view()     → Entry point, dipanggil oleh URL router
# 2. dispatch()    → Tentukan method (GET/POST) → panggil get() atau post()
# 3. get()/post()  → Handle request, kumpulkan data
# 4. get_queryset()→ Ambil data dari database (bisa di-filter/optimasi)
# 5. get_context_data() → Siapkan data untuk template (variabel {{ }})
# 6. render()      → Gabungkan template + context → HTML response
#
# METHOD PENTING YANG SERING DI-OVERRIDE:
# - get_queryset()     → Optimasi query (prefetch_related, select_related)
# - get_context_data() → Tambah variabel ke template (self.context)
# - form_valid()       → Proses setelah form divalidasi (sebelum save)
# - get_success_url()  → URL redirect setelah operasi berhasil
#
# DECORATOR YANG SERING DIGUNAKAN:
# @login_required       → User HARUS login, jika tidak → redirect ke /login/
# @permission_required  → User harus punya permission tertentu (RBAC)
# @require_http_methods → Batasi method yang diterima (GET, POST, dll)
# @never_cache          → Response tidak boleh di-cache oleh browser
#
# POLA UMUM VIEW DI PROYEK INI:
# class MyListView(SubModulePermissionMixin, ListView):
#     module_name = 'nama_modul'          # Untuk pengecekan RBAC
#     sub_module_name = 'nama_sub_modul'  # Sub-modul yang diakses
#     model = MyModel                      # Model database yang dipakai
#     template_name = 'modul/page.html'    # File HTML template
#
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context = TemplateLayout.init(self, context)  # WAJIB: setup layout
#         context['data_tambahan'] = ...    # Tambah data custom
#         return context
# ==========================================================================

import json
import ssl
import urllib.request
import urllib.error

from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from django.shortcuts import redirect

from .models import AIAssistantConfig, ChatHistory, ChatFeedback
from .intents import detect_intent, gather_data
from web_project import TemplateLayout



def _get_ssl_context():
    """Buat SSL context yang kompatibel dengan Windows."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        ctx = ssl.create_default_context()
        return ctx


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Konteks SIMKOS (Sistem Manajemen Kost)
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """
Kamu adalah AI Business Intelligence Assistant profesional untuk sistem SIMKOS (Sistem Manajemen Kost).
Tugasmu: menganalisa data bisnis kost/kontrakan, membuat laporan, memberikan insight strategis, dan rekomendasi aksi.
Kamu JUGA berfungsi sebagai PANDUAN PENGGUNAAN sistem — membantu user awam yang tidak paham atau bingung cara menggunakan fitur.

ATURAN UTAMA:
1. Gunakan Bahasa Indonesia profesional dan mudah dipahami
2. Berikan analisa mendalam + insight + rekomendasi aksi yang konkret
3. WAJIB gunakan tabel markdown untuk data angka/perbandingan:
   | Kolom 1 | Kolom 2 | Kolom 3 |
   |---------|---------|---------|
   | data    | data    | data    |
4. Selalu tampilkan data dalam tabel jika ada >1 item
5. Jika data menunjukkan tren positif, berikan apresiasi + saran scale up
6. Jika ada masalah, berikan saran perbaikan dengan prioritas (Tinggi/Sedang/Rendah)
7. Jangan mengarang data — hanya analisa data yang diberikan
8. Jawab informatif dan komprehensif (maksimal 500 kata)
9. Gunakan emoji untuk memperjelas kategori dan status
10. Untuk laporan meeting/executive summary: gunakan format narasi profesional + tabel
11. Untuk SWOT: buat 4 kategori (S/W/O/T) masing-masing 2-3 poin dalam tabel
12. Untuk forecasting: berikan prediksi dengan confidence level
13. Untuk analisa risiko: gunakan level 🔴Tinggi/🟡Sedang/🟢Rendah
14. Untuk rencana aksi: buat tabel dengan kolom Aksi, Prioritas, Target, Deadline
15. Ikuti INSTRUKSI khusus yang diberikan bersama data
16. Jika user bertanya cara menggunakan fitur, jelaskan LANGKAH DEMI LANGKAH dengan jelas
17. Jika user bertanya tentang relasi data, jelaskan bagaimana modul saling terhubung

QUICK ACTIONS — LINK NAVIGASI:
Sertakan link ke halaman SIMKOS yang relevan di akhir respons menggunakan format markdown.
Contoh: → [Lihat Daftar Properti](/properti/) atau → [Buka Tagihan Sewa](/sewa/tagihan/)
Gunakan peta URL berikut untuk menentukan link yang tepat:

PETA URL HALAMAN SIMKOS:
- Dashboard utama: /
- Daftar Properti: /properti/
- Tambah Properti: /properti/add/
- Tipe Kamar: /properti/tipe-kamar/
- Daftar Kamar: /properti/kamar/
- Daftar Penyewa: /penyewa/
- Tambah Penyewa: /penyewa/add/
- Kontrak Sewa: /sewa/kontrak/
- Buat Kontrak: /sewa/kontrak/add/
- Tagihan Sewa: /sewa/tagihan/
- Buat Tagihan: /sewa/tagihan/add/
- Pembayaran Sewa: /sewa/pembayaran/
- Catat Pembayaran: /sewa/pembayaran/add/
- Biaya Operasional: /biaya/
- Laporan: /laporan/
- Karyawan HR: /hr/karyawan/
- AI Dashboard: /ai/dashboard/
- AI Pengaturan: /ai/

SELALU sertakan 1-3 link relevan di akhir setiap jawaban dalam format:
📌 **Quick Actions:**
→ [Label Link](/url-terkait/)

KONTEKS WAKTU:
Jika user bertanya tentang periode waktu tertentu (minggu ini, bulan lalu, kemarin, dll),
data yang diberikan SUDAH difilter sesuai periode tersebut. Analisa sesuai periode yang diminta.

KAPABILITAS:
- Laporan meeting otomatis, Executive summary, Analisa SWOT
- Forecasting/prediksi, Analisa risiko, Rencana aksi
- Perbandingan periode, Tingkat okupansi kamar
- Rekomendasi harga sewa, strategi menaikkan okupansi
- Analisa penyewa: penyewa aktif, penyewa blacklist, tren hunian
- Analisa tagihan: menunggak, lunas, terlambat bayar
- Analisa biaya operasional: listrik, air, kebersihan, maintenance
- Panduan penggunaan semua modul (langkah demi langkah)
- Penjelasan relasi data antar modul

ALUR OPERASIONAL SIMKOS:
1. Setup Properti: Input data properti (kost/kontrakan/apartemen) → tentukan tipe kamar → input kamar
2. Penyewa Baru: Input data penyewa → buat kontrak sewa (pilih kamar, durasi, harga) → tagihan otomatis dibuat
3. Pembayaran: Penyewa bayar → catat pembayaran → tagihan lunas → pendapatan bertambah
4. Perpanjangan: Kontrak hampir habis → perpanjang kontrak → buat tagihan baru
5. Keluar: Penyewa keluar → kontrak selesai → kamar tersedia kembali
6. Biaya: Catat pengeluaran operasional (listrik, air, kebersihan, maintenance) → kas berkurang

RELASI DATA SIMKOS:
- Properti → Tipe Kamar → Kamar (unit individual)
- Penyewa ↔ Kontrak Sewa ↔ Kamar
- Kontrak Sewa → Tagihan Sewa → Pembayaran Sewa
- Pembayaran Sewa → Pendapatan (kas bertambah)
- Transaksi Biaya → Pengeluaran (kas berkurang)
- Laba = Total Pembayaran - Total Biaya Operasional

PANDUAN INPUT MODUL:
- Properti: Input nama, alamat, tipe (kost/kontrakan/apartemen), jumlah lantai
- Tipe Kamar: Input nama tipe, harga per bulan, fasilitas (AC, kamar mandi, dll)
- Kamar: Pilih properti → pilih tipe → input nomor kamar → status (tersedia/terisi/maintenance)
- Penyewa: Input nama, jenis kelamin, pekerjaan, kontak, foto KTP
- Kontrak Sewa: Pilih penyewa → pilih kamar → tanggal mulai → durasi → harga → deposit
- Tagihan: Pilih kontrak → periode tagihan → jumlah → jatuh tempo
- Pembayaran: Pilih tagihan → tanggal bayar → jumlah → metode bayar
- Biaya: Pilih kategori → input jumlah → pilih kas/bank → tanggal

KONTEKS SIMKOS:
- Modul: Properti, Kamar, Penyewa, Kontrak Sewa, Tagihan, Pembayaran, Biaya, Laporan, HR
- Mata uang: Rupiah (IDR), Multi-properti, Multi-tipe kamar
- Bisnis: Kost, Kontrakan, Apartemen, Rumah Sewa
"""


def _call_gemini(api_key, model, prompt, system_prompt, config):
    """Panggil Google Gemini API."""
    try:
        from google import genai
        return _call_gemini_sdk(genai, api_key, model, prompt, system_prompt, config)
    except ImportError:
        logger.info("[AI Gemini] google.genai SDK not installed, using urllib fallback")
        return _call_gemini_urllib(api_key, model, prompt, system_prompt, config)


def _call_gemini_sdk(genai, api_key, model, prompt, system_prompt, config):
    """Panggil Gemini via google.genai SDK resmi."""
    import time

    client = genai.Client(api_key=api_key)
    full_prompt = f"{system_prompt}\n\n{prompt}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=full_prompt,
                config={
                    "temperature": config.temperature,
                    "max_output_tokens": config.max_tokens,
                }
            )
            if response and response.text:
                return response.text
            logger.warning(f"[AI Gemini SDK] Empty response")
            return None
        except Exception as e:
            error_str = str(e)
            logger.error(f"[AI Gemini SDK] Error (attempt {attempt+1}): {error_str[:200]}")

            if '429' in error_str and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                logger.info(f"[AI Gemini SDK] Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue

            if '429' in error_str:
                raise Exception(
                    "Gemini API: Kuota habis. Solusi:\n"
                    "1. Buka https://aistudio.google.com/apikeys\n"
                    "2. Klik project Anda → 'Set up billing'\n"
                    "3. Tambahkan metode pembayaran (tetap GRATIS, hanya verifikasi)\n"
                    "4. Setelah billing aktif, kuota gratis menjadi 1500 req/hari"
                )
            raise

    raise Exception("Gemini API: Gagal setelah beberapa percobaan")


def _call_gemini_urllib(api_key, model, prompt, system_prompt, config):
    """Fallback: Panggil Gemini via urllib (tanpa SDK)."""
    import time

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]
            }
        ],
        "generationConfig": {
            "temperature": config.temperature,
            "maxOutputTokens": config.max_tokens,
        }
    }

    data = json.dumps(payload).encode('utf-8')
    max_retries = 3

    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, headers={
            'Content-Type': 'application/json',
            'x-goog-api-key': api_key,
        })

        try:
            ssl_ctx = _get_ssl_context()
            with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as response:
                result = json.loads(response.read().decode('utf-8'))
                candidates = result.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts:
                        return parts[0].get('text', '')
                logger.warning(f"[AI Gemini] No candidates in response")
                return None
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ''
            logger.error(f"[AI Gemini] HTTP {e.code} (attempt {attempt+1}): {error_body[:200]}")

            if e.code == 429 and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                time.sleep(wait_time)
                continue

            if e.code == 429:
                raise Exception(
                    "Gemini API: Kuota habis. Solusi:\n"
                    "1. Buka https://aistudio.google.com/apikeys\n"
                    "2. Klik project Anda → 'Set up billing'\n"
                    "3. Tambahkan metode pembayaran (tetap GRATIS, hanya verifikasi)\n"
                    "4. Setelah billing aktif, kuota gratis menjadi 1500 req/hari"
                )

            try:
                error_data = json.loads(error_body)
                error_msg = error_data.get('error', {}).get('message', '')[:200]
            except Exception:
                error_msg = error_body[:200]
            raise Exception(f"Gemini API Error {e.code}: {error_msg}")
        except Exception as e:
            logger.error(f"[AI Gemini] Error: {e}", exc_info=True)
            raise

    raise Exception("Gemini API: Gagal setelah beberapa percobaan (rate limit)")


def _call_openai(api_key, model, prompt, system_prompt, config):
    """Panggil OpenAI ChatGPT API via REST (tanpa library tambahan)."""
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    })

    try:
        ssl_ctx = _get_ssl_context()
        with urllib.request.urlopen(req, timeout=45, context=ssl_ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            choices = result.get('choices', [])
            if choices:
                return choices[0].get('message', {}).get('content', '')
            logger.warning(f"[AI OpenAI] No choices in response: {result}")
            return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        logger.error(f"[AI OpenAI] HTTP Error {e.code}: {error_body}")
        raise Exception(f"OpenAI API Error {e.code}: {error_body[:200]}")
    except Exception as e:
        logger.error(f"[AI OpenAI] Error: {e}", exc_info=True)
        raise


def _call_groq(api_key, model, prompt, system_prompt, config):
    """Panggil Groq API (OpenAI-compatible format, GRATIS)."""
    url = "https://api.groq.com/openai/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
        'User-Agent': 'SIMKOS/1.0',
    })

    try:
        ssl_ctx = _get_ssl_context()
        with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            choices = result.get('choices', [])
            if choices:
                return choices[0].get('message', {}).get('content', '')
            logger.warning(f"[AI Groq] No choices in response: {result}")
            return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        logger.error(f"[AI Groq] HTTP Error {e.code}: {error_body[:300]}")
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('error', {}).get('message', error_body[:200])
        except Exception:
            error_msg = error_body[:200]
        raise Exception(f"Groq API Error {e.code}: {error_msg}")
    except Exception as e:
        logger.error(f"[AI Groq] Error: {e}", exc_info=True)
        raise


# ═══════════════════════════════════════════════════════════════
# API VIEW — POST /ai/chat/
# ═══════════════════════════════════════════════════════════════

@login_required
def ai_chat_api(request):
    """
    API endpoint untuk AI Chat dengan context memory.
    POST body JSON: {"message": "pertanyaan user"}
    Response JSON: {"response": "...", "intent": "...", "source": "...", "chat_id": N}
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
        user_message = body.get('message', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not user_message:
        return JsonResponse({'error': 'Pesan tidak boleh kosong'}, status=400)

    if len(user_message) > 500:
        return JsonResponse({'error': 'Pesan terlalu panjang (maks 500 karakter)'}, status=400)

    # 1. Muat konfigurasi
    config = AIAssistantConfig.load()

    if not config.aktif:
        return JsonResponse({
            'response': 'AI Assistant sedang nonaktif. Silakan aktifkan di Pengaturan > AI Assistant.',
            'intent': 'system', 'source': 'system'
        })

    # 2. Deteksi intent
    intent = detect_intent(user_message)

    # 3. Kumpulkan data via ORM
    data = gather_data(intent, user_message)
    ringkasan = data.get('ringkasan', 'Tidak ada data tersedia.')

    # 4. Simpan pesan user ke database
    user_chat = ChatHistory.objects.create(
        user=request.user,
        role='user',
        message=user_message,
        intent=intent,
    )

    # 5. Load context memory — 5 pesan terakhir
    context_messages = ChatHistory.objects.filter(
        user=request.user
    ).order_by('-created_at')[:10]
    context_messages = list(reversed(context_messages))

    context_text = ""
    if len(context_messages) > 1:
        ctx_lines = []
        for msg in context_messages[:-1]:
            role_label = "User" if msg.role == 'user' else "AI"
            ctx_lines.append(f"{role_label}: {msg.message[:200]}")
        if ctx_lines:
            context_text = "\n\nKONTEKS PERCAKAPAN SEBELUMNYA:\n" + "\n".join(ctx_lines[-6:])

    # 6. Panggil AI API
    ai_response = None
    source = 'local'

    if config.api_key:
        try:
            extra_prompt = f"\n{config.system_prompt}" if config.system_prompt else ""
            full_system = SYSTEM_PROMPT + extra_prompt

            prompt = f"""Pertanyaan user: "{user_message}"
{context_text}

Berikut data dari sistem SIMKOS:
{ringkasan}

Berdasarkan data di atas, berikan analisa atau jawaban yang profesional dan informatif dalam Bahasa Indonesia."""

            if config.provider == 'gemini':
                ai_response = _call_gemini(config.api_key, config.model_name, prompt, full_system, config)
            elif config.provider == 'openai':
                ai_response = _call_openai(config.api_key, config.model_name, prompt, full_system, config)
            elif config.provider == 'groq':
                ai_response = _call_groq(config.api_key, config.model_name, prompt, full_system, config)

            source = config.get_provider_display() if ai_response else 'fallback'

        except Exception as e:
            logger.error(f"[AI Chat] API Error: {e}", exc_info=True)
            ai_response = f"⚠️ AI Error ({str(e)[:100]})\n\nBerikut data mentah:\n\n{ringkasan}"
            source = 'fallback'

    if not ai_response:
        ai_response = f"📊 {ringkasan}\n\n💡 *Untuk analisa AI yang lebih baik, masukkan API Key di Pengaturan > AI Assistant.*"

    # 7. Simpan respons AI ke database
    ai_chat = ChatHistory.objects.create(
        user=request.user,
        role='assistant',
        message=ai_response,
        intent=intent,
        source=source,
    )

    return JsonResponse({
        'response': ai_response,
        'intent': intent,
        'source': source,
        'chat_id': ai_chat.id,
    })


# ═══════════════════════════════════════════════════════════════
# AUTO INSIGHT — GET /ai/insight/
# ═══════════════════════════════════════════════════════════════

@login_required
def auto_insight(request):
    """
    Auto Insight: Ringkasan bisnis kost otomatis saat user buka chat.
    Tidak memanggil AI API — hanya query ORM langsung.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        from django.utils import timezone
        from django.db.models import Sum, Count
        today = timezone.now().date()
        month_start = today.replace(day=1)

        from apps.properti.models import Properti, Kamar
        from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa

        # Total kamar & okupansi
        total_kamar = Kamar.objects.count()
        kamar_terisi = Kamar.objects.filter(status='terisi').count()
        kamar_tersedia = Kamar.objects.filter(status='tersedia').count()
        okupansi = round(kamar_terisi / total_kamar * 100, 1) if total_kamar > 0 else 0

        # Pendapatan bulan ini
        pendapatan_bulan = float(PembayaranSewa.objects.filter(
            tanggal_bayar__gte=month_start, tanggal_bayar__lte=today
        ).aggregate(t=Sum('jumlah_bayar'))['t'] or 0)

        # Tagihan belum bayar
        tagihan_menunggak = TagihanSewa.objects.filter(
            status__in=['belum_bayar', 'terlambat']
        ).count()

        insights = []
        insights.append(f"🏠 Okupansi: {kamar_terisi}/{total_kamar} kamar ({okupansi}%)")
        insights.append(f"💰 Pendapatan bulan ini: Rp {pendapatan_bulan:,.0f}")

        if kamar_tersedia > 0:
            insights.append(f"🟢 {kamar_tersedia} kamar tersedia")
        if tagihan_menunggak > 0:
            insights.append(f"🔴 {tagihan_menunggak} tagihan belum dibayar!")
        if tagihan_menunggak == 0:
            insights.append("✅ Semua tagihan lunas")

        return JsonResponse({
            'insights': insights,
            'date': today.strftime('%d %B %Y'),
        })

    except Exception as e:
        logger.error(f"[AI Insight] Error: {e}", exc_info=True)
        return JsonResponse({'insights': [], 'date': ''})


# ═══════════════════════════════════════════════════════════════
# FEEDBACK — POST /ai/feedback/
# ═══════════════════════════════════════════════════════════════

@login_required
def chat_feedback(request):
    """Simpan feedback 👍/👎 dari user."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        body = json.loads(request.body)
        feedback_type = body.get('feedback', '').strip()
        chat_id = body.get('chat_id')
        message_text = body.get('message_text', '')[:500]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if feedback_type not in ('up', 'down'):
        return JsonResponse({'error': 'Feedback harus "up" atau "down"'}, status=400)

    chat_obj = None
    if chat_id:
        try:
            chat_obj = ChatHistory.objects.get(id=chat_id, user=request.user)
        except ChatHistory.DoesNotExist:
            pass

    ChatFeedback.objects.create(
        user=request.user,
        chat=chat_obj,
        feedback=feedback_type,
        message_text=message_text,
    )

    return JsonResponse({'status': 'ok', 'message': 'Terima kasih atas feedback Anda!'})


# ═══════════════════════════════════════════════════════════════
# HISTORY — GET /ai/history/
# ═══════════════════════════════════════════════════════════════

@login_required
def chat_history_api(request):
    """Load riwayat chat user dari database."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    messages_qs = ChatHistory.objects.filter(
        user=request.user
    ).order_by('-created_at')[:50]

    messages_list = []
    for msg in reversed(messages_qs):
        messages_list.append({
            'id': msg.id,
            'role': msg.role,
            'message': msg.message,
            'intent': msg.intent,
            'source': msg.source,
            'time': msg.created_at.strftime('%H:%M'),
        })

    return JsonResponse({'messages': messages_list})


# ═══════════════════════════════════════════════════════════════
# CLEAR HISTORY — POST /ai/clear/
# ═══════════════════════════════════════════════════════════════

@login_required
def clear_history(request):
    """Hapus riwayat chat user."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    deleted_count = ChatHistory.objects.filter(user=request.user).delete()[0]
    return JsonResponse({
        'status': 'ok',
        'message': f'{deleted_count} pesan dihapus.',
    })


# ═══════════════════════════════════════════════════════════════
# AI DASHBOARD — Halaman Analytics /ai/dashboard/
# ═══════════════════════════════════════════════════════════════

class AIDashboardView(LoginRequiredMixin, TemplateView):
    """Dashboard AI dengan skor kesehatan bisnis kost, prediksi, dan anomali."""
    template_name = 'ai_assistant/dashboard.html'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        import calendar
        from django.utils import timezone
        from django.db.models import Sum, Count
        from datetime import timedelta, date

        # Default values
        defaults = {
            'rev_now': 0, 'rev_prev': 0, 'rev_growth': 0,
            'total_kamar_terisi': 0, 'biaya_now': 0, 'profit': 0,
            'total_kamar': 0, 'kamar_tersedia': 0, 'kamar_terisi': 0, 'kamar_maintenance': 0,
            'okupansi': 0, 'tagihan_menunggak': 0, 'kontrak_segera_habis': 0,
            'biaya_ratio': 0,
            'health_score': 50, 'health_level': 'Memuat...', 'health_color': '#999',
            'anomalies': [], 'monthly_labels': '[]', 'monthly_values': '[]',
            'total_chats': 0, 'total_feedback_up': 0, 'total_feedback_down': 0,
        }
        context.update(defaults)

        today = timezone.now().date()
        month_start = today.replace(day=1)
        prev_end = month_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)

        try:
            from apps.properti.models import Properti, Kamar
            from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa
            from apps.biaya.models import TransaksiBiaya

            # ── Helper: hitung pendapatan sewa antara 2 tanggal ──
            def get_revenue(start, end):
                return float(PembayaranSewa.objects.filter(
                    tanggal_bayar__gte=start, tanggal_bayar__lte=end
                ).aggregate(t=Sum('jumlah_bayar'))['t'] or 0)

            # ── REVENUE (Pendapatan Sewa) ──
            rev_now = get_revenue(month_start, today)
            rev_prev = get_revenue(prev_start, prev_end)
            rev_growth = round((rev_now - rev_prev) / rev_prev * 100, 1) if rev_prev > 0 else 0

            # ── KAMAR ──
            total_kamar = Kamar.objects.count()
            kamar_terisi = Kamar.objects.filter(status='terisi').count()
            kamar_tersedia = Kamar.objects.filter(status='tersedia').count()
            kamar_maintenance = Kamar.objects.filter(status='maintenance').count()
            okupansi = round(kamar_terisi / total_kamar * 100, 1) if total_kamar > 0 else 0

            # ── TAGIHAN ──
            tagihan_menunggak = TagihanSewa.objects.filter(
                status__in=['belum_bayar', 'terlambat']
            ).count()
            total_nilai_menunggak = float(TagihanSewa.objects.filter(
                status__in=['belum_bayar', 'terlambat']
            ).aggregate(t=Sum('jumlah'))['t'] or 0)

            # ── KONTRAK segera habis (30 hari ke depan) ──
            kontrak_segera_habis = KontrakSewa.objects.filter(
                status='aktif',
                tanggal_keluar__lt=today + timedelta(days=30),
                tanggal_keluar__gte=today
            ).count()

            # ── BIAYA ──
            biaya_now = float(TransaksiBiaya.objects.filter(
                tanggal__gte=month_start
            ).aggregate(t=Sum('jumlah'))['t'] or 0)
            profit = rev_now - biaya_now

            # ═══ SKOR KESEHATAN BISNIS KOST (0-100) ═══
            score = 50

            # Okupansi
            if okupansi >= 90:
                score += 20
            elif okupansi >= 70:
                score += 10
            elif okupansi >= 50:
                score += 5
            elif okupansi >= 30:
                score -= 5
            else:
                score -= 15

            # Revenue growth
            if rev_growth > 10:
                score += 10
            elif rev_growth > 0:
                score += 5
            elif rev_growth > -10:
                score -= 5
            else:
                score -= 10

            # Tagihan menunggak
            if tagihan_menunggak == 0:
                score += 10
            elif tagihan_menunggak <= 3:
                score += 5
            elif tagihan_menunggak <= 10:
                score -= 5
            else:
                score -= 10

            # Rasio biaya
            biaya_ratio = biaya_now / max(rev_now, 1) * 100
            if biaya_ratio < 30:
                score += 10
            elif biaya_ratio < 50:
                score += 5
            elif biaya_ratio < 70:
                score -= 5
            else:
                score -= 10

            score = max(0, min(100, score))

            if score >= 80:
                health_level, health_color = 'Sangat Sehat', '#28a745'
            elif score >= 60:
                health_level, health_color = 'Sehat', '#4caf50'
            elif score >= 40:
                health_level, health_color = 'Perlu Perhatian', '#ff9800'
            elif score >= 20:
                health_level, health_color = 'Bermasalah', '#f44336'
            else:
                health_level, health_color = 'Kritis', '#d32f2f'

            # ═══ DETEKSI ANOMALI ═══
            anomalies = []
            if tagihan_menunggak > 0:
                anomalies.append({
                    'level': 'danger', 'icon': 'ri-error-warning-line',
                    'title': f'{tagihan_menunggak} Tagihan Menunggak (Rp {total_nilai_menunggak:,.0f})',
                    'desc': 'Segera lakukan follow-up ke penyewa untuk menghindari tunggakan lebih lanjut.',
                })
            if kontrak_segera_habis > 0:
                anomalies.append({
                    'level': 'warning', 'icon': 'ri-calendar-event-line',
                    'title': f'{kontrak_segera_habis} Kontrak Segera Berakhir',
                    'desc': 'Hubungi penyewa untuk perpanjangan kontrak dalam 30 hari ke depan.',
                })
            if okupansi < 50:
                anomalies.append({
                    'level': 'danger', 'icon': 'ri-home-heart-line',
                    'title': f'Okupansi Rendah ({okupansi}%)',
                    'desc': 'Tingkat hunian di bawah 50%. Pertimbangkan promosi atau penyesuaian harga sewa.',
                })
            if rev_growth < -20:
                anomalies.append({
                    'level': 'danger', 'icon': 'ri-arrow-down-line',
                    'title': f'Pendapatan Turun {abs(rev_growth)}%',
                    'desc': 'Pendapatan sewa bulan ini turun signifikan dibanding bulan lalu.',
                })
            if biaya_ratio > 60:
                anomalies.append({
                    'level': 'warning', 'icon': 'ri-money-dollar-circle-line',
                    'title': f'Rasio Biaya Tinggi ({biaya_ratio:.0f}%)',
                    'desc': 'Biaya operasional melebihi 60% dari pendapatan sewa.',
                })
            if kamar_maintenance > 0:
                anomalies.append({
                    'level': 'info', 'icon': 'ri-tools-line',
                    'title': f'{kamar_maintenance} Kamar Dalam Perbaikan',
                    'desc': 'Pastikan perbaikan selesai tepat waktu agar kamar bisa disewakan.',
                })
            if not anomalies:
                anomalies.append({
                    'level': 'success', 'icon': 'ri-check-double-line',
                    'title': 'Tidak Ada Anomali',
                    'desc': 'Semua metrik bisnis kost dalam kondisi normal.',
                })

            # ═══ TREN BULANAN (6 bulan) ═══
            monthly_labels = []
            monthly_values = []
            cur_year, cur_month = today.year, today.month
            for i in range(5, -1, -1):
                m = cur_month - i
                y = cur_year
                while m <= 0:
                    m += 12
                    y -= 1
                m_start = date(y, m, 1)
                _, last_day = calendar.monthrange(y, m)
                m_end = date(y, m, last_day) if i > 0 else today
                m_rev = get_revenue(m_start, m_end)
                monthly_labels.append(m_start.strftime('%b %Y'))
                monthly_values.append(m_rev)

            # ═══ AI USAGE STATS ═══
            total_chats = ChatHistory.objects.filter(user=self.request.user).count()
            total_feedback_up = ChatFeedback.objects.filter(
                user=self.request.user, feedback='up'
            ).count()
            total_feedback_down = ChatFeedback.objects.filter(
                user=self.request.user, feedback='down'
            ).count()

            context.update({
                'rev_now': rev_now,
                'rev_prev': rev_prev,
                'rev_growth': rev_growth,
                'total_kamar_terisi': kamar_terisi,
                'biaya_now': biaya_now,
                'profit': profit,
                'total_kamar': total_kamar,
                'kamar_tersedia': kamar_tersedia,
                'kamar_terisi': kamar_terisi,
                'kamar_maintenance': kamar_maintenance,
                'okupansi': okupansi,
                'tagihan_menunggak': tagihan_menunggak,
                'kontrak_segera_habis': kontrak_segera_habis,
                'biaya_ratio': round(biaya_ratio, 1),
                'health_score': score,
                'health_level': health_level,
                'health_color': health_color,
                'anomalies': anomalies,
                'monthly_labels': json.dumps(monthly_labels),
                'monthly_values': json.dumps(monthly_values),
                'total_chats': total_chats,
                'total_feedback_up': total_feedback_up,
                'total_feedback_down': total_feedback_down,
            })

        except Exception as e:
            logger.error(f"[AI Dashboard] Error: {e}", exc_info=True)
            context['dashboard_error'] = str(e)

        return context


# ═══════════════════════════════════════════════════════════════
# PENGATURAN VIEW — CRUD Halaman Pengaturan AI Assistant
# ═══════════════════════════════════════════════════════════════

class AIAssistantSettingsView(LoginRequiredMixin, TemplateView):
    """Halaman pengaturan AI Assistant (GET = tampilkan, POST = simpan)."""
    template_name = 'ai_assistant/index.html'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['config'] = AIAssistantConfig.load()
        context['provider_choices'] = AIAssistantConfig.PROVIDER_CHOICES
        context['page_title'] = 'AI Assistant'
        return context

    def post(self, request, *args, **kwargs):
        config = AIAssistantConfig.load()

        config.provider = request.POST.get('provider', 'gemini')
        config.api_key = request.POST.get('api_key', '').strip()
        config.model_name = request.POST.get('model_name', 'gemini-2.0-flash').strip()
        config.aktif = request.POST.get('aktif') == 'on'
        config.ai_name = request.POST.get('ai_name', 'AI Assistant').strip() or 'AI Assistant'
        config.system_prompt = request.POST.get('system_prompt', '').strip()

        try:
            config.max_tokens = int(request.POST.get('max_tokens', 1024))
        except (ValueError, TypeError):
            config.max_tokens = 1024

        try:
            config.temperature = float(request.POST.get('temperature', 0.7))
        except (ValueError, TypeError):
            config.temperature = 0.7

        config.save()
        messages.success(request, 'Pengaturan AI Assistant berhasil disimpan!')
        return redirect('ai_assistant:index')
