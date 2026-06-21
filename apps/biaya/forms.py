"""
BIAYA FORMS - Form Kategori Biaya & Transaksi Biaya (SIMKOS)
"""
from django import forms
from apps.biaya.models import KategoriBiaya, TransaksiBiaya
from datetime import date

import logging

logger = logging.getLogger(__name__)



class KategoriBiayaForm(forms.ModelForm):
    """Form CRUD Kategori Biaya."""
    class Meta:
        model = KategoriBiaya
        fields = ['nama', 'deskripsi', 'aktif']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TransaksiBiayaForm(forms.ModelForm):
    """Form catat pengeluaran biaya."""
    # Definisikan metode_pembayaran sebagai ChoiceField eksplisit
    # agar Django render sebagai dropdown Select (bukan TextInput)
    metode_pembayaran = forms.ChoiceField(
        choices=[('', 'Pilih Metode Pembayaran')],
        required=False,
        label='Metode Pembayaran',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = TransaksiBiaya
        fields = ['tanggal', 'kategori', 'jumlah', 'metode_pembayaran', 'status', 'deskripsi', 'bukti']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'bukti': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'tanggal': 'Tanggal Transaksi',
            'kategori': 'Kategori Biaya',
            'jumlah': 'Jumlah (Rp)',
            'metode_pembayaran': 'Metode Pembayaran',
            'status': 'Status',
            'deskripsi': 'Deskripsi/Keterangan',
            'bukti': 'Upload Bukti (Foto/PDF)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_kategori = KategoriBiaya.objects.filter(aktif=True)
        if active_kategori.exists():
            self.fields['kategori'].queryset = active_kategori
        else:
            self.fields['kategori'].queryset = KategoriBiaya.objects.all()
        self.fields['kategori'].empty_label = 'Pilih Kategori Biaya'
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()

        # Ambil pilihan metode pembayaran dari model MetodePembayaran (Pengaturan)
        try:
            from apps.pengaturan.models import MetodePembayaran
            metode_qs = MetodePembayaran.objects.filter(aktif=True).order_by('nama')
            choices = [('', 'Pilih Metode Pembayaran')]
            choices += [(m.kode, m.nama) for m in metode_qs]
            self.fields['metode_pembayaran'].choices = choices
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)

