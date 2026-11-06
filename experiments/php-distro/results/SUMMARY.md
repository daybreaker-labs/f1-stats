# OpenTelemetry PHP Distro 0.7.0 offline /home results (2026-11-06)

Wall = curl time_total; CPU = container cgroup usage_usec delta (1 s settle). Overhead % vs baseline of the same app version and shape. Medians over n pairs; with n<=8 p95 is effectively the max. `fix` = f1_2022 branch tip 342d8e0 (FOUND-329 eager loading; upstream merge db41e92 not present locally, unverified identical), `main` = 08b0291.

| app | shape | n | variant | wall med ms | wall p95 ms | wall med % | wall p95 % | CPU med ms | CPU med % | CPU p95 % | identical |
|---|---|---|---|---|---|---|---|---|---|---|---|
