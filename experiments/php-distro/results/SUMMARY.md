# OpenTelemetry PHP Distro 0.7.0 offline /home results (2026-11-06)

Wall = curl time_total; CPU = container cgroup usage_usec delta (1 s settle). Overhead % vs baseline of the same app version and shape. Medians over n pairs; with n<=8 p95 is effectively the max. `fix` = f1_2022 branch tip 342d8e0 (FOUND-329 eager loading; upstream merge db41e92 not present locally, identity unverified), `main` = 08b0291.

| app | shape | n | variant | wall med ms | wall p95 ms | wall med % | wall p95 % | CPU med ms | CPU med % | CPU p95 % | identical, all 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main | light | 8 | baseline | 2636 | 3367 | +0.0 | +0.0 | 1863 | +0.0 | +0.0 | True |
| main | light | 8 | distro | 3963 | 4064 | +50.4 | +20.7 | 3186 | +71.1 | +47.6 | True |
| main | light | 8 | distro-ratio | 3763 | 4281 | +42.7 | +27.1 | 2937 | +57.7 | +46.8 | True |
| main | light | 8 | distro-pdoff | 3806 | 4765 | +44.4 | +41.5 | 2986 | +60.3 | +63.5 | True |
| main | light | 8 | distro-ratio-pdoff | 3661 | 4457 | +38.9 | +32.4 | 2844 | +52.7 | +46.2 | True |
| main | light | 8 | distro-lite | 3324 | 4623 | +26.1 | +37.3 | 2525 | +35.6 | +45.6 | True |
| main | light | 8 | distro-ratio-lite | 3227 | 3335 | +22.4 | -1.0 | 2425 | +30.2 | +14.4 | True |
| main | heavy | 6 | baseline | 13144 | 13394 | +0.0 | +0.0 | 8008 | +0.0 | +0.0 | True |
| main | heavy | 6 | distro | 21203 | 21338 | +61.3 | +59.3 | 15853 | +98.0 | +96.0 | True |
| main | heavy | 6 | distro-ratio | 18202 | 20912 | +38.5 | +56.1 | 12787 | +59.7 | +91.3 | True |
| main | heavy | 6 | distro-pdoff | 18646 | 19560 | +41.9 | +46.0 | 13241 | +65.3 | +70.7 | True |
| main | heavy | 6 | distro-ratio-pdoff | 16497 | 18194 | +25.5 | +35.8 | 11237 | +40.3 | +58.0 | True |
| main | heavy | 6 | distro-lite | 14725 | 18718 | +12.0 | +39.7 | 9398 | +17.3 | +47.1 | True |
| main | heavy | 6 | distro-ratio-lite | 14592 | 15694 | +11.0 | +17.2 | 9309 | +16.2 | +23.3 | True |
| fix | light | 8 | baseline | 493 | 721 | +0.0 | +0.0 | 150 | +0.0 | +0.0 | True |
| fix | light | 8 | distro | 515 | 994 | +4.5 | +37.9 | 188 | +25.2 | +85.4 | True |
| fix | light | 8 | distro-ratio | 515 | 1105 | +4.5 | +53.3 | 185 | +23.1 | +87.6 | True |
| fix | light | 8 | distro-pdoff | 693 | 1417 | +40.6 | +96.6 | 267 | +77.7 | +129.2 | True |
| fix | light | 8 | distro-ratio-pdoff | 542 | 794 | +10.0 | +10.2 | 193 | +28.8 | +34.4 | True |
| fix | light | 8 | distro-lite | 500 | 690 | +1.4 | -4.3 | 178 | +18.7 | +12.1 | True |
| fix | light | 8 | distro-ratio-lite | 500 | 897 | +1.4 | +24.4 | 174 | +16.1 | +80.3 | True |
| fix | heavy | 6 | baseline | 993 | 1284 | +0.0 | +0.0 | 741 | +0.0 | +0.0 | True |
| fix | heavy | 6 | distro | 1346 | 1693 | +35.5 | +31.9 | 1087 | +46.7 | +39.6 | True |
| fix | heavy | 6 | distro-ratio | 1184 | 2238 | +19.2 | +74.3 | 920 | +24.2 | +107.5 | True |
| fix | heavy | 6 | distro-pdoff | 1086 | 2027 | +9.3 | +57.9 | 839 | +13.2 | +74.1 | True |
| fix | heavy | 6 | distro-ratio-pdoff | 1111 | 2424 | +11.9 | +88.8 | 866 | +16.9 | +113.1 | True |
| fix | heavy | 6 | distro-lite | 1123 | 1181 | +13.1 | -8.0 | 848 | +14.4 | +1.6 | True |
| fix | heavy | 6 | distro-ratio-lite | 1229 | 1498 | +23.8 | +16.7 | 956 | +28.9 | +38.1 | True |
