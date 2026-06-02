"""
==========================================================================
 PAGES VIEWS - View untuk Halaman Statis (Error, Maintenance, dll)
==========================================================================
 View generik untuk halaman-halaman statis/misc:
 - Error page (404/500)
 - Under Maintenance page
 - Coming Soon page
 - Not Authorized page (403)
 - Server Error page

 Semua halaman menggunakan layout_blank.html (tanpa sidebar/navbar)
 karena ini adalah halaman yang ditampilkan saat terjadi error
 atau saat user tidak memiliki akses.

 Terhubung dengan:
 - pages/urls.py → Routing ke template berbeda via template_name parameter
 - web_project → TemplateLayout untuk inisialisasi global layout
 - web_project/template_helpers/theme.py → TemplateHelper untuk set layout
==========================================================================
"""
from django.shortcuts import redirect
from django.views.generic import TemplateView
from web_project import TemplateLayout
from web_project.template_helpers.theme import TemplateHelper


class MiscPagesView(TemplateView):
    """
    View generik untuk halaman statis/error.
    Template ditentukan via parameter di urls.py, bukan di sini.
    Menggunakan layout_blank.html (halaman tanpa sidebar/navbar).
    """
    def get(self, request, *args, **kwargs):
        if self.template_name == 'pages_misc_under_maintenance.html':
            from apps.core.license_models import LicenseConfig
            try:
                from apps.pengaturan.models import PengaturanPerusahaan
                pengaturan = PengaturanPerusahaan.load()
                local_maintenance = getattr(pengaturan, 'maintenance_mode', False)
            except Exception:
                local_maintenance = False
                
            config = LicenseConfig.get_config()
            # Jika user terlanjur mendarat di halaman perbaikan, tapi sekarang Maintenance Mode (baik remote CLS maupun lokal) ternyata SUDAH DIMATIKAN
            if not config.is_maintenance and not local_maintenance:
                return redirect('/')
                
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # Inisialisasi layout global (tema, warna, dll)
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))

        # Set layout ke blank (tanpa sidebar dan navbar)
        context.update(
            {
                "layout_path": TemplateHelper.set_layout("layout_blank.html", context),
            }
        )

        # Load config lisensi
        from apps.core.license_models import LicenseConfig
        try:
            lc = LicenseConfig.get_config()
            context['license_config'] = lc
        except Exception:
            context['license_config'] = None

        return context
