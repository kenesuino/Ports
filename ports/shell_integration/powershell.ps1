param([string]$PortsToken)
# User profiles have already loaded through normal PowerShell startup.
$global:PortsPromptToken = $PortsToken
$global:PortsOriginalPrompt = $function:prompt
function global:prompt {
    $location = $ExecutionContext.SessionState.Path.CurrentFileSystemLocation.Path
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($location))
    [Console]::Write(([char]27) + "]777;ports;" + $global:PortsPromptToken + ";ready;" + $encoded + ([char]7))
    if ($global:PortsOriginalPrompt) { & $global:PortsOriginalPrompt } else { "PS $location> " }
}
