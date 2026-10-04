import asyncio
from temporalio.client import Client
from temporalio.worker import Worker
from engineering.activities import ACTIVITIES
from engineering.config import ADDRESS, NAMESPACE, TASK_QUEUE
from engineering.workflow import EngineeringWorkflow


async def run() -> None:
    client = await Client.connect(ADDRESS, namespace=NAMESPACE)
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=[EngineeringWorkflow], activities=ACTIVITIES)
    await worker.run()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
