# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.append(str(project_dir))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "game.settings")
django.setup()


class BattleDaemon:
    def __init__(self):
        self.running = True

    def _battle_loop(self):
        while self.running:
            try:
                # Fetch battles that are in progress
                battles = Battle.objects.filter(status=Battle.Status.IN_PROGRESS)

                for battle in battles:
                    # Process each battle
                    self.process_battle(battle)

                # Sleep for a short duration to avoid busy waiting
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Battle daemon interrupted. Exiting...")
                self.running = False
            except Exception as e:
                logger.error(f"Error in battle loop: {e}")


if __name__ == "__main__":
    battle_daemon = BattleDaemon()
