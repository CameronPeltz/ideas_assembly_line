"""Run the command-line interface as a module or package directory."""

if __package__:
    from .cli import main
else:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from house_floor_schedule.cli import main

main()
