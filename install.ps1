param(
  [ValidateSet('claude-code', 'codex', 'github-copilot')]
  [string]$Platform = 'claude-code',
  [string]$TargetRoot,
  [switch]$Project,
  [switch]$DryRun,
  [switch]$Force,
  [switch]$ShowVersion
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Builder = Join-Path $Root 'scripts\build-distributions.py'
if (!(Test-Path -LiteralPath (Join-Path $Root "dist\$Platform"))) {
  & python $Builder
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$Installer = Join-Path $Root 'scripts\install.py'
$Arguments = @($Installer, '--platform', $Platform)
if ($TargetRoot) { $Arguments += @('--target-root', $TargetRoot) }
if ($Project) { $Arguments += '--project' }
if ($DryRun) { $Arguments += '--dry-run' }
if ($Force) { $Arguments += '--force' }
if ($ShowVersion) { $Arguments += '--show-version' }
& python @Arguments
exit $LASTEXITCODE
