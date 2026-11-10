def format_currency(value):
    """Display an integer copper amount in gold, silver, and copper."""
    amount = int(value or 0)
    sign = "-" if amount < 0 else ""
    gold, remainder = divmod(abs(amount), 100)
    silver, copper = divmod(remainder, 10)
    parts = [f"{count} {unit}" for count, unit in
             ((gold, "gold"), (silver, "silver"), (copper, "copper")) if count]
    return sign + (" ".join(parts) or "0 copper")


def render_currency(value):
    """Render currency with the supplied denomination artwork."""
    from django.conf import settings
    from django.utils.html import format_html, format_html_join

    label = format_currency(value)
    words = label.split()
    images = {"gold": "Coin_Gold_0.png", "silver": "Coin_Silver_0.png",
              "copper": "Coin_Cupper_0.png"}
    coins = format_html_join(
        " ",
        '<span class="currency-denomination"><img class="currency-coin" src="{}" '
        'alt="" width="24" height="24">{} {}</span>',
        ((f"{settings.MEDIA_URL}coin/{images[unit]}", count, unit)
         for count, unit in zip(words[::2], words[1::2])),
    )
    return format_html('<span class="currency" aria-label="{}">{}</span>', label, coins)
