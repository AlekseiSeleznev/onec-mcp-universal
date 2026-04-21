param(
    [int]$MaxTokens = 200000,
    [int]$WarnPercent = 70,
    [int]$CriticalPercent = 85
)

$inputText = $input | Out-String
$delta = [math]::Floor($inputText.Length / 4)
$currentTokens = 0
$parsed = 0
if ([int]::TryParse([string]$env:ONEC_CONTEXT_TOKENS, [ref]$parsed)) {
    $currentTokens = $parsed
}

$current = $currentTokens + $delta
$env:ONEC_CONTEXT_TOKENS = $current

$pct = [math]::Floor(($current / $MaxTokens) * 100)
if ($pct -ge $CriticalPercent) {
    [Console]::Error.WriteLine("!! Context ${pct}% (${current} tokens). Save session now: /session-save")
} elseif ($pct -ge $WarnPercent) {
    [Console]::Error.WriteLine("! Context ${pct}% (${current} tokens). Consider /session-save")
}

$inputText
