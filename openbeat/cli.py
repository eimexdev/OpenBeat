from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .analysis import load_or_analyze, write_lua_analysis
from .artifacts import create_click_track


def analyze_command(args: argparse.Namespace) -> int:
    analysis = load_or_analyze(args.audio)
    if args.format == "json":
        payload = json.dumps(asdict(analysis), indent=2)
        if args.output:
            Path(args.output).write_text(payload + "\n")
        else:
            print(payload)
        return 0

    if not args.output:
        raise SystemExit("--output is required for --format lua")

    write_lua_analysis(analysis, args.output)
    return 0


def click_track_command(args: argparse.Namespace) -> int:
    output, analysis = create_click_track(args.audio, args.output, args.mode)
    print(
        json.dumps(
            {
                "output_path": output,
                "tempo_bpm": analysis.tempo_bpm,
                "mode": args.mode,
            }
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openbeat")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze an audio file for beats.")
    analyze.add_argument("--audio", required=True, help="Audio file to analyze.")
    analyze.add_argument("--format", choices=["json", "lua"], default="json")
    analyze.add_argument("--output", help="Optional output path.")
    analyze.set_defaults(func=analyze_command)

    click_track = subparsers.add_parser("click-track", help="Render a click track wav file.")
    click_track.add_argument("--audio", required=True, help="Audio file to analyze.")
    click_track.add_argument("--mode", choices=["quantized", "raw"], default="quantized")
    click_track.add_argument("--output", required=True, help="Where to write the wav file.")
    click_track.set_defaults(func=click_track_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
