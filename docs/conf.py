"""Sphinx configuration. See https://www.sphinx-doc.org/en/master/usage/configuration.html"""

project = "django-task-psql"
copyright = "2026, YP Software"
author = "YP Software"
release = "0.1.0"

extensions = [
    "myst_parser",
]

source_suffix = {
    ".md": "markdown",
}

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Read the Docs sets the target language per linked translation project
# (Admin > Translations) and passes it to sphinx-build directly (`-D
# language=...`) — no env var needed here. Sphinx pulls translated strings
# from locale_dirs/<lang>/LC_MESSAGES/*.po and falls back to the source text
# (English) for anything untranslated.
language = "en"
locale_dirs = ["locale/"]
gettext_compact = False

html_theme = "furo"
html_title = project
