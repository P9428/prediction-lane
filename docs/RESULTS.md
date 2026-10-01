# prediction-lane results — walk-forward, generated 2026-10-01T20:46:17+00:00

Primary test per league: cluster-robust Wald z on the model coefficient in `logit(y) = a + b·logit(p_close) + c·logit(p_model)` on the test seasons. Bonferroni over 4 leagues: p < 0.0125 to pass. The market is Shin-devigged ESPN BET / DraftKings close.

| league | tune | test seasons | n | c_model | z (cluster) | p | LR p | blend w | VERDICT |
|---|---|---|---|---|---|---|---|---|---|
| mlb | 2024 | [2025, 2026] | 4916 | 0.086 | 0.49 | 0.6219 | 0.6215 | 0.092 | **REDUNDANT** |
| nhl | 2024 | [2025, 2026] | 2799 | -0.449 | -2.08 | 0.0376 | 0.0283 | -0.550 | **REDUNDANT** |
| nba | 2024 | [2025, 2026] | 2633 | -0.095 | -0.84 | 0.4017 | 0.3851 | -0.100 | **REDUNDANT** |
| nfl | 2022 | [2023, 2024, 2025, 2026] | 722 | -0.133 | -0.69 | 0.4904 | 0.5274 | -0.137 | **REDUNDANT** |

## MLB

- hyper-parameters frozen on 2024: `{"elo": {"k": 4.0, "hfa": 12.0, "carry": 0.67, "ll_tune": 0.6838}, "poisson": {"eta": 0.01, "hfa": 0.05, "carry": 0.7, "mu0": 1.4793, "ll_tune": 0.7048}}`
- market (close, Shin) Cox calibration: a=0.026 (z 0.87), b=0.906 (z vs 1: -1.14); Hosmer-Lemeshow p=0.1402; median overround 0.0453
- skill exists to forecast? team-season win counts vs binomial: beta-binomial rho=0.014 (LR p=1.0000); split-half persistence of team win%: spearman=0.397 (p=0.0001)
- margin residual (vs Gaussian model): sd=4.52, skew=-0.02, excess kurt=1.08, JB p=0.0000, AD stat=7.36 (5% crit 0.79), Student-t df=8.5, AIC t-normal=-119.0
- score dispersion: home var/mean=2.21 (CT z=59.8, NB size=3.7); away var/mean=2.46 (CT z=72.2)

| model | log-loss | market log-loss | Δ (mkt−model) | 95% CI | Brier Δ | Cox b | Cox a |
|---|---|---|---|---|---|---|---|
| p_elo | 0.6823 | 0.6776 | -0.0047 | [-0.0078, -0.0019] | -0.0023 | 0.907 | 0.085 |
| p_gauss | 0.6835 | 0.6776 | -0.0059 | [-0.0096, -0.0024] | -0.0028 | 0.830 | 0.131 |
| p_pois | 0.7075 | 0.6776 | -0.0299 | [-0.0374, -0.0221] | -0.0129 | 0.328 | 0.108 |
| p_pois_pitch | 0.7225 | 0.6776 | -0.0450 | [-0.0539, -0.0352] | -0.0176 | 0.294 | 0.113 |
| p_model | 0.6811 | 0.6776 | -0.0035 | [-0.0063, -0.0008] | -0.0017 | 0.942 | 0.011 |

- vs OPENING line: c_model=0.427, z=2.82, p=0.0048, blend w=0.426 (n=4916)
- sanity, market over model: c_market=0.849, z=5.91 (must be large and positive)

| bet set | games | bets | staked $ | pnl $ | ROI | ROI 95% CI | P(ROI≤0) | hit | avg dec | max DD $ | losing months | payoff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bets_close | 4916 | 43 | 192 | -21 | -0.1107 | [-0.4932, 0.3102] | 0.717 | 0.302 | 2.950 | -44 | 3/3 | 1.92 |
| bets_model_only_close | 4916 | 2625 | 38707 | -826 | -0.0213 | [-0.0676, 0.0221] | 0.815 | 0.447 | 2.263 | -1586 | 12/17 | 1.19 |
| bets_open | 4916 | 507 | 4592 | 397 | 0.0864 | [-0.0199, 0.1980] | 0.060 | 0.503 | 2.231 | -225 | 6/15 | 1.17 |

| season | n | c_model | z | p | Δ log-loss | ROI | ROI CI | bets |
|---|---|---|---|---|---|---|---|---|
| 2025 | 2478 | 0.273 | 1.19 | 0.2345 | -0.0019 | — | — | 0 |
| 2026 | 2438 | -0.174 | -0.65 | 0.5185 | -0.0052 | -0.1107 | [-0.4787, 0.3096] | 43 |

market calibration (close, Shin), test seasons:

| bin | n | mean p | realized | exact 95% CI | binom p |
|---|---|---|---|---|---|
| (0.2, 0.3] | 26 | 0.278 | 0.269 | [0.116, 0.478] | 1.000 |
| (0.3, 0.4] | 309 | 0.367 | 0.379 | [0.324, 0.435] | 0.680 |
| (0.4, 0.5] | 1436 | 0.459 | 0.484 | [0.458, 0.510] | 0.064 |
| (0.5, 0.6] | 2093 | 0.550 | 0.548 | [0.526, 0.569] | 0.843 |
| (0.6, 0.7] | 894 | 0.638 | 0.615 | [0.582, 0.647] | 0.164 |
| (0.7, 0.8] | 158 | 0.730 | 0.753 | [0.678, 0.818] | 0.532 |

## NHL

- hyper-parameters frozen on 2024: `{"elo": {"k": 12.0, "hfa": 33.0, "carry": 0.7, "ll_tune": 0.671}, "poisson": {"eta": 0.01, "hfa": 0.1, "carry": 0.7, "mu0": 1.1317, "ll_tune": 0.672}}`
- market (close, Shin) Cox calibration: a=0.024 (z 0.59), b=0.938 (z vs 1: -0.70); Hosmer-Lemeshow p=0.5692; median overround 0.0414
- skill exists to forecast? team-season win counts vs binomial: beta-binomial rho=0.025 (LR p=1.0000); split-half persistence of team win%: spearman=0.670 (p=0.0000)
- margin residual (vs Gaussian model): sd=2.56, skew=-0.07, excess kurt=-0.54, JB p=0.0000, AD stat=9.11 (5% crit 0.79), Student-t df=176410811807.0, AIC t-normal=2.0
- score dispersion: home var/mean=0.98 (CT z=-0.9, NB size=2980.9); away var/mean=0.97 (CT z=-1.0)

| model | log-loss | market log-loss | Δ (mkt−model) | 95% CI | Brier Δ | Cox b | Cox a |
|---|---|---|---|---|---|---|---|
| p_elo | 0.6800 | 0.6688 | -0.0112 | [-0.0159, -0.0071] | -0.0053 | 0.726 | 0.031 |
| p_gauss | 0.6793 | 0.6688 | -0.0106 | [-0.0150, -0.0066] | -0.0050 | 0.750 | 0.059 |
| p_pois | 0.6810 | 0.6688 | -0.0122 | [-0.0173, -0.0077] | -0.0058 | 0.704 | 0.030 |
| p_model | 0.6779 | 0.6688 | -0.0092 | [-0.0134, -0.0050] | -0.0043 | 0.845 | 0.023 |

- vs OPENING line: c_model=-0.310, z=-1.31, p=0.1906, blend w=-0.356 (n=2799)
- sanity, market over model: c_market=1.264, z=7.08 (must be large and positive)

| bet set | games | bets | staked $ | pnl $ | ROI | ROI 95% CI | P(ROI≤0) | hit | avg dec | max DD $ | losing months | payoff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bets_close | 2799 | 281 | 2833 | 100 | 0.0353 | [-0.0770, 0.1668] | 0.286 | 0.523 | 2.048 | -193 | 7/16 | 0.99 |
| bets_model_only_close | 2799 | 1586 | 23456 | -1939 | -0.0827 | [-0.1454, -0.0263] | 0.999 | 0.424 | 2.343 | -2433 | 12/18 | 1.16 |
| bets_open | 2799 | 51 | 472 | -17 | -0.0367 | [-0.2920, 0.2385] | 0.590 | 0.510 | 1.990 | -94 | 7/11 | 0.88 |

| season | n | c_model | z | p | Δ log-loss | ROI | ROI CI | bets |
|---|---|---|---|---|---|---|---|---|
| 2025 | 1405 | -0.444 | -1.58 | 0.1139 | -0.0116 | 0.0662 | [-0.1027, 0.2547] | 94 |
| 2026 | 1394 | -0.442 | -1.29 | 0.1961 | -0.0068 | 0.0229 | [-0.1280, 0.1787] | 187 |

market calibration (close, Shin), test seasons:

| bin | n | mean p | realized | exact 95% CI | binom p |
|---|---|---|---|---|---|
| (0.1, 0.2] | 1 | 0.190 | 0.000 | [0.000, 0.975] | 1.000 |
| (0.2, 0.3] | 35 | 0.271 | 0.257 | [0.125, 0.433] | 1.000 |
| (0.3, 0.4] | 265 | 0.364 | 0.400 | [0.341, 0.462] | 0.226 |
| (0.4, 0.5] | 763 | 0.454 | 0.468 | [0.432, 0.504] | 0.467 |
| (0.5, 0.6] | 911 | 0.554 | 0.536 | [0.503, 0.568] | 0.271 |
| (0.6, 0.7] | 630 | 0.639 | 0.641 | [0.602, 0.679] | 0.934 |
| (0.7, 0.8] | 188 | 0.736 | 0.777 | [0.710, 0.834] | 0.216 |
| (0.8, 0.9] | 6 | 0.813 | 0.667 | [0.223, 0.957] | 0.312 |

## NBA

- hyper-parameters frozen on 2024: `{"elo": {"k": 10.0, "hfa": 35.0, "carry": 0.75, "ll_tune": 0.6202}}`
- market (close, Shin) Cox calibration: a=-0.020 (z -0.46), b=0.976 (z vs 1: -0.49); Hosmer-Lemeshow p=0.1592; median overround 0.0426
- skill exists to forecast? team-season win counts vs binomial: beta-binomial rho=0.092 (LR p=1.0000); split-half persistence of team win%: spearman=0.742 (p=0.0000)
- margin residual (vs Gaussian model): sd=14.54, skew=-0.09, excess kurt=0.38, JB p=0.0001, AD stat=1.62 (5% crit 0.79), Student-t df=16.8, AIC t-normal=-11.5
- score dispersion: home var/mean=1.47 (CT z=17.0, NB size=241.2); away var/mean=1.52 (CT z=18.8)

| model | log-loss | market log-loss | Δ (mkt−model) | 95% CI | Brier Δ | Cox b | Cox a |
|---|---|---|---|---|---|---|---|
| p_elo | 0.6071 | 0.5800 | -0.0271 | [-0.0359, -0.0181] | -0.0110 | 0.996 | 0.033 |
| p_gauss | 0.6111 | 0.5800 | -0.0311 | [-0.0400, -0.0213] | -0.0125 | 1.114 | -0.014 |
| p_model | 0.6076 | 0.5800 | -0.0276 | [-0.0360, -0.0187] | -0.0111 | 1.024 | 0.030 |

- vs OPENING line: c_model=0.107, z=0.89, p=0.3740, blend w=0.110 (n=2633)
- sanity, market over model: c_market=1.043, z=11.03 (must be large and positive)

| bet set | games | bets | staked $ | pnl $ | ROI | ROI 95% CI | P(ROI≤0) | hit | avg dec | max DD $ | losing months | payoff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bets_close | 2633 | 87 | 461 | 2 | 0.0041 | [-0.2682, 0.2496] | 0.479 | 0.391 | 2.840 | -75 | 6/12 | 1.57 |
| bets_model_only_close | 2633 | 1913 | 32031 | -3915 | -0.1222 | [-0.1872, -0.0511] | 1.000 | 0.327 | 3.683 | -4372 | 14/18 | 1.67 |
| bets_open | 2633 | 832 | 6447 | 70 | 0.0108 | [-0.1002, 0.1212] | 0.446 | 0.329 | 3.539 | -214 | 8/18 | 2.07 |

| season | n | c_model | z | p | Δ log-loss | ROI | ROI CI | bets |
|---|---|---|---|---|---|---|---|---|
| 2025 | 1317 | -0.076 | -0.52 | 0.6040 | -0.0257 | -0.0777 | [-0.3823, 0.1768] | 54 |
| 2026 | 1316 | -0.115 | -0.66 | 0.5107 | -0.0295 | 0.1506 | [-0.3839, 0.6469] | 33 |

market calibration (close, Shin), test seasons:

| bin | n | mean p | realized | exact 95% CI | binom p |
|---|---|---|---|---|---|
| (0.0, 0.1] | 46 | 0.076 | 0.022 | [0.001, 0.115] | 0.259 |
| (0.1, 0.2] | 141 | 0.153 | 0.106 | [0.061, 0.169] | 0.159 |
| (0.2, 0.3] | 208 | 0.250 | 0.274 | [0.215, 0.340] | 0.424 |
| (0.3, 0.4] | 339 | 0.349 | 0.375 | [0.323, 0.429] | 0.333 |
| (0.4, 0.5] | 344 | 0.451 | 0.451 | [0.397, 0.505] | 1.000 |
| (0.5, 0.6] | 338 | 0.555 | 0.565 | [0.510, 0.619] | 0.743 |
| (0.6, 0.7] | 402 | 0.651 | 0.634 | [0.585, 0.682] | 0.497 |
| (0.7, 0.8] | 389 | 0.750 | 0.740 | [0.694, 0.783] | 0.682 |
| (0.8, 0.9] | 319 | 0.850 | 0.809 | [0.761, 0.850] | 0.041 |
| (0.9, 1.0] | 107 | 0.926 | 0.953 | [0.894, 0.985] | 0.356 |

## NFL

- hyper-parameters frozen on 2022: `{"elo": {"k": 30.0, "hfa": 48.0, "carry": 0.67, "ll_tune": 0.64}}`
- market (close, Shin) Cox calibration: a=-0.033 (z -0.40), b=1.012 (z vs 1: 0.12); Hosmer-Lemeshow p=0.4426; median overround 0.0407
- skill exists to forecast? team-season win counts vs binomial: beta-binomial rho=0.089 (LR p=1.0000); split-half persistence of team win%: spearman=0.314 (p=0.0001)
- margin residual (vs Gaussian model): sd=13.54, skew=0.12, excess kurt=0.10, JB p=0.3499, AD stat=0.95 (5% crit 0.78), Student-t df=49.2, AIC t-normal=1.6
- score dispersion: home var/mean=4.23 (CT z=61.3, NB size=6.0); away var/mean=4.38 (CT z=64.0)

| model | log-loss | market log-loss | Δ (mkt−model) | 95% CI | Brier Δ | Cox b | Cox a |
|---|---|---|---|---|---|---|---|
| p_elo | 0.6371 | 0.6093 | -0.0277 | [-0.0492, -0.0090] | -0.0115 | 0.761 | -0.003 |
| p_gauss | 0.6501 | 0.6093 | -0.0408 | [-0.0608, -0.0213] | -0.0179 | 0.839 | -0.049 |
| p_model | 0.6370 | 0.6093 | -0.0277 | [-0.0464, -0.0113] | -0.0120 | 0.955 | -0.043 |

- vs OPENING line: c_model=-0.089, z=-0.43, p=0.6672, blend w=-0.090 (n=722)
- sanity, market over model: c_market=1.107, z=6.40 (must be large and positive)

| bet set | games | bets | staked $ | pnl $ | ROI | ROI 95% CI | P(ROI≤0) | hit | avg dec | max DD $ | losing months | payoff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bets_close | 722 | 86 | 608 | -124 | -0.2031 | [-0.4820, 0.0717] | 0.928 | 0.291 | 3.051 | -176 | 4/8 | 1.72 |
| bets_model_only_close | 722 | 524 | 8938 | -717 | -0.0802 | [-0.1865, 0.0299] | 0.928 | 0.376 | 3.008 | -973 | 10/16 | 1.44 |
| bets_open | 621 | 167 | 2239 | -481 | -0.2149 | [-0.4255, -0.0225] | 0.990 | 0.341 | 2.640 | -554 | 5/12 | 1.30 |

| season | n | c_model | z | p | Δ log-loss | ROI | ROI CI | bets |
|---|---|---|---|---|---|---|---|---|
| 2023 | 106 | -1.039 | -1.74 | 0.0816 | -0.0351 | 0.2504 | [-0.0818, 0.8728] | 25 |
| 2024 | 284 | 0.113 | 0.35 | 0.7279 | -0.0327 | -0.4042 | [-0.7388, -0.0986] | 60 |
| 2025 | 284 | -0.262 | -0.76 | 0.4479 | -0.0256 | 1.5000 | [0.0000, 1.5000] | 1 |

market calibration (close, Shin), test seasons:

| bin | n | mean p | realized | exact 95% CI | binom p |
|---|---|---|---|---|---|
| (0.0, 0.1] | 2 | 0.080 | 0.000 | [0.000, 0.842] | 1.000 |
| (0.1, 0.2] | 20 | 0.163 | 0.100 | [0.012, 0.317] | 0.760 |
| (0.2, 0.3] | 53 | 0.260 | 0.245 | [0.138, 0.383] | 0.877 |
| (0.3, 0.4] | 100 | 0.353 | 0.320 | [0.230, 0.421] | 0.531 |
| (0.4, 0.5] | 110 | 0.446 | 0.436 | [0.342, 0.534] | 0.849 |
| (0.5, 0.6] | 114 | 0.561 | 0.623 | [0.527, 0.712] | 0.188 |
| (0.6, 0.7] | 138 | 0.646 | 0.638 | [0.552, 0.718] | 0.859 |
| (0.7, 0.8] | 119 | 0.748 | 0.723 | [0.633, 0.801] | 0.527 |
| (0.8, 0.9] | 52 | 0.848 | 0.808 | [0.675, 0.904] | 0.438 |
| (0.9, 1.0] | 14 | 0.916 | 1.000 | [0.768, 1.000] | 0.624 |
