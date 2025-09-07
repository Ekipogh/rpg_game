from django_unicorn.components import UnicornView
from hero.models import Hero


class HeroScreenView(UnicornView):
    hero: Hero

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hero'] = self.hero
        return context
