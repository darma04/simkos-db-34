"""
==========================================================================
 WEB PROJECT - Template Layout Engine
==========================================================================
 File ini adalah __init__.py dari package web_project — file yang
 otomatis dimuat saat Python mengimport package 'web_project'.

 Berisi class TemplateLayout yang merupakan inti template engine proyek ini.

 Apa yang dilakukan TemplateLayout?
 - Menginisialisasi context (data) untuk SETIAP halaman
 - Mengatur layout yang aktif (vertical, horizontal, blank, dll)
 - Mengatur mode RTL (Right-to-Left) untuk bahasa Arab
 - Memetakan variabel template (CSS class, konfigurasi sidebar, navbar, dll)

 Cara penggunaan di View:
    class MyView(TemplateView):
        def get_context_data(self, **kwargs):
            context = TemplateLayout.init(self, super().get_context_data(**kwargs))
            # context sekarang sudah berisi layout_path, rtl_mode, dll
            return context

 Kenapa setiap view harus memanggil TemplateLayout.init()?
 - Agar semua halaman menggunakan layout yang konsisten
 - Agar semua variabel template (sidebar, navbar, footer) tersedia
 - Agar pengaturan tema dari settings.py diterapkan

 Koneksi:
 - config/settings.py → TEMPLATE_CONFIG (pengaturan tema dan layout)
 - web_project/template_helpers/theme.py → TemplateHelper (logika tema)
 - Semua views di seluruh proyek → Memanggil TemplateLayout.init()
 - templates/layout/ → File layout HTML yang dipilih
==========================================================================
"""

# from web_project.bootstrap import TemplateBootstrap  # Tidak dipakai (dikomentari)
from web_project.template_helpers.theme import TemplateHelper  # Helper untuk tema/layout
from django.conf import settings  # Mengakses pengaturan Django


class TemplateLayout:
    """
    Class utama untuk menginisialisasi layout template di setiap halaman.

    Class ini TIDAK mewarisi model atau view apapun — murni utility class.
    Semua method-nya untuk mempersiapkan data yang dibutuhkan template.
    """

    def init(self, context):
        """
        Inisialisasi context template dengan data layout dan tema.

        Parameter:
        - self: Instance view yang memanggil (contoh: DashboardView)
          → Dibutuhkan untuk mengakses self.request (request dari user)
        - context: Dictionary context dari view (berisi data halaman)

        Langkah-langkah:
        1. init_context() → Set variabel dari TEMPLATE_CONFIG di settings.py
        2. Ambil nama layout dari context (misal: 'vertical', 'horizontal')
        3. set_layout() → Tentukan file layout HTML yang dipakai
        4. Cek cookie rtl_mode → Tentukan arah teks (LTR atau RTL)
        5. map_context() → Petakan variabel tema ke CSS class

        Return:
        - context yang sudah diperkaya dengan data layout
        """
        # Langkah 1: Inisialisasi context dengan variabel dari TEMPLATE_CONFIG
        # Ini mengisi context dengan: layout, hasCustomizer, navbarFull, dll
        context = TemplateHelper.init_context(context)

        # Inject request ke context agar bisa diakses oleh layout bootstrap
        # (diperlukan untuk RBAC menu filtering di init_menu_data)
        if hasattr(self, 'request'):
            context['request'] = self.request

        # Langkah 2: Ambil layout yang dipilih (misal: 'vertical')
        layout = context["layout"]

        # Langkah 3 & 4: Set layout path dan RTL mode
        context.update(
            {
                # Tentukan file layout HTML: 'layout_vertical.html', 'layout_horizontal.html', dll
                "layout_path": TemplateHelper.set_layout(
                    "layout_" + layout + ".html", context
                ),
                # Mode RTL (Right-to-Left) untuk bahasa Arab
                # Cek dari cookie: jika user memilih RTL → True
                # Jika tidak → gunakan nilai default dari TEMPLATE_CONFIG
                "rtl_mode": True
                if self.request.COOKIES.get('django_text_direction') == "rtl"
                else settings.TEMPLATE_CONFIG.get("rtl_mode"),
            }
        )

        # Langkah 5: Petakan variabel context ke CSS class
        # Contoh: navbar_type='fixed' → CSS class 'layout-navbar-fixed'
        TemplateHelper.map_context(context)

        return context
