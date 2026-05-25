from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from typing import Callable


class NewsScheduler:
    def __init__(self, pipeline_factory: Callable, cron_expr: str = "0 8 * * *"):
        self.scheduler = BackgroundScheduler()
        self.pipeline_factory = pipeline_factory
        self.cron_expr = cron_expr

    def start(self):
        parts = self.cron_expr.split()
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )
        self.scheduler.add_job(
            self._run_job,
            trigger,
            id="news_collection",
            replace_existing=True,
        )
        self.scheduler.start()
        print(f"[Scheduler] 定时任务已启动，cron: {self.cron_expr}")

    def _run_job(self):
        print("[Scheduler] 触发定时采集...")
        pipeline = self.pipeline_factory()
        pipeline.run(trigger="scheduled")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            print("[Scheduler] 已停止")
