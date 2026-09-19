from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-manim-docker",
        action="store_true",
        default=False,
        help="run integration tests that start the pinned Manim Docker image",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--run-manim-docker"):
        return
    skip_docker = pytest.mark.skip(reason="use --run-manim-docker to run container renders")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_docker)
