from rq import Connection, Worker

from queueing import get_sync_redis


def main():
    redis_conn = get_sync_redis()
    with Connection(redis_conn):
        worker = Worker(["sessions"])
        worker.work()


if __name__ == "__main__":
    main()
