#!/bin/sh
# usage: privacy-traffic.sh <container>   Requests with known private values, sent to the OBI-selected container
# after the timed runs (never during them). Values are synthetic; privacy.py searches the export for them.
c=$1
C="curl -s -o /dev/null -w %{http_code}\n -H Host:home.fixture.test -b /tmp/pcj -c /tmp/pcj"
docker exec "$c" sh -c "rm -f /tmp/pcj
tk=\$(curl -s -H Host:home.fixture.test -b /tmp/pcj -c /tmp/pcj http://127.0.0.1:8080/users/login | grep -o 'name=\"_token\"[^>]*value=\"[^\"]*' | sed 's/.*value=\"//')
$C --data-urlencode _token=\$tk --data-urlencode email=home-fixture@example.test --data-urlencode password=home-fixture-password http://127.0.0.1:8080/users/authenticate
$C 'http://127.0.0.1:8080/home?email=home-fixture%40example.test&token=privacy-token-value&q=privacy-plain-value'
$C 'http://127.0.0.1:8080/ajax/ajaxGetVitoriasPilotoPorTemporada?temporada_id=privacy-season-value&_token='\$tk
$C 'http://127.0.0.1:8080/home?remember_web=privacy-cookie-like&password=privacy-password-value'
$C -H 'X-CSRF-TOKEN: privacy-header-csrf' -H 'Cookie: laravel_session=privacy-cookie-value' http://127.0.0.1:8080/home
$C http://127.0.0.1:8080/users/logout -X POST --data-urlencode _token=\$tk"
