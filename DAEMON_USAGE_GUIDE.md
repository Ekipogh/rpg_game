# 🏥 Healing Daemon Usage Guide

## Quick Start

### 🚀 **Start Everything at Once**
```cmd
# Start both Django server AND healing daemon
start_windows_rpg.bat
```
This opens two windows:
- **Django Server**: Your web game at http://127.0.0.1:8000/
- **Healing Daemon**: Background healing system

---

## Manual Usage

### 1. **Interactive Mode (Recommended for Testing)**
```cmd
# Start daemon in interactive mode
python healing_daemon.py
```

**Available Commands:**
```
heal <hero_id>           - Start healing hero
stop <hero_id>           - Stop healing hero
rest <hero_id>           - Instantly heal hero to full
damage <hero_id> <amount> - Damage hero and start auto-healing
status                   - Show healing status
heroes                   - List all heroes with health
quit                     - Exit daemon
```

**Example Session:**
```
Healing> heroes
👥 All Heroes:
   ID 7: Olly - 84/104 HP
   ID 8: Mark - 100/100 HP

Healing> damage 7 20
⚔️  Damaged Olly: 84 → 64/104 HP
🚀 Started healing Olly (ID: 7)

Healing> status
📊 Healing Daemon Status - 2025-09-07 18:15:32
🔄 Active healing sessions: 1
   🏥 Olly: 65/104 HP (Last heal: 2025-09-07 18:15:32)

Healing> rest 7
💤 Olly rested: 65 → 104/104 HP
✅ Olly is fully healed! Stopping healing.

Healing> quit
```

### 2. **Command Line Mode**
```cmd
# Quick commands without interactive mode
python healing_daemon.py status
python healing_daemon.py heal 7
python healing_daemon.py damage 7 30
python healing_daemon.py rest 7
```

### 3. **Background Mode (for Production)**
```cmd
# Start daemon in background (keeps running)
start "Healing Daemon" python healing_daemon.py
```

---

## Integration with Django

### **From Django Web Interface:**
- **Rest Button**: Click "Rest" in your game → Instantly heals hero to full
- **Automatic Healing**: When hero takes damage → Auto-starts healing

### **From Django Management Commands:**
```cmd
# Damage a hero (starts auto-healing)
python manage.py damage_hero 7 25

# This calls the daemon via windows_tasks.py
```

---

## Healing System Features

### **Automatic Healing:**
- ❤️ Heals **1 HP every 30 seconds**
- 🔄 Continues until hero reaches full health
- 🛑 Stops automatically when fully healed
- 💀 Stops if hero dies (0 HP)

### **Persistent State:**
- 💾 Saves healing state to `healing_state.json`
- 🔄 Resumes healing after daemon restart
- 📊 Tracks last heal time per hero

### **Real-time Monitoring:**
```
❤️  Healed Olly: 65 → 66/104 HP
❤️  Healed Olly: 66 → 67/104 HP
❤️  Healed Olly: 67 → 68/104 HP
✅ Olly is fully healed! Stopping healing.
```

---

## Typical Workflows

### **🎮 Game Development/Testing:**
1. Start interactive daemon: `python healing_daemon.py`
2. Create/damage heroes for testing
3. Watch real-time healing
4. Test rest functionality

### **🏃 Quick Game Session:**
1. Run: `start_windows_rpg.bat`
2. Play your game in browser
3. Heroes heal automatically in background
4. Close both windows when done

### **🛠️ Debugging:**
```cmd
# Check what's happening
python healing_daemon.py status

# List all heroes and their health
python healing_daemon.py
Healing> heroes

# Manually heal/damage for testing
Healing> damage 7 50
Healing> heal 7
```

---

## Files Created by Daemon

- **`healing_state.json`**: Saves which heroes are being healed
- **`daemon_commands.json`**: Communication file with Django
- **`daemon_status.json`**: Status information

---

## Troubleshooting

### **"Hero not found" errors:**
```cmd
# Check what heroes exist
python healing_daemon.py
Healing> heroes
```

### **Daemon not responding:**
```cmd
# Restart daemon
# Close daemon window, then run:
python healing_daemon.py
```

### **Django integration issues:**
- Make sure `hero/windows_tasks.py` exists
- Check that home_screen.py imports from windows_tasks

---

## Pro Tips

- 🔍 **Monitor in real-time**: Keep daemon window open to see healing happen
- 💾 **Persistent healing**: Heroes continue healing even if you restart
- ⚡ **Instant healing**: Use `rest` command for immediate full heal
- 🎯 **Testing**: Use `damage` command to create injured heroes quickly

Your healing daemon is a powerful, Windows-native background system that handles all hero healing automatically! 🎮⚔️
