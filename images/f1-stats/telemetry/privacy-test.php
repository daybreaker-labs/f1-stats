<?php

declare(strict_types=1);

use F1Stats\Telemetry\PrivacyExporter;
use F1Stats\Telemetry\PrivacyExporterFactory;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;
use OpenTelemetry\Contrib\Otlp\SpanConverter;
use OpenTelemetry\SDK\Common\Attribute\Attributes;
use OpenTelemetry\SDK\Registry;
use OpenTelemetry\SDK\Resource\ResourceInfo;
use OpenTelemetry\SDK\Trace\SpanExporter\InMemoryExporter;
use OpenTelemetry\SDK\Trace\SpanProcessor\SimpleSpanProcessor;
use OpenTelemetry\SDK\Trace\TracerProvider;

require $argv[1] ?? dirname(__DIR__) . '/vendor/autoload.php';
require_once __DIR__ . '/register.php';
assert(ini_get('zend.assertions') === '1', 'Run with php -d zend.assertions=1 -d assert.exception=1');
assert(count(iterator_to_array(Nevay\SPI\ServiceLoader::load(
    OpenTelemetry\API\Instrumentation\AutoInstrumentation\HookManagerInterface::class,
))) > 0, 'The SPI Composer plugin must register the SDK hook manager');
// Export through an uninstrumented client to avoid tracing the telemetry requests.
assert(OpenTelemetry\SDK\Common\Http\Psr\Client\Discovery::find() instanceof Symfony\Component\HttpClient\Psr18Client);

$original = new InMemoryExporter();
$provider = TracerProvider::builder()
    ->setResource(ResourceInfo::create(Attributes::create([
        'service.name' => 'f1-stats', 'deployment.environment' => 'production',
        'process.command_args' => ['secret-resource'],
    ])))
    ->addSpanProcessor(new SimpleSpanProcessor($original))
    ->build();
$tracer = $provider->getTracer('privacy-test', '1', null, ['secret-scope' => 'secret-scope']);
$parent = $tracer->spanBuilder('parent')->startSpan();
$context = $parent->storeInContext(OpenTelemetry\Context\Context::getCurrent());
$span = $tracer->spanBuilder('GET /stats?secret-name=1')
    ->setParent($context)
    ->setSpanKind(SpanKind::KIND_SERVER)
    ->setAttributes([
        'http.request.method' => 'GET', 'http.route' => 'stats/{id}',
        'http.response.status_code' => 500, 'server.address' => 'example.test',
        'url.full' => 'https://example.test/stats?secret-url=1', 'url.query' => 'secret-query=1',
        'http.request.header.cookie' => ['secret-cookie'], 'db.query.text' => "SELECT 'secret-sql'",
        'db.statement' => "SELECT 'secret-old-sql'", 'db.query.parameter.id' => 'secret-binding',
        'unrecognized.attribute' => 'secret-unknown',
    ])
    ->addLink($parent->getContext(), ['http.request.header.cookie' => 'secret-link'])
    ->startSpan();
$span->recordException(new RuntimeException('secret-exception'));
$span->addEvent('secret-event-name', ['secret-event-attribute' => 'secret-event-value']);
$span->setStatus(StatusCode::STATUS_ERROR, 'secret-status');
$span->end();
$parent->end();
$source = $original->getSpans()[0];
$sink = new InMemoryExporter();
$exporter = new PrivacyExporter($sink);
assert($exporter->export([$source])->await());
$safe = $sink->getSpans()[0];
$wire = (new SpanConverter())->convert([$safe])->serializeToJsonString();
assert(!str_contains($wire, 'secret-'), $wire);
assert($safe->getName() === 'GET /stats/{id}');
assert($safe->getAttributes()->toArray()['http.response.status_code'] === 500);
assert($safe->getResource()->getAttributes()->toArray()['deployment.environment'] === 'production');
assert($safe->getEvents()[0]->getAttributes()->toArray()['exception.type'] === RuntimeException::class);
assert($safe->getEvents()[0]->getEpochNanos() === $source->getEvents()[0]->getEpochNanos());
assert($safe->getLinks()[0]->getSpanContext() === $source->getLinks()[0]->getSpanContext());
assert($safe->getStatus()->getCode() === StatusCode::STATUS_ERROR);
assert($safe->getStatus()->getDescription() === '');
foreach (['getKind', 'getContext', 'getParentContext', 'getTraceId', 'getSpanId', 'getParentSpanId',
    'getStartEpochNanos', 'getEndEpochNanos', 'hasEnded', 'getTotalDroppedEvents', 'getTotalDroppedLinks'] as $method) {
    assert($safe->$method() === $source->$method(), $method);
}
foreach ([['db.system.name' => 'mysql', 'db.operation.name' => 'SELECT'],
    ['db.system.name' => 'mysql', 'code.function.name' => 'PDOStatement::execute'], []] as $index => $attributes) {
    $db = $tracer->spanBuilder("SELECT 'secret-name'")->setAttributes($attributes)->startSpan();
    $db->end();
    $source = $original->getSpans()[array_key_last($original->getSpans())];
    assert($exporter->export([$source])->await());
    $safe = $sink->getSpans()[array_key_last($sink->getSpans())];
    assert($safe->getName() === ['sql SELECT', 'PDOStatement::execute', 'internal'][$index]);
}
assert($exporter->forceFlush());
assert($exporter->shutdown());
assert(!$exporter->export([$source])->await());
assert(Registry::spanExporterFactory('f1_otlp') instanceof PrivacyExporterFactory);
echo "telemetry privacy: passed\n";
