from django_unicorn.components import UnicornView
from django.shortcuts import redirect

# Use Windows-compatible healing system
from hero.windows_tasks import rest_hero, start_hero_healing, simple_heal_hero


class HomeScreenView(UnicornView):
    """Home screen component for the RPG game"""

    def navigate_to_battle(self):
        """Handle navigation to battle screen"""
        # Add navigation logic here
        pass

    def navigate_to_shop(self):
        """Handle navigation to shop screen"""
        # Add navigation logic here
        pass

    def rest(self):
        """Restore hero's health instantly"""
        hero_id = self.request.session.get('hero_id')
        if hero_id:
            rest_hero(hero_id)
            # Refresh the page to show updated health
            return

    def start_healing(self):
        """Start gradual healing over time"""
        hero_id = self.request.session.get('hero_id')
        if hero_id:
            start_hero_healing(hero_id)

    def exit_game(self):
        """Handle exiting the game"""
        # clear session hero_id or any other cleanup
        # redirect to index or login page
        self.request.session.pop('hero_id', None)
        return redirect('index')
