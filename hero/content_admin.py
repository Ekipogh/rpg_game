"""Browser access to the same transactional importer used by the CLI."""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django import forms
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.management import CommandError, call_command
from django.db import transaction
from django.template.response import TemplateResponse

from hero.models import HeroClass


class ContentImportForm(forms.Form):
    catalog = forms.FileField(label="RPG content YAML")
    action = forms.ChoiceField(choices=(("validate", "Validate only"), ("apply", "Apply content")))

    def clean_catalog(self):
        upload = self.cleaned_data["catalog"]
        if upload.size > 2 * 1024 * 1024:
            raise forms.ValidationError("The catalog must be at most 2 MiB.")
        return upload


def import_content(request, admin_site):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied
    form = ContentImportForm(request.POST or None, request.FILES or None)
    output = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["catalog"]
        dry_run = form.cleaned_data["action"] == "validate"
        stream = StringIO()
        try:
            # Never use a client-supplied filename as a server path.
            with TemporaryDirectory(prefix="rpg-content-") as directory:
                path = Path(directory) / "catalog.yaml"
                path.write_bytes(upload.read())
                with transaction.atomic():
                    call_command("import_rpg_content", str(path), dry_run=dry_run,
                                 stdout=stream, no_color=True)
                    if not dry_run:
                        LogEntry.objects.create(
                            user_id=request.user.pk,
                            content_type=ContentType.objects.get_for_model(HeroClass),
                            object_repr="RPG content catalog",
                            action_flag=ADDITION,
                            change_message=f"Applied YAML catalog {upload.name}: {stream.getvalue().strip()}",
                        )
            output = stream.getvalue()
            # Avoid accidental resubmission on refresh.
            form = ContentImportForm(initial={"action": "validate"})
        except (CommandError, UnicodeError) as exc:
            form.add_error("catalog", str(exc))
    return TemplateResponse(request, "admin/hero/content_import.html", {
        **admin_site.each_context(request), "title": "Import RPG content",
        "form": form, "output": output,
    })
