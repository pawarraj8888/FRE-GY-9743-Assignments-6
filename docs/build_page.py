"""Generate docs/index.html: the Assignment 6 project page (curves, swap and basis-swap cashflows, Part I summary).

Run from the repository root with the QuantLib interpreter:  python docs/build_page.py
"""
import html, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests")); os.chdir(ROOT)
from test_swap_valuation_engines import (ANNUAL, BASIS_SPREAD, FIXED_RATE, FF_IFR, NOTIONAL, QUARTERLY, SOFR_IFR,  # noqa: E402
                                         SPREAD_IFR, VALUE_DATE, act360, build, compounded_rate, df_ff, df_funding,
                                         df_sofr, engine_for, make_basis_swap, make_swap, overnight_leg_pv, parameters, years)
from fixedincomelib import qfCreateProductFRA, qfCreateValueReport  # noqa: E402

model = build()
swap_engine, basis_engine = engine_for(make_swap(), model), engine_for(make_basis_swap(), model)
fra_pv = qfCreateValueReport(model, qfCreateProductFRA("2026-04-02", "2026-07-02", "SOFR-1B", FIXED_RATE, "receive", NOTIONAL,
                                                       accrual_basis="ACT/360"), parameters(), "PV")[0][1]
swap_rows = swap_engine.create_cash_flows_report().content
basis_rows = basis_engine.create_cash_flows_report().content
annuity_fixed = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in ANNUAL)
annuity_quarterly = sum(NOTIONAL * act360(s, e) * df_funding(p) for s, e, p in QUARTERLY)
par_rate = overnight_leg_pv(ANNUAL, df_sofr) / annuity_fixed
fair_spread = (overnight_leg_pv(QUARTERLY, df_ff) - overnight_leg_pv(QUARTERLY, df_sofr)) / annuity_quarterly

# ---- SVG: the three step functions over 0..2.2 years, with the quarterly coupon periods of the basis swap marked
W, L, R = 760, 60, 20
x_max = 2.2
def x(t): return L + (W - L - R) * t / x_max
def panel(top, height, nodes, y_lo, y_hi, steps, fmt, colour, title):
    def y(v): return top + height * (1 - (v - y_lo) / (y_hi - y_lo))
    parts = [f'<rect x="{L}" y="{top}" width="{W-L-R}" height="{height}" fill="none" stroke="#d8d8d8"/>']
    for s, e, _ in QUARTERLY:
        parts.append(f'<rect x="{x(years(s)):.1f}" y="{top}" width="{x(years(e))-x(years(s)):.1f}" height="{height}" fill="#f3f3f3"/>')
    lower = 0.0
    for i, (node, v) in enumerate(nodes):
        upper = x_max if i == len(nodes) - 1 else years(node)
        parts.append(f'<line x1="{x(lower):.1f}" y1="{y(v):.1f}" x2="{x(upper):.1f}" y2="{y(v):.1f}" stroke="{colour}" stroke-width="2"/>')
        if i < len(nodes) - 1:
            parts.append(f'<line x1="{x(upper):.1f}" y1="{y(v):.1f}" x2="{x(upper):.1f}" y2="{y(nodes[i+1][1]):.1f}" stroke="{colour}" stroke-width="1" stroke-dasharray="2 2"/>')
        lower = upper
    for s, e, p in QUARTERLY:
        parts.append(f'<line x1="{x(years(e)):.1f}" y1="{top}" x2="{x(years(e)):.1f}" y2="{top+height}" stroke="#b00" stroke-width="1" stroke-dasharray="4 3"/>')
    ticks = [y_lo + k * (y_hi - y_lo) / steps for k in range(steps + 1)]
    parts += [f'<text x="{L-6}" y="{y(v)+4:.1f}" font-size="11" text-anchor="end" fill="#555">{fmt(v)}</text>' for v in ticks]
    parts.append(f'<text x="{L+8}" y="{top+14}" font-size="12" fill="{colour}">{title}</text>')
    return "".join(parts)
svg = f"""<svg viewBox="0 0 {W} 420" width="100%" role="img" aria-label="SOFR and Fed Funds forward rates and the funding spread, with the quarterly coupon periods of the basis swap shaded">
{panel(14, 120, SOFR_IFR, 0.0, 0.06, 3, lambda v: f"{v*100:.0f}%", "#1f4e79", "SOFR-1B instantaneous forward rate")}
{panel(150, 120, FF_IFR, 0.0, 0.06, 3, lambda v: f"{v*100:.0f}%", "#2e7d32", "FF-1B instantaneous forward rate")}
{panel(286, 80, SPREAD_IFR, 0.0, 0.002, 2, lambda v: f"{v*1e4:.0f} bp", "#8a4b00", "SOFR-1B-FLAT spread over SOFR (funding)")}
{''.join(f'<line x1="{x(t):.1f}" y1="378" x2="{x(t):.1f}" y2="384" stroke="#888"/><text x="{x(t):.1f}" y="398" font-size="11" text-anchor="middle" fill="#555">{t:g}Y</text>' for t in (0, 0.5, 1, 1.5, 2))}
<text x="{x(years('2026-04-02')):.1f}" y="413" font-size="11" text-anchor="middle" fill="#b00">effective 2026-04-02</text>
<text x="{x(years('2027-04-02')):.1f}" y="413" font-size="11" text-anchor="middle" fill="#b00">termination 2027-04-02</text>
</svg>"""

def table(headers, rows):
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

def money(v): return f"{v:,.2f}"
cf_headers = ["Leg", "Accrual start", "Accrual end", "Payment", "Notional", "Accrual", "Rate", "Spread", "Cashflow", "Funding DF", "PV"]
def cf_row(r): return [r["Leg"], r["Accrual Start"], r["Accrual End"], r["Payment Date"], f"{r['Notional']:,.0f}", f"{r['Accrual']:.6f}",
                       f"{r['Rate']:.6f}", f"{r['Spread']:.4f}", money(r["Cashflow"]), f"{r['Discount Factor']:.6f}", money(r["PV"])]
hand_headers = ["Coupon", "alpha (ACT/360)", "SOFR compounded", "Fed Funds compounded", "Funding DF at payment", "Leg 1 PV (hand)", "Leg 2 PV (hand)"]
hand_rows = [[f"{s} to {e}", f"{act360(s, e):.6f}", f"{compounded_rate(df_sofr, s, e):.6f}", f"{compounded_rate(df_ff, s, e):.6f}", f"{df_funding(p):.6f}",
              money(NOTIONAL * act360(s, e) * (compounded_rate(df_sofr, s, e) + BASIS_SPREAD) * df_funding(p)),
              money(NOTIONAL * act360(s, e) * compounded_rate(df_ff, s, e) * df_funding(p))] for s, e, p in QUARTERLY]
summary = [["FRA 3x6, receive 4% (supplied example)", "", money(fra_pv), ""],
           ["RFR swap, receive 4% vs compounded SOFR, 1Y/1Y", f"fixed {money(swap_engine.fixed_leg_engine_.value)}, floating {money(swap_engine.floating_leg_engine_.value)}",
            money(swap_engine.value), f"par rate {par_rate*100:.4f}%"],
           ["Basis swap, receive SOFR + 10 bp vs Fed Funds, 3M/3M",
            f"leg 1 {money(sum(r['PV'] for r in basis_rows[:8]))}, leg 2 {money(-sum(r['PV'] for r in basis_rows[8:]))}",
            money(basis_engine.value), f"fair spread {fair_spread*1e4:.2f} bp"]]

page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>FRE-GY 9743 Assignment 6: Interest-Rate Products and a GBP-Collateralised FX Forward</title>
<style>
body{{font-family:Georgia,'Times New Roman',serif;max-width:900px;margin:32px auto;padding:0 16px;color:#222;line-height:1.45;background:#fff}}
h1{{font-size:1.6em;margin-bottom:0}} h2{{font-size:1.2em;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:3px}}
.meta{{color:#555;margin-top:4px}} code{{font-family:Menlo,Consolas,monospace;font-size:0.92em;background:#f4f4f4;padding:1px 4px;border-radius:3px}}
table{{border-collapse:collapse;font-size:0.85em;margin:10px 0;width:100%;overflow-x:auto;display:block}} th,td{{border:1px solid #ddd;padding:4px 6px;text-align:right;white-space:nowrap}}
th{{background:#f7f7f7}} td:first-child,th:first-child{{text-align:left}} .formula{{background:#f8f8ff;border-left:3px solid #1f4e79;padding:8px 12px;margin:8px 0;font-size:0.95em}}
.note{{color:#444;font-size:0.95em}} sup,sub{{line-height:0}}
</style></head><body>
<h1>Assignment 6: Interest-Rate Products and a GBP-Collateralised FX Forward</h1>
<p class="meta">Raj Pawar, FRE-GY 9743 (Spec Topics in Risk Management), NYU Tandon, October 2026.
Branch <a href="https://github.com/pawarraj8888/FRE-GY-9743-Assignments-6/tree/Raj_Pawar_Branch"><code>Raj_Pawar_Branch</code></a>,
write-up <a href="https://github.com/pawarraj8888/FRE-GY-9743-Assignments-6/blob/Raj_Pawar_Branch/writeup/Assignment6_Writeup_RajPawar.pdf">PDF</a>.</p>

<h2>Part I in one paragraph</h2>
<p>An EUR/USD forward (receive <i>N</i> EUR, pay <i>NK</i> USD at <i>T</i>) collateralised in GBP is discounted with the GBP-collateralised curves.
Redoing the collateral replication argument with the collateral in another currency gives the rule: a payoff in currency <i>i</i> collateralised in currency <i>k</i>
is discounted at <i>c<sub>i</sub></i> + <i>y<sub>i</sub></i> &minus; <i>y<sub>k</sub></i>, where <i>c</i> is the OIS rate and <i>y</i> the gap between the cash rate and the collateral rate. Writing
<i>P</i><sup>(k)</sup><sub>i</sub>(t,T) for that discount factor:</p>
<div class="formula">V<sub>t</sub> = N [ X<sub>t</sub> P<sup>(GBP)</sup><sub>EUR</sub>(t,T) &minus; K P<sup>(GBP)</sup><sub>USD</sub>(t,T) ],
&nbsp;&nbsp; K* = X<sub>t</sub> P<sup>(GBP)</sup><sub>EUR</sub>(t,T) / P<sup>(GBP)</sup><sub>USD</sub>(t,T).</div>
<p>With deterministic collateral spreads the switch factors chain through USD, so the five given curves are enough:
P<sup>(GBP)</sup><sub>USD</sub> = df<sub>SOFR</sub> &middot; df<sub>SONIA</sub> / df<sub>[GBP,USD]</sub> and
P<sup>(GBP)</sup><sub>EUR</sub> = df<sub>[EUR,USD]</sub> &middot; df<sub>SONIA</sub> / df<sub>[GBP,USD]</sub>. The fair strike collapses to the USD-CSA forward
X<sub>t</sub> df<sub>[EUR,USD]</sub>/df<sub>SOFR</sub>; GBP enters only through the factor df<sub>SONIA</sub>/df<sub>[GBP,USD]</sub> that rescales the mark-to-market. The write-up has the derivation and the caveats.</p>

<h2>Part II: the curves and the trades</h2>
<p class="note">Value date {VALUE_DATE}. SOFR and Fed Funds have their own projection curves; the funding curve is SOFR plus an IFR spread. The shaded bands are the four
quarterly coupon periods of the basis swap; the dashed red lines are the accrual ends (2027-01-02 is a Saturday, so that coupon ends on Monday 2027-01-04).</p>
{svg}

<h2>RFR swap: receive 4% fixed, pay compounded SOFR, both legs annual</h2>
{table(cf_headers, [cf_row(r) for r in swap_rows])}
<p class="note">The compounded rate is (D(T<sub>s</sub>)/D(T<sub>e</sub>) &minus; 1)/&alpha; on the SOFR curve: the daily factors telescope because every observation period lies inside the coupon.
Swap PV {money(swap_engine.value)} USD; the par fixed rate is {par_rate*100:.4f}%.</p>

<h2>Overnight index basis swap: receive SOFR + 10 bp, pay Fed Funds, quarterly</h2>
{table(cf_headers, [cf_row(r) for r in basis_rows])}
<p class="note">Leg 1 is valued as its index-only stream plus its spread-only stream on the same schedule. Basis swap PV {money(basis_engine.value)} USD; the fair spread over SOFR is {fair_spread*1e4:.2f} bp
(negative: Fed Funds projects below SOFR on these synthetic curves).</p>

<h2>Hand check of the quarterly coupons (no library)</h2>
{table(hand_headers, hand_rows)}

<h2>Summary</h2>
{table(["Product", "Leg values (USD)", "PV (USD)", "Fair level"], summary)}
<p class="note">Everything on this page is generated from the library by <code>docs/build_page.py</code>; the tests in <code>tests/</code> check the same numbers against the hand calculation.</p>
</body></html>
"""
(ROOT / "docs" / "index.html").write_text(page)
print("wrote docs/index.html", len(page), "bytes")
