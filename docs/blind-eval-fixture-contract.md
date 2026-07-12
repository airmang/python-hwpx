# Blind real-work evaluation — fixture contract

`hwpx.benchmark` freezes the S-070 benchmark protocol consumed by the installed
`run_fixture_benchmark` and `export_fixture_benchmark` surface. Strict fixture
validation requires at least 60 work orders spanning six families, at least
three materially named fixture clients, one artifact for every
work-order/client pair, and two independent agent-judge passes per artifact.

The fixture rail is a reproducibility and drift test, not a field evaluation.
Every protocol, result, aggregate, and generated projection therefore carries:

```json
{
  "humanControls": false,
  "humanJudges": false,
  "realAgentClients": false,
  "realHancomVerified": false,
  "humanLabels": false,
  "replacementClaimAllowed": false
}
```

`benchmarkGatePassed` means only that the frozen simulation met its structural
and metric target. `releaseGatePassed` remains false. Human review/edit minutes
and real cost remain `null` and `measured=false`; fixture values must not be
presented as human measurements.

The aggregate publishes Wilson 95% confidence intervals for acceptance and
abstention rates, per-family and per-client results, critical-failure counts,
and agent-judge agreement. `build_result_projections()` derives scorecard,
ROADMAP, gallery, and release-metric projections from the same aggregate;
`check_projection_drift()` rejects any checked-in projection that differs.
