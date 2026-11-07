<?php
declare(strict_types=1);

// Browser reports are untrusted; retain origins, never URL paths or samples.
function reportOrigin(mixed $value): ?string
{
    if (!is_string($value) || strlen($value) > 4096) {
        return null;
    }
    if (in_array($value, ['inline', 'eval', 'wasm-eval'], true)) {
        return $value;
    }
    $url = parse_url($value);
    if (!is_array($url) || !isset($url['scheme'])) {
        return null;
    }
    $scheme = strtolower($url['scheme']);
    if (in_array($scheme, ['data', 'blob', 'about', 'chrome-extension', 'moz-extension'], true)) {
        return $scheme . ':';
    }
    if (!in_array($scheme, ['https', 'http'], true) || !isset($url['host'])) {
        return null;
    }
    return $scheme . '://' . strtolower($url['host']) . (isset($url['port']) ? ':' . $url['port'] : '');
}

header('Cache-Control: no-store');
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    header('Allow: POST');
    http_response_code(405);
    exit;
}
if (strtolower(trim(explode(';', $_SERVER['CONTENT_TYPE'] ?? '')[0])) !== 'application/csp-report') {
    http_response_code(415);
    exit;
}
$body = file_get_contents('php://input', false, null, 0, 16385);
if ($body === false || strlen($body) > 16384) {
    http_response_code(413);
    exit;
}
$decoded = json_decode($body, false, 8);
$report = is_object($decoded) ? ($decoded->{'csp-report'} ?? null) : null;
$directive = is_object($report) ? ($report->{'effective-directive'} ?? null) : null;
$documentOrigin = is_object($report) ? reportOrigin($report->{'document-uri'} ?? null) : null;
if (!is_string($directive) || !preg_match('/\A(?:[a-z]+-src(?:-elem|-attr)?|base-uri|form-action|frame-ancestors)\z/', $directive) || strlen($directive) > 40) {
    http_response_code(400);
    exit;
}
if ($documentOrigin === null || !str_starts_with($documentOrigin, 'http') || ($report->disposition ?? 'report') !== 'report') {
    http_response_code(400);
    exit;
}
$event = [
    'level' => 'info',
    'event' => 'csp_violation',
    'disposition' => 'report',
    'directive' => $directive,
    'document_origin' => $documentOrigin,
    'blocked_origin' => reportOrigin($report->{'blocked-uri'} ?? null),
    'source_origin' => reportOrigin($report->{'source-file'} ?? null),
];
foreach (['line-number', 'column-number'] as $field) {
    $value = $report->{$field} ?? null;
    if (is_int($value) && $value >= 0 && $value <= 10000000) {
        $event[str_replace('-', '_', $field)] = $value;
    }
}
$written = file_put_contents('php://stderr', json_encode($event, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE) . "\n");
http_response_code($written === false ? 503 : 204);
