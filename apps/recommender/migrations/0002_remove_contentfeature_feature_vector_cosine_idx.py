# Generated by Django 5.2 on 2025-06-09 12:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('recommender', '0001_initial'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='contentfeature',
            name='feature_vector_cosine_idx',
        ),
    ]
