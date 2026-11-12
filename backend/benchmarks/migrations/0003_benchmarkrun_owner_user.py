from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import evaluations.ownership


def move_benchmark_owners_to_users(apps, schema_editor):
    BenchmarkRun = apps.get_model('benchmarks', 'BenchmarkRun')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    database = schema_editor.connection.alias

    for run in BenchmarkRun.objects.using(database).all().iterator():
        username = run.owner_name or f'legacy-benchmark-owner-{run.pk}'
        user, _ = User.objects.using(database).get_or_create(username=username)
        run.owner_id = user.pk
        run.save(update_fields=['owner'])


def restore_benchmark_owner_names(apps, schema_editor):
    BenchmarkRun = apps.get_model('benchmarks', 'BenchmarkRun')
    database = schema_editor.connection.alias
    for run in BenchmarkRun.objects.using(database).select_related('owner').iterator():
        run.owner_name = run.owner.username
        run.save(update_fields=['owner_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('benchmarks', '0002_benchmarkrun_owner'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('evaluations', '0004_testsuite_owner_user'),
    ]

    operations = [
        migrations.RenameField(
            model_name='benchmarkrun',
            old_name='owner',
            new_name='owner_name',
        ),
        migrations.AddField(
            model_name='benchmarkrun',
            name='owner',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='benchmark_runs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(move_benchmark_owners_to_users, restore_benchmark_owner_names),
        migrations.AlterField(
            model_name='benchmarkrun',
            name='owner',
            field=models.ForeignKey(
                default=evaluations.ownership.get_default_owner_id,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='benchmark_runs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name='benchmarkrun',
            name='owner_name',
        ),
    ]