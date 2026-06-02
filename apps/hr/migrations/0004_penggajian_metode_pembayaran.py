from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0003_absensi_persentase_kemiripan'),
    ]

    operations = [
        migrations.AddField(
            model_name='penggajian',
            name='metode_pembayaran',
            field=models.CharField(
                blank=True,
                help_text="Wajib diisi saat status 'dibayar' agar saldo terhitung dengan benar",
                max_length=50,
                null=True,
                verbose_name='Metode Pembayaran',
            ),
        ),
    ]
