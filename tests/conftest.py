import pytest
from tracelab.api.service import Service


@pytest.fixture
async def service(tmp_path):
    service = Service(tmp_path / "app")
    yield service
    await service.close()


@pytest.fixture
def event_factory():
    def build(index=0, type="user", content="research question", tid="t", **extra):
        return {
            "id": f"{tid}:e{index}",
            "trajectoryId": tid,
            "index": index,
            "type": type,
            "content": content,
            "parentEventIds": [],
            "metadata": {},
            **extra,
        }

    return build
