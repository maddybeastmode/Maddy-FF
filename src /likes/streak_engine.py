"""
Streak Engine
Orchestrates concurrent like streaks with progress tracking and recovery.
"""

import asyncio
from typing import List
from dataclasses import dataclass, field

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..core.config_loader import get_config
from ..core.logger import setup_logger
from ..guests.manager import GuestAccount
from .sender import LikeSender, LikeResult

logger = setup_logger("streak")


@dataclass
class StreakResult:
    target_uid: str
    requested: int
    success: int = 0
    failed: int = 0
    errors: dict = field(default_factory=dict)
    duration_seconds: float = 0.0


class StreakEngine:
    """
    Manages like streak execution with concurrency control and progress display.
    """

    def __init__(self, like_sender: LikeSender):
        self.sender = like_sender
        self.config = get_config()
        self.semaphore = asyncio.Semaphore(self.config.settings.bot.max_workers)

    async def execute(self, target_uid: str, count: int, region: str = "ME") -> StreakResult:
        """
        Execute a like streak with progress bar, automatic verification,
        and dynamic replacement of dead guests.
        """
        start_time = asyncio.get_event_loop().time()
        result = StreakResult(target_uid=target_uid, requested=count)

        if count <= 0:
            logger.error("Requested like count must be greater than 0")
            return result

        # Get total available guests first
        available_count = await self.sender.guests.count_available(target_uid, region)
        if available_count < count:
            logger.warning(
                f"Only {available_count} guests currently available for {count} likes. "
                "The bot will run with available guests."
            )

        logger.info(f"🚀 Starting streak: {count} likes → {target_uid}")

        # Fetch initial guest pool
        guests_pool = await self.sender.guests.get_available_for_target(target_uid, region, limit=max(count * 2, 200))
        
        # Use an asyncio Queue to distribute guest accounts to workers
        guest_queue = asyncio.Queue()
        for g in guests_pool:
            guest_queue.put_nowait(g)

        success_count = 0
        failed_count = 0

        # Progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.completed}/{task.total} | ✅ {task.fields[success]} ❌ {task.fields[failed]}"),
        ) as progress:
            task = progress.add_task(
                f"Liking {target_uid}",
                total=count,
                success=0,
                failed=0,
            )

            counter_lock = asyncio.Lock()

            async def worker():
                nonlocal success_count, failed_count
                while True:
                    # Check if we already reached target likes
                    async with counter_lock:
                        if success_count >= count:
                            break

                    try:
                        guest = guest_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        # Queue is empty, try to fetch more guests from database if needed
                        await asyncio.sleep(0.1)  # Yield control
                        async with counter_lock:
                            if success_count >= count:
                                break
                            more_guests = await self.sender.guests.get_available_for_target(
                                target_uid, region, limit=50
                            )
                            if not more_guests:
                                # Wait/poll for new healthy guests to be added
                                await asyncio.sleep(2.0)
                                continue
                            for g in more_guests:
                                guest_queue.put_nowait(g)
                            continue

                    # Try to send like (will automatically handle/acquire JWT)
                    # Pass cached OAuth tokens to skip rate-limited OAuth step
                    like_result = await self.sender.send_like(
                        guest.uid, guest.password, target_uid, region,
                        open_id=getattr(guest, 'open_id', ''),
                        access_token=getattr(guest, 'access_token', '')
                    )

                    async with counter_lock:
                        if like_result.success:
                            if success_count < count:
                                success_count += 1
                                result.success = success_count
                                progress.update(task, completed=success_count, success=success_count)
                        else:
                            # If it was an authentication failure (JWT generation failed),
                            # verify the guest to update its database status (it will deactivate if needed)
                            # Only deactivate on real auth failures (blacklist/ban), NOT on 429 rate-limit
                            if like_result.http_code == 401 or "blacklist" in like_result.message.lower() or "blacklisted" in like_result.message.lower():
                                await self.sender.guests.verify_guest(guest, self.sender.jwt)
                            # On 429, just wait and retry — don't deactivate
                            
                            failed_count += 1
                            result.failed = failed_count
                            result.errors[like_result.message] = result.errors.get(like_result.message, 0) + 1
                            progress.update(task, failed=failed_count)

                    # Handle rate limit backoff
                    if like_result.retry_after > 0:
                        await asyncio.sleep(like_result.retry_after)

            # Spawn workers up to max_workers
            num_workers = min(self.config.settings.bot.max_workers, count)
            if num_workers < 1:
                num_workers = 1
                
            workers_tasks = [asyncio.create_task(worker()) for _ in range(num_workers)]
            await asyncio.gather(*workers_tasks)


        result.duration_seconds = asyncio.get_event_loop().time() - start_time
        logger.info(
            f"✅ Streak complete: {result.success}/{count} succeeded "
            f"in {result.duration_seconds:.1f}s"
        )
        return result
