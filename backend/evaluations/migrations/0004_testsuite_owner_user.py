from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import evaluations.ownership


def move_suite_owners_to_users(apps, schema_editor):
    TestSuite = apps.get_model('evaluations', 'TestSuite')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    database = schema_editor.connection.alias

    for suite in TestSuite.objects.using(database).all().iterator():
        username = suite.owner_name or f'legacy-suite-owner-{suite.pk}'
        user, _ = User.objects.using(database).get_or_create(username=username)
        suite.owner_id = user.pk
        suite.save(update_fields=['owner'])


def restore_suite_owner_names(apps, schema_editor):
    TestSuite = apps.get_model('evaluations', 'TestSuite')
    database = schema_editor.connection.alias
    for suite in TestSuite.objects.using(database).select_related('owner').iterator():
        suite.owner_name = suite.owner.username
        suite.save(update_fields=['owner_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('evaluations', '0003_alter_testsuite_owner'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='testsuite',
            old_name='owner',
            new_name='owner_name',
        ),
        migrations.AddField(
            model_name='testsuite',
            name='owner',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='test_suites',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(move_suite_owners_to_users, restore_suite_owner_names),
        migrations.AlterField(
            model_name='testsuite',
            name='owner',
            field=models.ForeignKey(
                default=evaluations.ownership.get_default_owner_id,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='test_suites',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name='testsuite',
            name='owner_name',
        ),
    ]