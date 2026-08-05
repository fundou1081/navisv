"""elk_layout.py - High-level Python wrapper for ELK layout + SVG render.

Orchestrates the two-step pipeline:
  1. Node.js subprocess invokes ELK.bundled.js for real layered layout
  2. Python renderer reads positioned JSON + emits SVG

Usage from Python:
  from navisv.tools.elk_layout import run_layout_and_render
  run_layout_and_render(elk_json, 'out.svg', title='counter', direction='RIGHT')

CLI:
  python -m navisv.tools.elk_layout <elk_input.json> <out.svg> [--direction=RIGHT]
"""
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, Optional

# Path to bundled ELK (relative to this module)
_HERE = os.path.dirname(os.path.abspath(__file__))
ELK_BUNDLED_JS = os.path.join(_HERE, '..', 'data', 'elk.bundled.js')
RUN_ELK_JS = os.path.join(_HERE, 'run_elk.js')


def _check_deps() -> None:
    """Verify Node.js + ELK bundled + run_elk.js are available."""
    if not os.path.exists(ELK_BUNDLED_JS):
        raise FileNotFoundError(
            f'ELK bundled not found at {ELK_BUNDLED_JS}. '
            f'Run from navisv repo root or set ELK_PATH env var.'
        )
    if not os.path.exists(RUN_ELK_JS):
        raise FileNotFoundError(f'run_elk.js not found at {RUN_ELK_JS}')
    try:
        subprocess.run(['node', '--version'], check=True, capture_output=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f'Node.js not available: {e}')


def run_elk_layout(elk_json: Dict[str, Any], direction: str = 'RIGHT') -> Dict[str, Any]:
    """Run ELK layered layout via Node.js subprocess.

    Args:
        elk_json: ELK input JSON (from ElkExporter.to_elk_json())
        direction: 'RIGHT' (default, horizontal flow), 'DOWN', 'UP', 'LEFT'

    Returns:
        ELK positioned JSON with x/y per node + sectioned edges.
    """
    _check_deps()
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as in_f:
        json.dump(elk_json, in_f)
        in_path = in_f.name
    out_path = in_path.replace('.json', '.out.json')
    try:
        result = subprocess.run(
            ['node', RUN_ELK_JS, in_path, out_path, f'--direction={direction}'],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f'ELK layout failed (rc={result.returncode}): '
                f'stdout={result.stdout!r} stderr={result.stderr!r}'
            )
        with open(out_path) as f:
            return json.load(f)
    finally:
        for p in [in_path, out_path]:
            if os.path.exists(p):
                os.unlink(p)


def run_layout_and_render(elk_json: Dict[str, Any], output_svg: str,
                          title: str = 'navisv — ELK layered',
                          subtitle: str = '',
                          direction: str = 'RIGHT') -> str:
    """One-shot: layout + render to SVG.

    Returns: output SVG file path.
    """
    # Late import to avoid circular deps (render_svg imports from this module)
    from .render_svg import render_svg

    positioned = run_elk_layout(elk_json, direction=direction)
    svg = render_svg(positioned, title=title, subtitle=subtitle)
    os.makedirs(os.path.dirname(os.path.abspath(output_svg)) or '.', exist_ok=True)
    with open(output_svg, 'w') as f:
        f.write(svg)
    return output_svg


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Run ELK layout + render to SVG')
    parser.add_argument('input', help='ELK input JSON (from ElkExporter)')
    parser.add_argument('output', help='Output SVG path')
    parser.add_argument('--direction', default='RIGHT',
                        choices=['RIGHT', 'DOWN', 'UP', 'LEFT'])
    parser.add_argument('--title', default='navisv — ELK layered')
    parser.add_argument('--subtitle', default='')
    args = parser.parse_args()

    with open(args.input) as f:
        elk_json = json.load(f)
    out = run_layout_and_render(
        elk_json, args.output,
        title=args.title, subtitle=args.subtitle, direction=args.direction,
    )
    print(f"✅ {out}")


if __name__ == '__main__':
    main()