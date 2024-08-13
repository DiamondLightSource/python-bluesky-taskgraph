from argparse import ArgumentParser

from . import __version__

__all__ = ["main"]


def main(args=None):
    parser = ArgumentParser()
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(args)
    # TODO


# test with: pipenv run python -m bluesky_taskgraph_runner
if __name__ == "__main__":
    main()
