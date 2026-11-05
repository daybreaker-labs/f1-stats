<?php

declare(strict_types=1);

require_once __DIR__ . '/PrivacyExporter.php';

// SDK 1.16 otherwise prefers Guzzle and instruments its own export requests.
OpenTelemetry\SDK\Common\Http\Psr\Client\Discovery::setDiscoverers([
    OpenTelemetry\SDK\Common\Http\Psr\Client\Discovery\Symfony::class,
]);
OpenTelemetry\SDK\Registry::registerSpanExporterFactory('f1_otlp', F1Stats\Telemetry\PrivacyExporterFactory::class);
