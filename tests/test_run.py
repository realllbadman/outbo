import socket

import pytest

import run


@pytest.mark.parametrize(
    "args",
    [
        [".venv/bin/python", "run.py", ""],
        ["/home/x/outboard/.venv/bin/python3", "/home/x/outboard/run.py", ""],
        [".venv/bin/python", "-m", "uvicorn", "app.main:app", "--port", "8030", ""],
    ],
)
def test_recognises_site_processes(args):
    assert run.is_site_process(args)


@pytest.mark.parametrize(
    "args",
    [
        ["nano", "run.py", ""],
        [".venv/bin/python", "-m", "pytest", ""],
        ["python3", "-m", "http.server", "8030", ""],
        [""],
    ],
)
def test_ignores_other_processes(args):
    assert not run.is_site_process(args)


def test_skips_a_port_that_is_in_use():
    with socket.socket() as holder:
        holder.bind((run.HOST, 0))
        holder.listen()
        taken = holder.getsockname()[1]
        assert not run.port_is_free(taken)
        assert run.first_free_port(taken) > taken


def test_uses_preferred_port_when_free():
    with socket.socket() as probe:
        probe.bind((run.HOST, 0))
        port = probe.getsockname()[1]
    assert run.first_free_port(port) == port
