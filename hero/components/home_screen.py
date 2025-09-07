from django_unicorn.components import UnicornView


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
        """Restore hero's health"""
        # You can access the hero from the parent context
        # For now, just a placeholder - you might want to implement
        # actual rest logic or redirect to a rest view
        pass
