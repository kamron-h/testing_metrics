from django import forms

class RepoURLForm(forms.Form):
    repo_url = forms.URLField(
        label="GitHub Repo URL",
        help_text="e.g. https://github.com/owner/repo.git",
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "GitHub repository URL"
        })
    )

class ReportSelectForm(forms.Form):
    # Keep the repo URL hidden so we can re‑POST it when switching reports
    repo_url = forms.CharField(widget=forms.HiddenInput())
    report   = forms.ChoiceField(label="Choose Report", choices=[])
