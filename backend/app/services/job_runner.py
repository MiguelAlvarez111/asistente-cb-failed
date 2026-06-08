from typing import Callable, Protocol

from fastapi import BackgroundTasks


class JobRunner(Protocol):
    def enqueue(self, job_id: str, upload_id: str, task: Callable[[str, str], None]) -> None:
        ...


class BackgroundTasksJobRunner:
    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self.background_tasks = background_tasks

    def enqueue(self, job_id: str, upload_id: str, task: Callable[[str, str], None]) -> None:
        self.background_tasks.add_task(task, job_id, upload_id)

