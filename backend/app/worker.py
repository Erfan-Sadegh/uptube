from redis import Redis
from rq import Worker

from app.core.config import get_settings
from app.tasks import QUEUE_NAME


def main() -> None:
    settings = get_settings()
    worker = Worker([QUEUE_NAME], connection=Redis.from_url(settings.redis_url))
    worker.work()


if __name__ == "__main__":
    main()
