# BTC Robustness and Calibration Experiments

**Date:** 2026-08-31

These are non-production experiments. The current combined model artifact was not replaced.

## 1. Recency-weighted BTC training

The challenger was trained on BTC time steps 1-29 with class-balanced weights multiplied by:

```text
1 + (time_step - 1) / 28
```

The threshold was re-selected on BTC validation steps 30-34. The recency-weighted model locks at `0.88`, not the baseline's `0.90`.

| Candidate threshold | Validation FPR | Validation recall | Eligible under 2% cap |
|---:|---:|---:|---|
| 0.50 | 26.01% | 88.13% | No |
| 0.60 | 21.45% | 83.87% | No |
| 0.70 | 11.16% | 77.49% | No |
| 0.75 | 6.81% | 75.98% | No |
| 0.80 | 4.84% | 72.40% | No |
| 0.85 | 2.89% | 68.09% | No |
| 0.88 | 1.88% | 64.50% | Yes |
| 0.90 | 1.51% | 59.85% | Yes |
| 0.92 | 1.13% | 54.37% | Yes |
| 0.95 | 0.65% | 39.64% | Yes |

| Metric | Current locked baseline | Recency-weighted BTC | Change |
|---|---:|---:|---:|
| Precision | 0.4820 | 0.4222 | -0.0598 |
| Recall | 0.3072 | 0.4303 | +0.1231 |
| F1 | 0.3753 | 0.4262 | +0.0509 |
| AUC-PR | 0.3721 | 0.4023 | +0.0302 |

### Worst historical steps

| Test step | Baseline F1 | Recency-weighted F1 | Change |
|---:|---:|---:|---:|
| 43 | 0.0880 | 0.0894 | +0.0014 |
| 45 | 0.0411 | 0.1029 | +0.0618 |
| 47 | 0.0513 | 0.0631 | +0.0118 |
| 48 | 0.0372 | 0.0098 | -0.0275 |

The re-locked recency model improves the overall BTC result and three of the four identified weak steps, but it does not solve step 48. The step-48 regression is evidence of a structural regime break or fraud pattern absent from the training history, rather than ordinary gradual concept drift. Recency weighting is therefore not a general concept-drift fix.

## 2. Feature ablation

Each challenger was trained from scratch on BTC training steps 1-29. Variants were selected using validation steps 30-34 only at threshold `0.90`; exactly one selected variant was then evaluated on test steps 35-49.

| Removed feature(s) | Precision | Recall | F1 | AUC-PR |
|---|---:|---:|---:|---:|
| Variant | Validation F1 | Validation AUC-PR |
|---|---:|---:|
| Remove `first_sent_block` | 0.6480 | 0.6785 |
| Remove `lifetime_in_blocks` | 0.6934 | 0.7198 |
| Remove `first_block_appeared_in` | 0.6849 | 0.7013 |
| Remove `last_block_appeared_in` | 0.7298 | 0.7499 |
| Remove all four | 0.5272 | 0.6085 |

Validation selected removal of `last_block_appeared_in`. Its one-time held-out test result is precision `0.4055`, recall `0.4427`, F1 `0.4233`, AUC-PR `0.3979`.

This selection is now methodologically valid because test results were not used to choose it. Removing all four is harmful on validation, so the time-correlated features collectively contain useful signal and should not be removed wholesale.

## 3. Platt calibration

A separate logistic (Platt) calibrator was fit on each chain's validation predictions and evaluated on that chain's held-out test slice.

| Chain | Raw Brier | Platt Brier | Change |
|---|---:|---:|---:|
| BTC | 0.1767 | 0.0436 | -0.1331 |
| ETH | 0.0456 | 0.0386 | -0.0070 |

Calibration substantially improves the BTC probability error and modestly improves ETH probability error. The calibrated probabilities are suitable for investigator-facing percentages only when the chain-specific calibrator is applied; the raw classifier remains the production behavior until reviewed.

## Conclusion

Recency weighting is worth keeping as a reviewed BTC challenger: after its own validation scan, threshold `0.88` respects the 2% FPR cap and improves overall F1/AUC-PR, but step 48 indicates a structural regime break that recency weighting cannot solve. The validation-only ablation selection favors `last_block_appeared_in`, with a held-out F1 of `0.4233` and AUC-PR of `0.3979`. Do not promote either challenger or calibrated output to production without review.

## 4. Combined recency weighting plus ablation

This third challenger applies both recency weighting and removal of `last_block_appeared_in`. Its threshold was selected from BTC validation steps 30-34 only using the same full candidate scan and 2% FPR cap. Threshold `0.90` was selected: validation FPR `1.66%`, validation recall `63.55%`.

| Variant | Precision | Recall | F1 | AUC-PR |
|---|---:|---:|---:|---:|
| Original baseline | 0.4820 | 0.3072 | 0.3753 | 0.3721 |
| Recency only, threshold 0.88 | 0.4222 | 0.4303 | 0.4262 | 0.4023 |
| Ablation only, `last_block_appeared_in` removed | 0.4055 | 0.4427 | 0.4233 | 0.3979 |
| Combined, threshold 0.90 | 0.4101 | 0.4289 | 0.4193 | 0.3808 |

### Combined variant BTC test steps

| Step | Precision | Recall | F1 | AUC-PR |
|---:|---:|---:|---:|---:|
| 35 | 0.6865 | 0.6928 | 0.6897 | 0.7342 |
| 36 | 0.7272 | 0.9274 | 0.8151 | 0.8941 |
| 37 | 0.8099 | 0.7968 | 0.8033 | 0.8367 |
| 38 | 0.4417 | 0.4892 | 0.4643 | 0.3017 |
| 39 | 0.1742 | 0.3622 | 0.2353 | 0.1366 |
| 40 | 0.3424 | 0.4215 | 0.3779 | 0.3582 |
| 41 | 0.2706 | 0.6069 | 0.3743 | 0.1921 |
| 42 | 0.3079 | 0.4691 | 0.3718 | 0.2121 |
| 43 | 0.0532 | 0.1414 | 0.0773 | 0.0557 |
| 44 | 0.4047 | 0.5516 | 0.4669 | 0.5133 |
| 45 | 0.0435 | 0.1724 | 0.0694 | 0.0193 |
| 46 | 0.1341 | 0.0692 | 0.0913 | 0.3634 |
| 47 | 0.0456 | 0.0700 | 0.0552 | 0.0418 |
| 48 | 0.0444 | 0.0053 | 0.0095 | 0.1257 |
| 49 | 0.5302 | 0.1212 | 0.1973 | 0.3556 |

The combined changes do not compound: combined F1 `0.4193` and AUC-PR `0.3808` are below both individual challengers. Recency-only is the final recommended candidate for a future promotion review; no variant is promoted here.
