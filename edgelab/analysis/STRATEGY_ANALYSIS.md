# EdgeLab Strategy Deep-Dive Analysis (S1 Turtle + S3 Session)
Data: EURUSD H1 5.4y. OOS = last 20%. PF = gross win pips / gross loss pips.

=== Strategy 3 (Session Volatility Expansion) DEEP ANALYSIS ===
Total trades: 943 (IS=748, OOS=195)

Session breakdown:
  LONDON: N=562 PF=0.80 win=48.6% avg_pips=-2.05
  NY: N=381 PF=0.78 win=42.8% avg_pips=-1.61
  OTHER: N=0
  OOS only:
    LONDON: N=112 PF=0.82 win=49.1%
    NY: N=83 PF=1.15 win=50.6%

Time-of-day (30-min buckets, NY time):
  L04: N=307 PF=0.95 win=49.8%
  N04: N=218 PF=0.74 win=39.4%
  X: N=418 PF=0.70 win=47.1%

Day-of-week breakdown:
  Monday: N=183 PF=0.91 win=47.0%
  Tuesday: N=201 PF=0.93 win=42.8%
  Wednesday: N=202 PF=0.96 win=52.0%
  Thursday: N=182 PF=0.78 win=46.7%
  Friday: N=175 PF=0.50 win=42.3%

Prior-4h / trend filter:
  BEAR: N=485 PF=0.72 win=45.6%
  BULL: N=458 PF=0.88 win=46.9%

Asymmetry: Avg win=15.74 pips Avg loss=17.02 pips Win/loss ratio=0.93
  OOS avg win=17.09 avg loss=18.12

Holding time: Avg winner=12.9 bars Avg loser=13.9 bars

PnL distribution (pips):
  min=-122.2 p25=-12.5 median=-1.9 p75=11.5 max=108.6 std=22.6
  % winners=46.2  biggest win=108.6 biggest loss=-122.2

Filtered equity (OOS cumulative pips):
  London only: N=112 OOS net pips=-213.3 PF=0.82
  NY only: N=83 OOS net pips=94.8 PF=1.15
  ATR>=median: N=98 OOS net pips=-1.9 PF=1.00
  prior4h=BULL only: N=93 OOS net pips=-137.2 PF=0.86

--- BEST SUBSET SEARCH ---

  Subset search (OOS, min 50 trades): 7 qualifying subsets
    NONE passed PF>1.2 on 50+ OOS trades.
    best  session=NY: N=83 win=50.6% PF=1.15 maxDD=196.8p
    best  session=LONDON & prior4h=BEAR: N=54 win=51.9% PF=1.10 maxDD=130.4p
    best  prior4h=BEAR: N=102 win=52.0% PF=1.02 maxDD=201.5p
    best  dow=Wednesday: N=51 win=56.9% PF=0.99 maxDD=125.0p
    best  prior4h=BULL: N=93 win=47.3% PF=0.86 maxDD=220.9p
    best  session=LONDON: N=112 win=49.1% PF=0.82 maxDD=340.4p

=== Strategy 1 (Modernized Turtle) DEEP ANALYSIS ===
Total trades: 258 (IS=202, OOS=56)

Day-of-week breakdown:
  Monday: N=43 PF=0.65 win=34.9%
  Tuesday: N=43 PF=0.71 win=34.9%
  Wednesday: N=69 PF=0.56 win=33.3%
  Thursday: N=55 PF=0.86 win=34.5%
  Friday: N=33 PF=0.79 win=45.5%

Prior-4h / trend filter:
  nan: N=0 PF=nan win=nan%

Asymmetry: Avg win=54.02 pips Avg loss=43.92 pips Win/loss ratio=1.23
  OOS avg win=55.92 avg loss=41.52

Holding time: Avg winner=99.6 bars Avg loser=43.2 bars

PnL distribution (pips):
  min=-139.9 p25=-46.5 median=-22.8 p75=15.8 max=299.8 std=60.6
  % winners=34.5  biggest win=299.8 biggest loss=-139.9

Filtered equity (OOS cumulative pips):
  London only: N=0 OOS net pips=0.0 PF=nan
  NY only: N=0 OOS net pips=0.0 PF=nan
  ATR>=median: N=27 OOS net pips=-115.6 PF=0.85
  prior4h=BULL only: N=0 OOS net pips=0.0 PF=nan

--- BEST SUBSET SEARCH ---

  Subset search (OOS, min 50 trades): 0 qualifying subsets
    NONE passed PF>1.2 on 50+ OOS trades.

=== CROSS-STRATEGY OVERLAP ===
Strategy1 trades: 258  Strategy3 trades: 943  Overlapping (bar+dir): 23
  S3 overlapping win%=34.8 (N=23)  non-overlap win%=46.5 (N=920)
  Overlap PF=0.77  non-overlap PF=0.80

=== RECOMMENDATION ===
See narrative report in chat. Analysis-only; no source modified.