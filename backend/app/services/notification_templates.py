"""Code-versioned bilingual notification templates with HTML autoescaping."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Literal

Locale = Literal["bn", "en"]
Channel = Literal["email", "sms"]


@dataclass(frozen=True, slots=True)
class RenderedTemplate:
    key: str
    version: int
    locale: Locale
    channel: Channel
    subject: str | None
    text: str
    html: str | None


_SUBJECTS: dict[str, dict[Locale, str]] = {
    "order.placed": {"bn": "আপনার বজ্র অর্ডার গ্রহণ করা হয়েছে", "en": "Your Bojro order was placed"},
    "order.confirmed": {"bn": "আপনার বজ্র অর্ডার নিশ্চিত হয়েছে", "en": "Your Bojro order was confirmed"},
    "order.shipped": {"bn": "আপনার বজ্র অর্ডার পাঠানো হয়েছে", "en": "Your Bojro order has shipped"},
    "order.delivered": {"bn": "আপনার বজ্র অর্ডার পৌঁছেছে", "en": "Your Bojro order was delivered"},
    "newsletter.confirm": {
        "bn": "বজ্র নিউজলেটার নিশ্চিত করুন",
        "en": "Confirm your Bojro newsletter subscription",
    },
    "newsletter.welcome": {"bn": "বজ্র নিউজলেটারে স্বাগতম", "en": "Welcome to the Bojro newsletter"},
    "cart.abandoned": {"bn": "আপনার বজ্র কার্ট অপেক্ষা করছে", "en": "Your Bojro cart is waiting"},
}

_ORDER_STATUS: dict[str, dict[Locale, str]] = {
    "order.placed": {"bn": "গ্রহণ করা হয়েছে", "en": "has been placed"},
    "order.confirmed": {"bn": "নিশ্চিত হয়েছে", "en": "has been confirmed"},
    "order.shipped": {"bn": "পাঠানো হয়েছে", "en": "has shipped"},
    "order.delivered": {"bn": "পৌঁছে দেওয়া হয়েছে", "en": "was delivered"},
}

_ALLOWED: dict[str, set[Channel]] = {
    "auth.otp": {"sms"},
    "order.placed": {"email", "sms"},
    "order.confirmed": {"email", "sms"},
    "order.shipped": {"email", "sms"},
    "order.delivered": {"email", "sms"},
    "newsletter.confirm": {"email"},
    "newsletter.welcome": {"email"},
    "cart.abandoned": {"email", "sms"},
}


def render_template(
    key: str,
    version: int,
    locale: Locale,
    channel: Channel,
    context: dict[str, object],
) -> RenderedTemplate:
    if version != 1 or key not in _ALLOWED or channel not in _ALLOWED[key]:
        raise ValueError("unsupported notification template")
    values = {name: _plain(value) for name, value in context.items()}
    if key == "auth.otp":
        code = values.get("code", "")
        text = (
            f"বজ্র যাচাইকরণ কোড: {code}। কোডটি কাউকে দেবেন না।"
            if locale == "bn"
            else f"Your Bojro verification code is {code}. Do not share this code."
        )
        return _result(key, version, locale, channel, None, text, None)

    if key.startswith("order."):
        number = values.get("order_number", "")
        status = _ORDER_STATUS[key][locale]
        if locale == "bn":
            text = f"অর্ডার {number} {status}। বজ্র বেছে নেওয়ার জন্য ধন্যবাদ।"
        else:
            text = f"Order {number} {status}. Thank you for choosing Bojro."
        return _result(
            key,
            version,
            locale,
            channel,
            _SUBJECTS[key][locale] if channel == "email" else None,
            text,
            _email_html(_SUBJECTS[key][locale], text, locale=locale)
            if channel == "email"
            else None,
        )

    if key == "newsletter.confirm":
        link = values.get("confirm_url", "")
        text = (
            f"বজ্র নিউজলেটার পেতে ২৪ ঘণ্টার মধ্যে নিশ্চিত করুন: {link}"
            if locale == "bn"
            else f"Confirm within 24 hours to receive the Bojro newsletter: {link}"
        )
        return _result(
            key,
            version,
            locale,
            channel,
            _SUBJECTS[key][locale],
            text,
            _email_html(_SUBJECTS[key][locale], text, locale=locale, link=link),
        )

    if key == "newsletter.welcome":
        unsubscribe = values.get("unsubscribe_url", "")
        text = (
            f"বজ্র নিউজলেটারে স্বাগতম। সদস্যতা বাতিল: {unsubscribe}"
            if locale == "bn"
            else f"Welcome to the Bojro newsletter. Unsubscribe: {unsubscribe}"
        )
        return _result(
            key,
            version,
            locale,
            channel,
            _SUBJECTS[key][locale],
            text,
            _email_html(_SUBJECTS[key][locale], text, locale=locale, link=unsubscribe),
        )

    cart_url = values.get("cart_url", "")
    text = (
        f"আপনার কার্টের পণ্যগুলো এখনো অপেক্ষা করছে: {cart_url}"
        if locale == "bn"
        else f"The items in your cart are still waiting: {cart_url}"
    )
    return _result(
        key,
        version,
        locale,
        channel,
        _SUBJECTS[key][locale] if channel == "email" else None,
        text,
        _email_html(_SUBJECTS[key][locale], text, locale=locale, link=cart_url)
        if channel == "email"
        else None,
    )


def template_catalog() -> list[dict[str, object]]:
    return [
        {"key": key, "version": 1, "channels": sorted(channels), "locales": ["bn", "en"]}
        for key, channels in sorted(_ALLOWED.items())
    ]


def _result(
    key: str,
    version: int,
    locale: Locale,
    channel: Channel,
    subject: str | None,
    text: str,
    html_body: str | None,
) -> RenderedTemplate:
    maximum = 320 if key == "auth.otp" else 480
    if channel == "sms" and len(text) > maximum:
        raise ValueError("rendered SMS exceeds the audited length limit")
    return RenderedTemplate(key, version, locale, channel, subject, text, html_body)


def _plain(value: object) -> str:
    return " ".join(str(value).replace("\x00", "").split())[:2000]


def _email_html(
    subject: str,
    text: str,
    *,
    locale: Locale,
    link: str | None = None,
) -> str:
    heading = html.escape(subject, quote=True)
    body = html.escape(text, quote=True)
    action = ""
    if link:
        safe_link = html.escape(link, quote=True)
        action = f'<p><a href="{safe_link}" rel="noopener noreferrer">{safe_link}</a></p>'
    return (
        f'<!doctype html><html lang="{locale}"><body>'
        f"<h1>{heading}</h1><p>{body}</p>{action}"
        "<p>Bojro</p></body></html>"
    )
