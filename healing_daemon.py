"""
Windows-compatible healing daemon for RPG game
Uses threading instead of Django-RQ to avoid Windows compatibility issues
"""
import os
import sys
import django
import threading
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add the project directory to Python path
project_dir = Path(__file__).parent
sys.path.append(str(project_dir))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'game.settings')
django.setup()

from hero.models import Hero
from django.db.models import F


class HealingDaemon:
    def __init__(self):
        self.healing_heroes = {}  # {hero_id: {'last_heal': datetime, 'thread': thread}}
        self.running = True
        self.heal_interval = 30  # seconds
        self.heal_amount = 1  # HP per heal

        # File to store healing state (persist across restarts)
        self.state_file = project_dir / 'healing_state.json'
        self.load_state()

        print(f"🏥 Healing Daemon started at {datetime.now()}")
        print(f"⏱️  Healing interval: {self.heal_interval} seconds")
        print(f"❤️  Heal amount: {self.heal_amount} HP")

    def load_state(self):
        """Load healing state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.healing_heroes = {int(k): v for k, v in data.items()}
                    print(f"📄 Loaded healing state for {len(self.healing_heroes)} heroes")
            except Exception as e:
                print(f"⚠️  Could not load healing state: {e}")

    def save_state(self):
        """Save healing state to file"""
        try:
            # Convert to serializable format
            data = {}
            for hero_id, info in self.healing_heroes.items():
                data[hero_id] = {
                    'last_heal': info.get('last_heal', datetime.now().isoformat()).isoformat(),
                    'active': True
                }

            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Could not save healing state: {e}")

    def start_hero_healing(self, hero_id):
        """Start healing process for a hero"""
        try:
            hero = Hero.objects.get(id=hero_id)

            if hero.current_health >= hero.max_health:
                print(f"✅ {hero.name} is already at full health")
                return False

            if hero_id in self.healing_heroes:
                print(f"🔄 {hero.name} is already being healed")
                return True

            # Start healing thread for this hero
            heal_thread = threading.Thread(
                target=self._heal_hero_loop,
                args=(hero_id,),
                daemon=True
            )

            self.healing_heroes[hero_id] = {
                'last_heal': datetime.now(),
                'thread': heal_thread
            }

            heal_thread.start()
            self.save_state()

            print(f"🚀 Started healing {hero.name} (ID: {hero_id})")
            return True

        except Hero.DoesNotExist:
            print(f"❌ Hero with ID {hero_id} not found")
            return False

    def stop_hero_healing(self, hero_id):
        """Stop healing process for a hero"""
        if hero_id in self.healing_heroes:
            del self.healing_heroes[hero_id]
            self.save_state()
            print(f"⏹️  Stopped healing for hero {hero_id}")
            return True
        return False

    def _heal_hero_loop(self, hero_id):
        """Main healing loop for a specific hero"""
        while hero_id in self.healing_heroes and self.running:
            try:
                hero = Hero.objects.get(id=hero_id)

                # Check if hero needs healing
                if hero.current_health >= hero.max_health:
                    print(f"✅ {hero.name} is fully healed! Stopping healing.")
                    self.stop_hero_healing(hero_id)
                    break

                # Check if hero is dead
                if hero.current_health <= 0:
                    print(f"💀 {hero.name} is dead. Stopping healing.")
                    self.stop_hero_healing(hero_id)
                    break

                # Heal the hero
                old_health = hero.current_health
                hero.current_health = min(hero.current_health + self.heal_amount, hero.max_health)
                hero.save()

                # Update last heal time
                self.healing_heroes[hero_id]['last_heal'] = datetime.now()

                print(f"❤️  Healed {hero.name}: {old_health} → {hero.current_health}/{hero.max_health} HP")

                # Wait for next heal
                time.sleep(self.heal_interval)

            except Hero.DoesNotExist:
                print(f"❌ Hero {hero_id} no longer exists. Stopping healing.")
                self.stop_hero_healing(hero_id)
                break
            except Exception as e:
                print(f"⚠️  Error healing hero {hero_id}: {e}")
                time.sleep(5)  # Wait a bit before retrying

    def rest_hero(self, hero_id):
        """Instantly heal hero to full health"""
        try:
            hero = Hero.objects.get(id=hero_id)

            if hero.current_health >= hero.max_health:
                print(f"✅ {hero.name} is already at full health")
                return False

            old_health = hero.current_health
            hero.current_health = hero.max_health
            hero.save()

            # Stop ongoing healing since hero is now full
            self.stop_hero_healing(hero_id)

            print(f"💤 {hero.name} rested: {old_health} → {hero.current_health}/{hero.max_health} HP")
            return True

        except Hero.DoesNotExist:
            print(f"❌ Hero with ID {hero_id} not found")
            return False

    def damage_hero(self, hero_id, damage):
        """Damage a hero and start healing"""
        try:
            hero = Hero.objects.get(id=hero_id)
            old_health = hero.current_health
            hero.current_health = max(0, hero.current_health - damage)
            hero.save()

            print(f"⚔️  Damaged {hero.name}: {old_health} → {hero.current_health}/{hero.max_health} HP")

            # Start healing if hero is alive and not at full health
            if hero.current_health > 0 and hero.current_health < hero.max_health:
                self.start_hero_healing(hero_id)

            return True

        except Hero.DoesNotExist:
            print(f"❌ Hero with ID {hero_id} not found")
            return False

    def status(self):
        """Show current healing status"""
        print(f"\n📊 Healing Daemon Status - {datetime.now()}")
        print(f"🔄 Active healing sessions: {len(self.healing_heroes)}")

        if not self.healing_heroes:
            print("😴 No heroes currently being healed")
            return

        for hero_id, info in self.healing_heroes.items():
            try:
                hero = Hero.objects.get(id=hero_id)
                last_heal = info.get('last_heal', 'Unknown')
                print(f"   🏥 {hero.name}: {hero.current_health}/{hero.max_health} HP (Last heal: {last_heal})")
            except Hero.DoesNotExist:
                print(f"   ❌ Hero {hero_id}: Not found")

    def run_interactive(self):
        """Run daemon in interactive mode for testing"""
        print("\n🎮 Interactive Healing Daemon")
        print("Commands:")
        print("  heal <hero_id>     - Start healing hero")
        print("  stop <hero_id>     - Stop healing hero")
        print("  rest <hero_id>     - Instantly heal hero to full")
        print("  damage <hero_id> <amount> - Damage hero")
        print("  status             - Show healing status")
        print("  heroes             - List all heroes")
        print("  quit               - Exit daemon")
        print()

        while self.running:
            try:
                command = input("Healing> ").strip().split()

                if not command:
                    continue

                cmd = command[0].lower()

                if cmd == 'quit':
                    break
                elif cmd == 'status':
                    self.status()
                elif cmd == 'heroes':
                    heroes = Hero.objects.all()
                    print(f"\n👥 All Heroes:")
                    for hero in heroes:
                        print(f"   ID {hero.id}: {hero.name} - {hero.current_health}/{hero.max_health} HP")
                elif cmd == 'heal' and len(command) > 1:
                    hero_id = int(command[1])
                    self.start_hero_healing(hero_id)
                elif cmd == 'stop' and len(command) > 1:
                    hero_id = int(command[1])
                    self.stop_hero_healing(hero_id)
                elif cmd == 'rest' and len(command) > 1:
                    hero_id = int(command[1])
                    self.rest_hero(hero_id)
                elif cmd == 'damage' and len(command) > 2:
                    hero_id = int(command[1])
                    damage = int(command[2])
                    self.damage_hero(hero_id, damage)
                else:
                    print("Unknown command or missing arguments")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")

        self.shutdown()

    def run_passive_mode(self):
        # for every hero not in combat and not at full health, start healing
        print("\n🎮 Passive Healing Daemon Mode")
        while self.running:
            try:
                heroes = Hero.objects.filter(
                    is_in_combat=False, current_health__lt=F('health'))
                for hero in heroes:
                    if hero.id not in self.healing_heroes:
                        self.start_hero_healing(hero.id)
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"Error in passive mode: {e}")

    def shutdown(self):
        """Gracefully shutdown the daemon"""
        print("\n🛑 Shutting down healing daemon...")
        self.running = False
        self.save_state()
        print("💾 State saved")
        print("👋 Goodbye!")


if __name__ == '__main__':
    daemon = HealingDaemon()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == 'status':
            daemon.status()
        elif command == 'heal' and len(sys.argv) > 2:
            hero_id = int(sys.argv[2])
            daemon.start_hero_healing(hero_id)
            daemon.run_interactive()
        elif command == 'damage' and len(sys.argv) > 3:
            hero_id = int(sys.argv[2])
            damage = int(sys.argv[3])
            daemon.damage_hero(hero_id, damage)
        elif command == 'rest' and len(sys.argv) > 2:
            hero_id = int(sys.argv[2])
            daemon.rest_hero(hero_id)
        elif command == 'passive':
            daemon.run_passive_mode()
        else:
            print("Usage: python healing_daemon.py [status|heal <id>|damage <id> <amount>|rest <id>]")
    else:
        # Run in interactive mode
        daemon.run_interactive()
