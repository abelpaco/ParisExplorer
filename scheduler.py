"""
Scheduler Module
Handles automated posting at scheduled times
"""

import logging
import time
import schedule
from datetime import datetime, timedelta
from typing import Callable, Dict, Any
import pytz

logger = logging.getLogger(__name__)

# Local time at which the schedules are rebuilt. `schedule` only understands
# system local time, so the configured times are converted once a day: this
# keeps the conversion correct across DST transitions on either side.
REPLAN_TIME = "00:01"


class AutomationScheduler:
    """Manages scheduled posts and automation tasks"""
    
    def __init__(self, config: Dict[str, Any], post_callback: Callable):
        """
        Initialize scheduler
        
        Args:
            config: Configuration dictionary
            post_callback: Function to call for posting content
        """
        self.config = config
        self.post_callback = post_callback
        self.schedule_config = config.get('schedule', {})
        self.enabled = self.schedule_config.get('enabled', True)
        self.timezone = pytz.timezone(
            self.schedule_config.get('timezone', 'Europe/Paris')
        )
        self.running = False
        
        # Setup scheduled jobs
        self._setup_schedules()
    
    def _to_local_time(self, post_time: str) -> str:
        """
        Convert a wall-clock time from the configured timezone to local time

        `schedule` always plans against the system clock, so on a UTC host
        `schedule.every().day.at("09:00")` fires at 11:00 Paris time in summer.
        The conversion is anchored on the *next* occurrence of `post_time` so
        that the UTC offset actually in effect that day (DST included) is used.

        Args:
            post_time: Wall-clock time "HH:MM" or "HH:MM:SS" in self.timezone

        Returns:
            Equivalent wall-clock time "HH:MM:SS" in the system's local time
        """
        parts = [int(part) for part in post_time.split(':')]
        hour, minute = parts[0], parts[1]
        second = parts[2] if len(parts) > 2 else 0

        now = datetime.now(self.timezone)
        target = now.replace(
            hour=hour, minute=minute, second=second, microsecond=0
        )
        if target <= now:
            target += timedelta(days=1)

        # Re-localize: replace() keeps the *current* UTC offset, which may
        # differ from the one in effect on the target day (DST switch)
        target = self.timezone.localize(target.replace(tzinfo=None))

        # astimezone() without argument converts to the system's local time
        return target.astimezone().strftime('%H:%M:%S')

    def _setup_schedules(self):
        """Setup scheduled posting times"""
        schedule.clear()

        if not self.enabled:
            logger.info("Scheduler is disabled in configuration")
            return

        post_times = self.schedule_config.get('post_times', [])

        if not post_times:
            logger.warning("No post times configured")
            return

        for post_time in post_times:
            local_time = self._to_local_time(post_time)
            schedule.every().day.at(local_time).do(self._scheduled_post)
            logger.info(
                f"Scheduled post at {post_time} {self.timezone} "
                f"(local time {local_time})"
            )

        # Rebuild the schedules every day: the offset between the configured
        # timezone and the system clock changes on each DST transition
        schedule.every().day.at(REPLAN_TIME).do(self._setup_schedules)

        logger.info(f"Setup complete. {len(post_times)} scheduled posts configured")
    
    def _scheduled_post(self):
        """Execute scheduled post"""
        try:
            current_time = datetime.now(self.timezone).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Executing scheduled post at {current_time}")
            
            # Call the post callback
            success = self.post_callback()
            
            if success:
                logger.info("Scheduled post completed successfully")
            else:
                logger.warning("Scheduled post had issues")
                
        except Exception as e:
            logger.error(f"Error during scheduled post: {e}")
    
    def start(self):
        """Start the scheduler"""
        if not self.enabled:
            logger.info("Scheduler is disabled")
            return
        
        self.running = True
        logger.info("Scheduler started")
        
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Scheduler stopped")
    
    def run_now(self):
        """Execute a post immediately (manual trigger)"""
        logger.info("Manual post triggered")
        return self._scheduled_post()
    
    def get_next_run_time(self) -> str:
        """Get the next scheduled run time"""
        next_run = schedule.next_run()
        if next_run:
            return next_run.strftime('%Y-%m-%d %H:%M:%S')
        return "No scheduled runs"
    
    def list_jobs(self) -> list:
        """List all scheduled jobs"""
        jobs = []
        for job in schedule.jobs:
            jobs.append({
                'time': str(job.at_time) if hasattr(job, 'at_time') else 'N/A',
                'next_run': job.next_run.strftime('%Y-%m-%d %H:%M:%S') if job.next_run else 'N/A',
                'last_run': job.last_run.strftime('%Y-%m-%d %H:%M:%S') if job.last_run else 'Never'
            })
        return jobs
