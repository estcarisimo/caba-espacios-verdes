"""Command-line entry point for the green-space pipeline."""

from __future__ import annotations

import argparse

from caba_espacios_verdes import __version__
from caba_espacios_verdes.paths import Layout
from caba_espacios_verdes.sources import DEFAULT_OSM_DATE


def _layout(args: argparse.Namespace) -> Layout:
    return Layout.from_options(args.data_dir, args.results_dir, args.figures_dir).ensure()


def _add_dirs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Downloaded and intermediate files (default: ./data or $CABA_DATA_DIR)",
    )
    parser.add_argument(
        "--results-dir",
        default=None,
        help="CSV and JSON summaries (default: ./results or $CABA_RESULTS_DIR)",
    )
    parser.add_argument(
        "--figures-dir",
        default=None,
        help="PNG maps (default: ./figures or $CABA_FIGURES_DIR)",
    )


def build_parser() -> argparse.ArgumentParser:
    directories = argparse.ArgumentParser(add_help=False)
    _add_dirs(directories)
    parser = argparse.ArgumentParser(
        prog="caba-espacios-verdes",
        description=(
            "Access to public green space in Ciudad Autónoma de Buenos Aires. "
            "Stages: download, coverage, population, quality, maps."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"caba-espacios-verdes {__version__}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    download = commands.add_parser(
        "download",
        parents=[directories],
        help="Download OSM, barrios and the census layer",
    )
    download.add_argument(
        "--osm-date",
        default=DEFAULT_OSM_DATE,
        help=f"Overpass attic date YYYY-MM-DD, or 'now' (default: {DEFAULT_OSM_DATE})",
    )
    download.add_argument(
        "--force", action="store_true", help="Re-download files that already exist"
    )

    commands.add_parser(
        "coverage",
        parents=[directories],
        help="Build polygons and the 500 m coverage scenarios",
    )
    commands.add_parser(
        "population",
        parents=[directories],
        help="Weight coverage by the 2022 census and run 2SFCA",
    )

    quality = commands.add_parser(
        "quality",
        parents=[directories],
        help="Sentinel-2 NDVI composite, vegetation metrics and vegetated 2SFCA",
    )
    quality.add_argument(
        "--skip-canopy",
        action="store_true",
        help="Do not download the Meta/WRI canopy-height tiles",
    )
    quality.add_argument(
        "--rebuild-composite",
        action="store_true",
        help="Rebuild the Sentinel-2 median even if it already exists",
    )

    maps = commands.add_parser(
        "maps",
        parents=[directories],
        help="Draw the PNG maps (and the coverage HTML map)",
    )
    maps.add_argument(
        "--only",
        choices=["coverage", "population", "quality", "all"],
        default="all",
        help="Which map set to draw (default: all)",
    )

    everything = commands.add_parser("all", parents=[directories], help="Run every stage in order")
    everything.add_argument("--osm-date", default=DEFAULT_OSM_DATE)
    everything.add_argument("--force", action="store_true")
    everything.add_argument("--skip-canopy", action="store_true")
    everything.add_argument("--rebuild-composite", action="store_true")

    commands.add_parser("version", parents=[directories], help="Print the version")
    return parser


def _maps(layout: Layout, only: str) -> None:
    if only in {"coverage", "all"}:
        from caba_espacios_verdes.maps_coverage import run as coverage_maps

        coverage_maps(layout)
    if only in {"population", "all"}:
        from caba_espacios_verdes.maps_population import run as population_maps

        population_maps(layout)
    if only in {"quality", "all"}:
        from caba_espacios_verdes.maps_quality import run as quality_maps

        quality_maps(layout)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "version":
        print(f"caba-espacios-verdes {__version__}")
        return
    layout = _layout(args)
    if args.command == "download":
        from caba_espacios_verdes.download import download_inputs

        download_inputs(layout, osm_date=args.osm_date, force=args.force)
    elif args.command == "coverage":
        from caba_espacios_verdes.coverage import run

        run(layout)
    elif args.command == "population":
        from caba_espacios_verdes.population import run

        run(layout)
    elif args.command == "quality":
        from caba_espacios_verdes.quality import run as metrics
        from caba_espacios_verdes.quality_composite import run as composite

        composite(layout, force=args.rebuild_composite)
        metrics(layout, skip_canopy=args.skip_canopy)
    elif args.command == "maps":
        _maps(layout, args.only)
    elif args.command == "all":
        from caba_espacios_verdes.coverage import run as coverage
        from caba_espacios_verdes.download import download_inputs
        from caba_espacios_verdes.population import run as population
        from caba_espacios_verdes.quality import run as metrics
        from caba_espacios_verdes.quality_composite import run as composite

        download_inputs(layout, osm_date=args.osm_date, force=args.force)
        coverage(layout)
        population(layout)
        composite(layout, force=args.rebuild_composite)
        metrics(layout, skip_canopy=args.skip_canopy)
        _maps(layout, "all")
    else:
        parser.error(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
