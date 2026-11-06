"""Standalone battle worker: python battle_daemon.py [run|status|retry ID]."""
import argparse
import logging
import math
import os
from pathlib import Path
import signal
import sys
import threading
import time
from uuid import uuid4

logger = logging.getLogger("battle_daemon")


def setup_django():
    project_dir = str(Path(__file__).resolve().parent)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "game.settings")
    import django
    django.setup()


class BattleDaemon:
    def __init__(self, poll_interval=0.1, batch_size=100):
        if not math.isfinite(poll_interval) or not 0.01 <= poll_interval <= 1:
            raise ValueError("Poll interval must be between 0.01 and 1 second")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("Batch size must be positive")
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.token = str(uuid4())
        self.stop_event = threading.Event()
        self._clocks = {}

    def shutdown(self, *_):
        self.stop_event.set()

    def tick(self):
        from django.db import close_old_connections, OperationalError
        from django.db.models import Q
        from django.utils import timezone
        from battle.models import Battle
        from battle.services import (MAX_BATCH_MS, LeaseLost, discover_battles,
                                     fence, pause_battle, process_battle)
        close_old_connections()
        fence(self.token)
        discover_battles(self.token, self.batch_size)
        ids = list(Battle.objects.filter(status__in=["PENDING", "ACTIVE", "RESOLVING"])
                   .filter(Q(next_due_at__lte=timezone.now()) | Q(next_due_at__isnull=True))
                   .order_by("next_due_at", "pk").values_list("pk", flat=True)[:self.batch_size])
        for battle_id in ids:
            if self.stop_event.is_set():
                break
            now = time.monotonic()
            baseline = self._clocks.get(battle_id, now)
            elapsed_ms = min(MAX_BATCH_MS, max(0, int((now - baseline) * 1000)))
            try:
                status = process_battle(battle_id, self.token, elapsed_ms)
            except (LeaseLost, OperationalError):
                raise
            except Exception as exc:
                logger.exception("Pausing battle %s", battle_id)
                pause_battle(battle_id, self.token, exc)
                self._clocks.pop(battle_id, None)
                continue
            self._clocks[battle_id] = baseline + elapsed_ms / 1000
            if status in {"FINISHED", "PAUSED_ERROR"}:
                self._clocks.pop(battle_id, None)
                logger.info("Battle %s: %s", battle_id, status)
        return len(ids)

    def run(self, once=False, retry_id=None):
        from django.db import OperationalError, connections
        from battle.services import LeaseLost, acquire_lease, release_lease, retry_battle
        if not acquire_lease(self.token):
            raise LeaseLost("Another battle daemon already owns the worker lease")
        self._clocks.clear()
        logger.info("Battle daemon started (%s)", self.token)
        try:
            if retry_id is not None:
                retry_battle(retry_id, self.token)
            failures = 0
            while not self.stop_event.is_set():
                try:
                    self.tick()
                    failures = 0
                except OperationalError:
                    failures += 1
                    logger.exception("Database operation failed (attempt %s/3)", failures)
                    if once or failures >= 3:
                        raise
                if once:
                    break
                self.stop_event.wait(min(1.0, self.poll_interval * 2**failures))
        finally:
            try:
                release_lease(self.token)
            finally:
                connections.close_all()
                logger.info("Battle daemon stopped")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=["run", "status", "retry"], default="run")
    parser.add_argument("battle_id", nargs="?", type=int)
    parser.add_argument("--once", action="store_true", help="Process one bounded pass and exit")
    parser.add_argument("--poll-interval", type=float, default=0.1)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args(argv)
    if (args.action == "retry") != (args.battle_id is not None):
        parser.error("retry requires a battle ID; other actions do not accept one")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    setup_django()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.db.models import Count
    from django.utils import timezone
    from battle.models import Battle, BattleWorkerLease
    try:
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise RuntimeError("Unapplied migrations. Run python manage.py migrate before starting the daemon.")
        if args.action == "status":
            for row in Battle.objects.values("status").annotate(count=Count("pk")).order_by("status"):
                print(f'{row["status"]}: {row["count"]}')
            lease = BattleWorkerLease.objects.filter(name="battle-worker").first()
            print("Worker: " + ("running" if lease and lease.expires_at and lease.expires_at > timezone.now() else "stopped"))
            return 0
        daemon = BattleDaemon(args.poll_interval, args.batch_size)
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, daemon.shutdown)
        daemon.run(once=args.once, retry_id=args.battle_id)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logger.exception("Battle daemon failed")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
