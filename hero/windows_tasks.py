"""
Simple healing tasks for Windows - No Django-RQ required
Communicates with healing daemon via file-based messaging
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from .models import Hero

# Path to communicate with daemon
DAEMON_COMMANDS_FILE = Path(__file__).parent.parent / 'daemon_commands.json'
DAEMON_STATUS_FILE = Path(__file__).parent.parent / 'daemon_status.json'


def send_daemon_command(command, **kwargs):
    """Send a command to the healing daemon"""
    try:
        command_data = {
            'command': command,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }

        # Write command to file
        with open(DAEMON_COMMANDS_FILE, 'w') as f:
            json.dump(command_data, f)

        print(f"📤 Sent command to daemon: {command}")
        return True

    except Exception as e:
        print(f"❌ Failed to send daemon command: {e}")
        return False


def start_hero_healing(hero_id):
    """Start healing process for a hero via daemon"""
    return send_daemon_command('start_healing', hero_id=hero_id)


def stop_hero_healing(hero_id):
    """Stop healing process for a hero via daemon"""
    return send_daemon_command('stop_healing', hero_id=hero_id)


def rest_hero(hero_id):
    """Instantly restore a hero to full health"""
    try:
        hero = Hero.objects.get(id=hero_id)

        if hero.current_health < hero.health:
            hero.current_health = hero.health
            hero.save()
            print(f"💤 {hero.name} rested and is now at full health!")

            # Tell daemon to stop healing this hero
            stop_hero_healing(hero_id)
            return True
        else:
            print(f"✅ {hero.name} is already at full health")
            return False

    except Hero.DoesNotExist:
        print(f"❌ Hero with ID {hero_id} not found")
        return False


def damage_hero(hero_id, damage):
    """Damage a hero and start healing"""
    try:
        hero = Hero.objects.get(id=hero_id)
        old_health = hero.current_health
        hero.current_health = max(0, hero.current_health - damage)
        hero.save()

        print(f"⚔️  Damaged {hero.name}: {old_health} → {hero.current_health}/{hero.health} HP")


        return True

    except Hero.DoesNotExist:
        print(f"❌ Hero with ID {hero_id} not found")
        return False


def simple_heal_hero(hero_id, heal_amount=5):
    """Simple healing function that heals immediately"""
    try:
        hero = Hero.objects.get(id=hero_id)
        old_health = hero.current_health
        hero.current_health = min(hero.current_health + heal_amount, hero.health)
        hero.save()

        print(f"❤️  Healed {hero.name}: {old_health} → {hero.current_health}/{hero.health} HP")
        return True

    except Hero.DoesNotExist:
        print(f"❌ Hero with ID {hero_id} not found")
        return False


def get_daemon_status():
    """Get status from healing daemon"""
    try:
        if DAEMON_STATUS_FILE.exists():
            with open(DAEMON_STATUS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not read daemon status: {e}")

    return {'status': 'unknown', 'healing_heroes': []}


# Fallback threading-based healing for when daemon is not running
def heal_hero_over_time_simple(hero_id, duration_seconds=300):
    """
    Heal hero over time using threading (fallback when daemon not available)
    """
    def healing_thread():
        try:
            start_time = time.time()

            while (time.time() - start_time) < duration_seconds:
                hero = Hero.objects.get(id=hero_id)

                if hero.current_health >= hero.health:
                    print(f"✅ {hero.name} is fully healed!")
                    break

                if hero.current_health <= 0:
                    print(f"💀 {hero.name} is dead. Stopping healing.")
                    break

                old_health = hero.current_health
                hero.current_health = min(hero.current_health + 1, hero.health)
                hero.save()

                print(f"❤️  Background heal: {hero.name} {old_health} → {hero.current_health}/{hero.health} HP")

                time.sleep(30)  # Wait 30 seconds

        except Hero.DoesNotExist:
            print(f"❌ Hero with ID {hero_id} not found")

    # Start healing in background thread
    thread = threading.Thread(target=healing_thread, daemon=True)
    thread.start()
    return thread
