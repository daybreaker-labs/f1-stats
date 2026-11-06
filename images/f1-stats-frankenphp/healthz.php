<?php
// Liveness only: proves a PHP thread answers without booting Laravel or
// reaching MySQL, as php-fpm's ping page did.
header('Content-Type: text/plain;charset=UTF-8');
header('Expires: Thu, 01 Jan 1970 00:00:00 GMT');
header('Cache-Control: no-cache, no-store, must-revalidate, max-age=0');
echo 'ok';
