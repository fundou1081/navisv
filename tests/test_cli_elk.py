"""
test_cli_elk.py - CLI 测试: navisv elk <file> (Stage 3)

覆盖范围:
- argparse 入口 (--help, --view, --output, --filter-clock-reset, --direction)
- HTML/SVG/PNG 3 种输出格式
- 3 个视图 (dataflow/controlflow/modules)
- 默认 filter_clock_reset=True (Stage 2.9 默认值)
- 真实 counter.sv 端到端
"""
import os
import subprocess
import sys

import pytest

# navisv repo root
NAVISV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTER_SV = os.path.join(NAVISV_ROOT, 'tests', 'fixtures', 'elk_counter.sv')


def _run_elk_cli(*args, expect_returncode=0):
    """Run `python3 cli.py elk <args>` and return (stdout, stderr, returncode)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(NAVISV_ROOT, 'cli.py'), 'elk', *args],
        capture_output=True, text=True, timeout=60,
    )
    if expect_returncode == 0:
        assert proc.returncode == 0, f"stderr={proc.stderr}"
    return proc.stdout, proc.stderr, proc.returncode


class TestElkCliArgparse:
    """Stage 3 - argparse 入口"""

    def test_elk_help(self):
        """navisv elk --help 应列出 --view, --output, --filter-clock-reset 等"""
        out, _, _ = _run_elk_cli('--help')
        assert '--view' in out
        assert '--output' in out
        assert '--filter-clock-reset' in out
        assert '--direction' in out
        assert 'dataflow' in out
        assert 'controlflow' in out
        assert 'modules' in out

    def test_elk_in_main_help(self):
        """navisv --help 应包含 elk 子命令"""
        proc = subprocess.run(
            [sys.executable, os.path.join(NAVISV_ROOT, 'cli.py'), '--help'],
            capture_output=True, text=True, timeout=10,
        )
        assert 'elk' in proc.stdout


class TestElkCliDataflowView:
    """Stage 3 - dataflow 视图 (默认)"""

    def test_html_output_default(self, tmp_path):
        """不指定 --output 应生成 <basename>.elk.html"""
        cwd_before = os.getcwd()
        # counter.sv 的 basename = elk_counter → 默认输出 elk_counter.elk.html
        default_path = os.path.join(cwd_before, 'elk_counter.elk.html')
        if os.path.exists(default_path):
            os.remove(default_path)
        try:
            out, _, _ = _run_elk_cli(str(COUNTER_SV))
            assert 'ELK 输出' in out
            assert 'view: dataflow' in out
            assert 'filter_clock_reset: True' in out
            assert os.path.exists(default_path), f"Expected HTML at {default_path}"
        finally:
            if os.path.exists(default_path):
                os.remove(default_path)

    def test_explicit_html_output(self, tmp_path):
        """-o path.html 应输出到指定路径"""
        out_html = str(tmp_path / 'counter.html')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_html)
        assert os.path.exists(out_html)
        with open(out_html) as f:
            content = f.read()
        assert 'elk' in content.lower() or 'svg' in content.lower()

    def test_svg_output(self, tmp_path):
        """-o path.svg 应生成 SVG"""
        out_svg = str(tmp_path / 'counter.svg')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_svg)
        assert os.path.exists(out_svg)
        with open(out_svg) as f:
            content = f.read()
        assert content.startswith('<svg')
        assert 'dataflow' in content

    def test_png_output(self, tmp_path):
        """-o path.png 应生成 PNG (需 rsvg-convert, CI 环境可能缺失)"""
        out_png = str(tmp_path / 'counter.png')
        out, stderr, rc = _run_elk_cli(str(COUNTER_SV), '-o', out_png, expect_returncode=None)
        if os.path.exists(out_png):
            with open(out_png, 'rb') as f:
                assert f.read(8) == b'\x89PNG\r\n\x1a\n'

    def test_metadata_in_stdout(self, tmp_path):
        """stdout 应报告 children/edges/filtered_edges 元数据"""
        out_svg = str(tmp_path / 'counter.svg')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_svg)
        assert 'children: 10' in out  # counter.sv (clk orphan removed)
        assert 'edges: 11' in out
        assert 'filtered_edges: 4' in out
        assert 'orphan_nodes_removed: 1' in out

    def test_no_filter_clock_reset(self, tmp_path):
        """--no-filter-clock-reset 应关闭过滤"""
        out_svg = str(tmp_path / 'counter.svg')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_svg, '--no-filter-clock-reset')
        assert 'filter_clock_reset: False' in out


class TestElkCliOtherViews:
    """Stage 3 - controlflow/modules 视图"""

    def test_controlflow_view(self, tmp_path):
        """--view controlflow 应可用 (filter_clock_reset 自动关)"""
        out_svg = str(tmp_path / 'counter_cf.svg')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_svg, '--view', 'controlflow')
        assert 'view: controlflow' in out
        assert 'filter_clock_reset: False' in out
        assert os.path.exists(out_svg)

    def test_modules_view(self, tmp_path):
        """--view modules 应可用"""
        out_svg = str(tmp_path / 'counter_mod.svg')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_svg, '--view', 'modules')
        assert 'view: modules' in out
        assert os.path.exists(out_svg)

    def test_direction_down(self, tmp_path):
        """--direction DOWN 应工作"""
        out_svg = str(tmp_path / 'counter_down.svg')
        out, _, _ = _run_elk_cli(str(COUNTER_SV), '-o', out_svg, '--direction', 'DOWN')
        assert 'direction: DOWN' in out
        assert os.path.exists(out_svg)


class TestElkCliErrorHandling:
    """Stage 3 - 错误处理"""

    def test_missing_file(self):
        """不存在的文件应报错"""
        _, stderr, rc = _run_elk_cli('/nonexistent/file.sv', expect_returncode=None)
        assert rc != 0

    def test_invalid_view(self):
        """--view invalid 应被 argparse 拒绝"""
        _, _, rc = _run_elk_cli(str(COUNTER_SV), '--view', 'invalid', expect_returncode=None)
        assert rc != 0


@pytest.mark.skipif(
    not os.path.exists(os.path.join(NAVISV_ROOT, 'navisv', 'data', 'elk.bundled.js')),
    reason='ELK bundled not present (skipped)'
)
class TestElkCliE2E:
    """Stage 3 - end-to-end smoke test"""

    def test_full_pipeline_svg(self, tmp_path):
        """完整流程: SV → DesignDriver → GraphBuilder → ELK → SVG"""
        out_svg = str(tmp_path / 'e2e.svg')
        _run_elk_cli(str(COUNTER_SV), '-o', out_svg)
        assert os.path.exists(out_svg)
        assert os.path.getsize(out_svg) > 1000  # 至少 1KB