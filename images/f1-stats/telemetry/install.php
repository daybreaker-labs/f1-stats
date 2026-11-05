<?php
declare(strict_types=1);

// Keep one autoloader and refuse changes to the upstream production dependencies.
$manifest = json_decode(file_get_contents('composer.json'), true, flags: JSON_THROW_ON_ERROR);
$original = json_decode(file_get_contents('composer.lock'), true, flags: JSON_THROW_ON_ERROR);
$overlay = json_decode(file_get_contents(__DIR__ . '/composer.json'), true, flags: JSON_THROW_ON_ERROR);
$manifest['require'] = array_merge($manifest['require'], $overlay['require']);
$manifest['autoload']['files'][] = 'telemetry/register.php';
// The SDK and Laravel hooks register providers through this Composer plugin.
$manifest['config']['allow-plugins']['tbachert/spi'] = true;
file_put_contents('composer.json', json_encode($manifest, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
$packages = implode(' ', array_keys($overlay['require']));
passthru('composer update --no-dev --no-interaction --no-progress --no-scripts --minimal-changes ' . $packages, $status);
if ($status !== 0) {
    exit($status);
}
$updated = json_decode(file_get_contents('composer.lock'), true, flags: JSON_THROW_ON_ERROR);
$locked = array_column($updated['packages'], null, 'name');
foreach ($original['packages'] as $package) {
    $current = $locked[$package['name']] ?? [];
    foreach (['version', 'source', 'dist'] as $field) {
        if (($package[$field] ?? null) !== ($current[$field] ?? null)) {
            throw new RuntimeException('Telemetry changed upstream dependency: ' . $package['name']);
        }
    }
}
