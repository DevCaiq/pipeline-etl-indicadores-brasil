# Registra somente tarefas próprias do usuário atual, sem senha em argumentos.
$ErrorActionPreference = 'Stop'
$raizProjeto = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonOrquestracao = Join-Path $raizProjeto 'orquestracao\.venv\Scripts\pythonw.exe'
$gerenciador = Join-Path $raizProjeto 'orquestracao\gerenciar.py'
if (-not (Test-Path -LiteralPath $pythonOrquestracao)) {
    throw 'Prepare o ambiente isolado da orquestração antes de registrar tarefas.'
}
$usuarioAtual = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $usuarioAtual -LogonType Interactive -RunLevel Limited
$configuracoes = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
foreach ($acaoLocal in @('servidor', 'worker')) {
    $nomeTarefa = 'PipelineETL-Prefect-' + $acaoLocal
    $argumentos = '"' + $gerenciador + '" ' + $acaoLocal
    $existente = Get-ScheduledTask -TaskName $nomeTarefa -ErrorAction SilentlyContinue
    if ($existente -and ($existente.Actions.Execute -ne $pythonOrquestracao -or
            $existente.Actions.Arguments -ne $argumentos)) {
        throw "A tarefa $nomeTarefa já existe com outra ação; não será substituída."
    }
    $acao = New-ScheduledTaskAction -Execute $pythonOrquestracao -Argument $argumentos `
        -WorkingDirectory $raizProjeto
    $gatilho = New-ScheduledTaskTrigger -AtLogOn -User $usuarioAtual
    Register-ScheduledTask -TaskName $nomeTarefa -Action $acao -Trigger $gatilho `
        -Settings $configuracoes -Principal $principal -Force | Select-Object TaskName,State
}
