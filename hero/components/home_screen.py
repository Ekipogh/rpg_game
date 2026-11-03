from django_unicorn.components import UnicornView
from django.shortcuts import redirect
from hero.dungeon import enter_or_resume


class HomeScreenView(UnicornView):
    """Home screen component for the RPG game"""

    def navigate_to_battle(self):
        """Handle navigation to battle screen"""
        hero_id = self.request.session.get('hero_id')
        if not hero_id:
            return redirect('index')
        result = enter_or_resume(hero_id)
        if result == 'invalid':
            return redirect('index')
        if result == 'not_healed':
            return redirect('home')
        return redirect('dungeon')

    def navigate_to_shop(self):
        """Handle navigation to shop screen"""
        # Add navigation logic here
        pass

    def navigate_to_inventory(self):
        return redirect('inventory')

    def exit_game(self):
        """Handle exiting the game"""
        # clear session hero_id or any other cleanup
        # redirect to index or login page
        self.request.session.pop('hero_id', None)
        return redirect('index')
