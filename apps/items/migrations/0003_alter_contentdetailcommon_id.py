# Generated by Django 5.2 on 2025-06-11 07:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0002_contentdetailcommon_summarize'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentdetailcommon',
            name='id',
            field=models.AutoField(primary_key=True, serialize=False),
        ),
    ]
