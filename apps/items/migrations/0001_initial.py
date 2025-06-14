# Generated by Django 5.2 on 2025-06-07 11:18

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ContentSummarize',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contentid', models.PositiveIntegerField(unique=True)),
                ('summarize_text', models.TextField()),
                ('spring_sim', models.FloatField(default=0)),
                ('summer_sim', models.FloatField(default=0)),
                ('autumn_sim', models.FloatField(default=0)),
                ('winter_sim', models.FloatField(default=0)),
            ],
            options={
                'db_table': 'content_summarize',
            },
        ),
        migrations.CreateModel(
            name='ContentDetailCommon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contentid', models.PositiveIntegerField(unique=True)),
                ('contenttypeid', models.PositiveSmallIntegerField()),
                ('title', models.TextField()),
                ('createdtime', models.DateTimeField()),
                ('modifiedtime', models.DateTimeField()),
                ('tel', models.TextField(blank=True, null=True)),
                ('telname', models.TextField(blank=True, null=True)),
                ('homepage', models.TextField(blank=True, null=True)),
                ('firstimage', models.TextField(blank=True, null=True)),
                ('firstimage2', models.TextField(blank=True, null=True)),
                ('cpyrhtdivcd', models.TextField(blank=True, null=True)),
                ('areacode', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('sigungucode', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('ldongregncd', models.TextField(blank=True, null=True)),
                ('ldongsigngucd', models.TextField(blank=True, null=True)),
                ('lclssystm1', models.TextField(blank=True, null=True)),
                ('lclssystm2', models.TextField(blank=True, null=True)),
                ('lclssystm3', models.TextField(blank=True, null=True)),
                ('cat1', models.TextField(blank=True, null=True)),
                ('cat2', models.TextField(blank=True, null=True)),
                ('cat3', models.TextField(blank=True, null=True)),
                ('addr1', models.TextField(blank=True, null=True)),
                ('addr2', models.TextField(blank=True, null=True)),
                ('zipcode', models.TextField(blank=True, null=True)),
                ('mapx', models.FloatField(blank=True, null=True)),
                ('mapy', models.FloatField(blank=True, null=True)),
                ('mlevel', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('overview', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'content_detail_common',
                'indexes': [models.Index(fields=['contentid'], name='content_det_content_9f06e4_idx'), models.Index(fields=['mapx', 'mapy'], name='content_det_mapx_0403d9_idx')],
            },
        ),
        migrations.CreateModel(
            name='ContentDetailImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contentid', models.PositiveIntegerField()),
                ('imgname', models.TextField()),
                ('originimgurl', models.TextField()),
                ('serialnum', models.TextField(unique=True)),
                ('smallimageurl', models.TextField()),
                ('cpyrhtdivcd', models.TextField()),
            ],
            options={
                'db_table': 'content_detail_image',
                'indexes': [models.Index(fields=['contentid'], name='content_det_content_302678_idx')],
            },
        ),
        migrations.CreateModel(
            name='ContentDetailInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contentid', models.PositiveIntegerField()),
                ('contenttypeid', models.PositiveSmallIntegerField()),
                ('etc', models.JSONField()),
            ],
            options={
                'db_table': 'content_detail_info',
                'indexes': [models.Index(fields=['contentid'], name='content_det_content_f6c662_idx')],
            },
        ),
        migrations.CreateModel(
            name='ContentDetailIntro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contentid', models.PositiveIntegerField(unique=True)),
                ('contenttypeid', models.PositiveSmallIntegerField()),
                ('etc', models.JSONField()),
            ],
            options={
                'db_table': 'content_detail_intro',
                'indexes': [models.Index(fields=['contentid'], name='content_det_content_6c0611_idx')],
            },
        ),
    ]
