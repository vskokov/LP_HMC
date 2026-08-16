#!/usr/bin/env python3
"""Build the standalone HTML companion for artifact.json using only stdlib."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def fmt(value):
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def table(title, rows):
    columns = list(rows[0])
    head = "".join(f"<th>{html.escape(column.replace('_', ' '))}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(fmt(row[column]))}</td>" for column in columns) + "</tr>"
        for row in rows
    )
    return f"<section><h2>{html.escape(title)}</h2><div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>"


def main():
    artifact = json.loads((ROOT / "artifact.json").read_text())
    data = artifact["snapshot"]["datasets"]
    issues = artifact["snapshot"]["accessIssues"]
    issue_items = "".join(f"<li>{html.escape(item['message'])}</li>" for item in issues)
    source_items = "".join(
        f"<li><a href='{html.escape(source['path'])}'>{html.escape(source['label'])}</a></li>"
        for source in artifact["manifest"]["sources"]
    )
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(artifact['manifest']['title'])}</title>
<style>
:root{{--ink:#18202a;--muted:#56606d;--line:#d9dee5;--panel:#f7f9fb;--accent:#145da0;--warn:#8a5200}}*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:var(--ink);font:15px/1.55 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:38px 28px 70px}}h1{{font-size:30px;line-height:1.2;margin:0 0 8px}}h2{{font-size:19px;margin:0 0 12px}}p{{max-width:860px}}.lede{{font-size:18px;color:var(--muted);margin:0 0 30px}}.verdict{{border-left:5px solid var(--warn);background:#fff7e8;padding:18px 20px;margin:24px 0}}section{{border-top:1px solid var(--line);padding-top:24px;margin-top:30px}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}th,td{{padding:9px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}th{{background:var(--panel);font-size:12px;text-transform:uppercase;color:var(--muted)}}code{{background:var(--panel);padding:2px 5px;border-radius:4px}}a{{color:var(--accent)}}.small{{font-size:13px;color:var(--muted)}}
</style></head><body><main>
<h1>{html.escape(artifact['manifest']['title'])}</h1>
<p class="lede">{html.escape(artifact['manifest']['description'])}</p>
<div class="verdict"><strong>Verdict:</strong> the swap mathematics, CUDA implementation, and walker bookkeeping pass the available checks. The run is nevertheless not equilibrated. Its high adjacent acceptance is dominated by correlated motion and rapid recrossing, so it is a poor proxy for end-to-end transport.</div>
<section><h2>Answer to the code-correctness question</h2><p>No concrete implementation defect was found. In a 2,000-sweep A6000 continuation, 78,760 accepted swaps produced exactly 157,520 one-edge label moves, proving that device fields and walker IDs move together. The exact crossed action agrees with direct energies to 2.10×10<sup>−13</sup>, and both CPU and GPU test suites pass.</p><p>The bad result comes from dynamics: at lag 1,000 the observed walker MSD is 22.7 windows², versus 731.1 for independent swaps with the same edge acceptance rates. Thus nominal acceptance overstates effective diffusion by roughly 32× in this comparison.</p></section>
{table('Transferred checkpoint summary', data['checkpoint_summary'])}
{table('Implementation and accounting checks', data['validation_checks'])}
{table('Measured versus independent-swap null', data['null_comparison'])}
<section><h2>Parameter diagnosis</h2><p>Changing only <code>swap_every</code> from 1 to 2 or 5 reduced MSD per HMC work, so less-frequent exchange is not the remedy. Longer single HMC trajectories allow a configuration to relax farther after entering a neighboring umbrella and reduce reversals. The short probes favor <code>n_lf=16</code>–<code>24</code> over the production value 4. The <code>n_lf=24</code> probe retained 77.4% HMC acceptance and increased lag-1,000 MSD to 202.9 windows².</p></section>
{table('HMC trajectory-length probes (same r0 checkpoint)', data['trajectory_probe'])}
{table('Swap-cadence probes at n_lf=4', data['swap_cadence_probe'])}
<section><h2>Recommended next decision</h2><ol><li>Do not collect statistics from either checkpoint and do not simply extend the current <code>n_lf=4</code> workflow.</li><li>Run matched discarded-thermalization pilots from both r0 and r1 with <code>n_lf=16</code> and <code>n_lf=24</code>, keeping the current ε initially. Record walker MSD at several lags, direction continuation, endpoint hits, HMC acceptance, and wall time.</li><li>Select on effective transport per wall-clock second—not adjacent acceptance. The present short probes put 16 and 24 close per leapfrog step; 24 has the more directly useful 77.4% acceptance.</li><li>Only after that comparison, consider reducing 161 windows further. The current minimum edge acceptance near 39% leaves some room, but fewer windows cannot cure the underlying recrossing by itself.</li><li>Retain the round-trip gate and require agreement between independent ordered/disordered reconstructions before production. Do not weaken the gate to make these files pass.</li></ol></section>
<section><h2>Limitations</h2><ul>{issue_items}</ul><p class="small">The independent-swap null preserves each edge's measured cumulative acceptance but deliberately removes temporal/configuration correlation. It is a diagnostic baseline, not a physical sampler.</p></section>
<section><h2>Sources</h2><ul>{source_items}</ul><p class="small">Canonical data: <a href="artifact.json">artifact.json</a>. Rebuild with <code>python3 build_report.py</code>.</p></section>
</main></body></html>"""
    (ROOT / "report.html").write_text(content)


if __name__ == "__main__":
    main()
