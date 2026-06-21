"""
SEWA FORMS - Form untuk Kontrak Sewa, Tagihan, dan Pembayaran
"""
from django import forms
from apps.sewa.models import KontrakSewa, TagihanSewa, PembayaranSewa
from apps.penyewa.models import Penyewa
from apps.properti.models import Kamar
from datetime import date

import logging

logger = logging.getLogger(__name__)



class KontrakSewaForm(forms.ModelForm):
    class Meta:
        model = KontrakSewa
        fields = ['penyewa', 'kamar', 'tanggal_masuk', 'tanggal_keluar', 'harga_sewa', 'deposit', 'status', 'catatan']
        widgets = {
            'penyewa': forms.Select(attrs={'class': 'form-select'}),
            'kamar': forms.Select(attrs={'class': 'form-select'}),
            'tanggal_masuk': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tanggal_keluar': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'harga_sewa': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'deposit': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['penyewa'].queryset = Penyewa.objects.filter(status='aktif')
        self.fields['penyewa'].empty_label = 'Pilih Penyewa'
        # Jika edit, tampilkan kamar yang terisi juga
        if self.instance.pk:
            self.fields['kamar'].queryset = Kamar.objects.all()
        else:
            self.fields['kamar'].queryset = Kamar.objects.filter(status='tersedia')
        self.fields['kamar'].empty_label = 'Pilih Kamar'
        if not self.instance.pk:
            self.fields['tanggal_masuk'].initial = date.today()


class TagihanSewaForm(forms.ModelForm):
    # Definisikan metode_pembayaran sebagai ChoiceField eksplisit — dropdown Select
    metode_pembayaran = forms.ChoiceField(
        choices=[('', 'Pilih Metode Pembayaran')],
        required=False,
        label='Metode Pembayaran',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = TagihanSewa
        fields = ['kontrak', 'periode_bulan', 'periode_tahun', 'jumlah',
                  'jumlah_bayar', 'metode_pembayaran',
                  'tanggal_jatuh_tempo', 'status', 'catatan']
        widgets = {
            'kontrak': forms.Select(attrs={'class': 'form-select'}),
            'periode_bulan': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '12'}),
            'periode_tahun': forms.NumberInput(attrs={'class': 'form-control', 'min': '2020', 'max': '2030'}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'jumlah_bayar': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'tanggal_jatuh_tempo': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kontrak'].queryset = KontrakSewa.objects.filter(status='aktif')
        self.fields['kontrak'].empty_label = 'Pilih Kontrak'
        self.fields['jumlah_bayar'].required = False
        if not self.instance.pk:
            from datetime import datetime
            now = datetime.now()
            self.fields['periode_bulan'].initial = now.month
            self.fields['periode_tahun'].initial = now.year

        # Ambil pilihan metode pembayaran dari model MetodePembayaran (Pengaturan)
        try:
            from apps.pengaturan.models import MetodePembayaran
            metode_qs = MetodePembayaran.objects.filter(aktif=True).order_by('nama')
            choices = [('', 'Pilih Metode Pembayaran')]
            choices += [(m.kode, m.nama) for m in metode_qs]
            self.fields['metode_pembayaran'].choices = choices
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)


class PembayaranSewaForm(forms.ModelForm):
    # Definisikan metode_bayar sebagai ChoiceField eksplisit
    # agar Django render sebagai dropdown Select (bukan TextInput)
    metode_bayar = forms.ChoiceField(
        choices=[('', 'Pilih Metode Pembayaran')],
        required=False,
        label='Metode Bayar',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = PembayaranSewa
        fields = ['tagihan', 'tanggal_bayar', 'jumlah_bayar', 'metode_bayar', 'bukti_bayar', 'catatan']
        widgets = {
            'tagihan': forms.Select(attrs={'class': 'form-select'}),
            'tanggal_bayar': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'jumlah_bayar': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'bukti_bayar': forms.FileInput(attrs={'class': 'form-control'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tagihan'].queryset = TagihanSewa.objects.exclude(status='lunas')
        self.fields['tagihan'].empty_label = 'Pilih Tagihan'
        if not self.instance.pk:
            self.fields['tanggal_bayar'].initial = date.today()

        # Ambil pilihan metode pembayaran dari model MetodePembayaran (Pengaturan)
        try:
            from apps.pengaturan.models import MetodePembayaran
            metode_qs = MetodePembayaran.objects.filter(aktif=True).order_by('nama')
            choices = [('', 'Pilih Metode Pembayaran')]
            choices += [(m.kode, m.nama) for m in metode_qs]
            self.fields['metode_bayar'].choices = choices
        except Exception as e:
            logger.warning("Error tidak terduga: %s", e)

