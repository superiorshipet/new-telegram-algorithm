import asyncio

from app.collector.worker import run

if __name__ == "__main__":
    asyncio.run(run())
