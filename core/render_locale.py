"""Locale-aware render helper (T118).

``locale=en`` stays the default.  ``locale=fa-IR`` only flips template
strings for brief/home copy — the logic of propose/approve/execute stays
locale-agnostic.  No Jalali calendar product.
"""

from __future__ import annotations

from typing import Any

# English (default) and Persian (fa-IR) template strings for brief/home copy.
# Only the human-readable *labels* change — the structural keys and logic
# are locale-agnostic.
_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "home_title": "Home",
        "brief_title": "Desk Brief",
        "pending_actions": "Pending actions",
        "approved_waiting": "Approved — waiting execute",
        "rejected": "Rejected",
        "due_commitments": "Due commitments",
        "meetings": "Meetings",
        "repos": "Repos",
        "brief": "Brief",
        "files": "Files",
        "generated": "Generated",
        "none_": "(none)",
        "no_meetings": "_No meetings scheduled today._",
        "no_repos": "_No recent repository activity._",
        "no_pending": "_No pending actions._",
        "warning_stale": (
            "warning: last desk tick was {days} days ago — "
            "run 'aegis tick' to refresh."
        ),
    },
    "fa-IR": {
        "home_title": "خانه",
        "brief_title": "خلاصه روز",
        "pending_actions": "اقدامات در انتظار",
        "approved_waiting": "تایید شده — در انتظار اجرا",
        "rejected": "رد شده",
        "due_commitments": "تعهدات موعد",
        "meetings": "جلسات",
        "repos": "مخازن",
        "brief": "خلاصه",
        "files": "فایل‌ها",
        "generated": "تولید شد",
        "none_": "(خالی)",
        "no_meetings": "_جلسه‌ای برای امروز برنامه‌ریزی نشده است._",
        "no_repos": "_فعالیت اخیر مخزن وجود ندارد._",
        "no_pending": "_اقدام معلق وجود ندارد._",
        "warning_stale": (
            "هشدار: آخرین tick سال‌م روز پیش بوده — "
            "برای به‌روز کردن 'aegis tick' را اجرا کنید."
        ),
    },
}

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES: tuple[str, ...] = ("en", "fa-IR")


def _normalize_locale(locale: str | None) -> str:
    """Normalize *locale* to a supported locale or raise ``ValueError``.

    ``None`` / empty defaults to ``"en"``.
    """
    if not locale or not locale.strip():
        return DEFAULT_LOCALE
    lc = locale.strip()
    if lc in _STRINGS:
        return lc
    # Accept bare "fa" as fa-IR.
    if lc.lower() == "fa":
        return "fa-IR"
    raise ValueError(f"unsupported locale: {locale}")


def get_strings(locale: str | None = None) -> dict[str, str]:
    """Return the template-strings dict for *locale* (default ``en``)."""
    lc = _normalize_locale(locale)
    return dict(_STRINGS[lc])


def localize_home(locale: str | None, home: dict[str, Any]) -> dict[str, Any]:
    """Localize the home-page *dict* labels without changing structure or logic.

    Only human-readable label fields are swapped.  ``locale`` defaults to
    ``"en"`` and unsupported locales raise ``ValueError``.
    """
    strings = get_strings(locale)
    out = dict(home)
    # Only overwrite label fields that exist — never add new keys.
    if "title" in out:
        out["title"] = strings["home_title"]
    if "brief_label" in out:
        out["brief_label"] = strings["brief"]
    return out


def localize_brief(locale: str | None, brief: dict[str, Any]) -> dict[str, Any]:
    """Localize the brief *dict* labels without changing structure or logic.

    Only human-readable label fields are swapped.  ``locale`` defaults to
    ``"en"`` and unsupported locales raise ``ValueError``.
    """
    strings = get_strings(locale)
    out = dict(brief)
    if "title" in out:
        out["title"] = strings["brief_title"]
    return out


def warning_stale(locale: str | None, days: int) -> str:
    """Return a locale-aware stale-tick warning string."""
    strings = get_strings(locale)
    return strings["warning_stale"].format(days=days)
