<?php

declare(strict_types=1);

namespace F1Stats\Telemetry;

use OpenTelemetry\API\Trace\SpanContextInterface;
use OpenTelemetry\Contrib\Otlp\SpanExporterFactory;
use OpenTelemetry\SDK\Common\Attribute\Attributes;
use OpenTelemetry\SDK\Common\Attribute\AttributesInterface;
use OpenTelemetry\SDK\Common\Future\CancellationInterface;
use OpenTelemetry\SDK\Common\Future\FutureInterface;
use OpenTelemetry\SDK\Common\Instrumentation\InstrumentationScope;
use OpenTelemetry\SDK\Common\Instrumentation\InstrumentationScopeInterface;
use OpenTelemetry\SDK\Resource\ResourceInfo;
use OpenTelemetry\SDK\Trace\Event;
use OpenTelemetry\SDK\Trace\Link;
use OpenTelemetry\SDK\Trace\SpanDataInterface;
use OpenTelemetry\SDK\Trace\SpanExporter\SpanExporterFactoryInterface;
use OpenTelemetry\SDK\Trace\SpanExporterInterface;
use OpenTelemetry\SDK\Trace\StatusData;
use OpenTelemetry\SDK\Trace\StatusDataInterface;

final class PrivacyExporterFactory implements SpanExporterFactoryInterface
{
    public function create(): SpanExporterInterface
    {
        return new PrivacyExporter((new SpanExporterFactory())->create());
    }
}

final class PrivacyExporter implements SpanExporterInterface
{
    public function __construct(private readonly SpanExporterInterface $exporter)
    {
    }

    public function export(iterable $batch, ?CancellationInterface $cancellation = null): FutureInterface
    {
        $sanitized = [];
        foreach ($batch as $span) {
            $sanitized[] = new PrivacySpan($span);
        }

        return $this->exporter->export($sanitized, $cancellation);
    }

    public function shutdown(?CancellationInterface $cancellation = null): bool
    {
        return $this->exporter->shutdown($cancellation);
    }

    public function forceFlush(?CancellationInterface $cancellation = null): bool
    {
        return $this->exporter->forceFlush($cancellation);
    }
}

final class PrivacySpan implements SpanDataInterface
{
    private readonly AttributesInterface $attributes;
    private readonly ResourceInfo $resource;
    private readonly InstrumentationScopeInterface $scope;

    public function __construct(private readonly SpanDataInterface $span)
    {
        // Instrumenters record raw URLs and SQL; only diagnostic dimensions leave the process.
        $this->attributes = self::keep($span->getAttributes(), [
            'http.request.method', 'http.method', 'http.route',
            'http.response.status_code', 'http.status_code',
            'server.address', 'server.port', 'network.protocol.version',
            'db.system', 'db.system.name', 'db.name', 'db.namespace',
            'db.operation', 'db.operation.name', 'db.collection.name', 'db.sql.table',
            'code.function.name', 'code.line.number', 'error.type',
        ]);
        $resource = $span->getResource();
        $this->resource = ResourceInfo::create(self::keep($resource->getAttributes(), [
            'service.name', 'service.namespace', 'service.version', 'service.instance.id',
            'deployment.environment', 'deployment.environment.name',
            'telemetry.sdk.name', 'telemetry.sdk.language', 'telemetry.sdk.version',
        ]), $resource->getSchemaUrl());
        $scope = $span->getInstrumentationScope();
        $this->scope = new InstrumentationScope(
            $scope->getName(), $scope->getVersion(), $scope->getSchemaUrl(), Attributes::create([]),
        );
    }

    private static function keep(AttributesInterface $attributes, array $keys): AttributesInterface
    {
        return Attributes::create(array_intersect_key($attributes->toArray(), array_flip($keys)));
    }

    public function getName(): string
    {
        $attributes = $this->attributes->toArray();
        $method = $attributes['http.request.method'] ?? $attributes['http.method'] ?? null;
        if (is_string($method)) {
            $method = in_array($method, ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH'], true)
                ? $method : 'HTTP';
            // http.route is the router template, not the requested URL or its parameter values.
            return isset($attributes['http.route']) ? $method . ' /' . ltrim($attributes['http.route'], '/') : $method;
        }
        $function = $attributes['code.function.name'] ?? null;
        if (is_string($function) && preg_match('/^[A-Za-z_\\\\][A-Za-z0-9_\\\\]*::[A-Za-z_][A-Za-z0-9_]*$/D', $function)) {
            return $function;
        }
        $operation = $attributes['db.operation.name'] ?? $attributes['db.operation'] ?? null;
        if (isset($attributes['db.system.name']) || isset($attributes['db.system'])) {
            return in_array($operation, ['SELECT', 'INSERT', 'UPDATE', 'DELETE'], true) ? 'sql ' . $operation : 'sql';
        }

        return 'internal';
    }

    public function getEvents(): array
    {
        $events = [];
        foreach ($this->span->getEvents() as $event) {
            // Exception messages and arbitrary event names can contain SQL bindings or URLs.
            $events[] = new Event(
                $event->getName() === 'exception' ? 'exception' : 'event',
                $event->getEpochNanos(),
                self::keep($event->getAttributes(), ['exception.type']),
            );
        }

        return $events;
    }

    public function getLinks(): array
    {
        return array_map(
            static fn ($link) => new Link($link->getSpanContext(), Attributes::create([])),
            $this->span->getLinks(),
        );
    }

    public function getStatus(): StatusDataInterface
    {
        return StatusData::create($this->span->getStatus()->getCode());
    }

    public function getAttributes(): AttributesInterface { return $this->attributes; }
    public function getResource(): ResourceInfo { return $this->resource; }
    public function getInstrumentationScope(): InstrumentationScopeInterface { return $this->scope; }
    public function getKind(): int { return $this->span->getKind(); }
    public function getContext(): SpanContextInterface { return $this->span->getContext(); }
    public function getParentContext(): SpanContextInterface { return $this->span->getParentContext(); }
    public function getTraceId(): string { return $this->span->getTraceId(); }
    public function getSpanId(): string { return $this->span->getSpanId(); }
    public function getParentSpanId(): string { return $this->span->getParentSpanId(); }
    public function getStartEpochNanos(): int { return $this->span->getStartEpochNanos(); }
    public function getEndEpochNanos(): int { return $this->span->getEndEpochNanos(); }
    public function hasEnded(): bool { return $this->span->hasEnded(); }
    public function getTotalDroppedEvents(): int { return $this->span->getTotalDroppedEvents(); }
    public function getTotalDroppedLinks(): int { return $this->span->getTotalDroppedLinks(); }
}
