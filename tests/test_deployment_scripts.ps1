param(
    [string]$PythonPath = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$profilePath = Join-Path $root "test-deployment-$([guid]::NewGuid().ToString('N')).json"
$envFile = [IO.Path]::GetTempFileName()
$global:DalilDeploymentTestState = @{ AzureCalls = [Collections.Generic.List[string]]::new(); Runtime = $null; Existing = $false }

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function az {
    $command = $args -join ' '
    $global:DalilDeploymentTestState.AzureCalls.Add($command)
    $global:LASTEXITCODE = 0
    switch -Wildcard ($command) {
        'account show *' { '{"state":"Enabled","name":"Test subscription"}'; break }
        'ad signed-in-user show *' { '{"id":"test-user","name":"Test user"}'; break }
        'rest *usages*' { '{"used":0,"limit":1000}'; break }
        'group list *' {
            if ($global:DalilDeploymentTestState.Existing) { '[{"name":"test-rg","tags":{"project":"dalil","environment":"dev"}}]' } else { '[]' }
            break
        }
        'cognitiveservices account list *' { '[{"name":"test-openai","kind":"OpenAI"}]'; break }
        'cognitiveservices account deployment list *' { '[{"name":"gpt-5-1","sku":{"name":"GlobalStandard","capacity":10},"properties":{"model":{"name":"gpt-5.1"}}},{"name":"text-embedding-3-large","sku":{"name":"Standard","capacity":100},"properties":{"model":{"name":"text-embedding-3-large"}}}]'; break }
        'containerapp list *' { '[{"properties":{"template":{"containers":[{"image":"testregistry.azurecr.io/current:release"}]}}}]'; break }
        'deployment sub what-if *' {
            $parameterFile = @($args | ForEach-Object { $_ } | Where-Object { $_ -like '@*runtime.parameters.json' })[0]
            $global:DalilDeploymentTestState.Runtime = (Get-Content $parameterFile.Substring(1) -Raw | ConvertFrom-Json -AsHashtable).parameters.runtimeSettings.value
            break
        }
        'deployment sub create *' { throw 'Regression test attempted provisioning' }
    }
}

function Read-Host {
    param([string]$Prompt)
    if ($Prompt.StartsWith('Type INGEST')) { return 'INGEST' }
    return 'STOP'
}

Push-Location $root
try {
    $profile = Get-Content (Join-Path $root 'accelerator.json') -Raw | ConvertFrom-Json -AsHashtable
    $profile.runtime.SEARCH_ENDPOINT = 'https://old-stack.search.windows.net'
    $profile.runtime.AOAI_CHAT_ENDPOINT = 'https://old-stack.openai.azure.com'
    $profile.runtime.AOAI_FAST_ENDPOINT = 'https://old-stack.openai.azure.com'
    $profile.runtime.COSMOS_ENDPOINT = 'https://old-stack.documents.azure.com'
    $profile | ConvertTo-Json -Depth 20 | Set-Content $profilePath -Encoding utf8
    & (Join-Path $root 'deploy-customer.ps1') -Subscription 'test-subscription' -ConfigPath $profilePath -PythonPath $PythonPath
    Assert-True ($null -ne $global:DalilDeploymentTestState.Runtime) 'Expected a cloud-free what-if preview'
    foreach ($key in @('SEARCH_ENDPOINT', 'AOAI_CHAT_ENDPOINT', 'AOAI_FAST_ENDPOINT', 'COSMOS_ENDPOINT', 'HISTORY_ENABLED')) {
        Assert-True (-not $global:DalilDeploymentTestState.Runtime.ContainsKey($key)) "Customer deployment reused override: $key"
    }
    Assert-True ($global:DalilDeploymentTestState.AzureCalls.Contains('account set --subscription test-subscription')) 'Customer subscription was not selected for ingestion'
    Assert-True (-not ($global:DalilDeploymentTestState.AzureCalls | Where-Object { $_ -like 'deployment sub create *' })) 'Unexpected provisioning'
    Write-Output 'Customer endpoint isolation and subscription selection: PASS'

    $global:DalilDeploymentTestState.Existing = $true
    $global:DalilDeploymentTestState.AzureCalls.Clear()
    & (Join-Path $root 'deploy-customer.ps1') -Subscription 'test-subscription' -ConfigPath $profilePath -PythonPath $PythonPath -UpdateExisting
    Assert-True (-not ($global:DalilDeploymentTestState.AzureCalls | Where-Object { $_ -like 'rest *usages*' })) 'Unchanged existing stack required spare quota'
    Write-Output 'Existing stack reuses allocated quota: PASS'
    $global:DalilDeploymentTestState.Existing = $false

    $profile.runtime.MODEL_PROVIDER = 'compass'
    $profile | ConvertTo-Json -Depth 20 | Set-Content $profilePath -Encoding utf8
    $rejected = $false
    try { & (Join-Path $root 'deploy-customer.ps1') -Subscription 'test-subscription' -ConfigPath $profilePath -PythonPath $PythonPath }
    catch { $rejected = $_.Exception.Message -like '*requires MODEL_PROVIDER=azure_openai*' }
    Assert-True $rejected 'Compass bootstrap must stop before provisioning without secret wiring'
    Write-Output 'Compass bootstrap guard: PASS'

    $profile.runtime.MODEL_PROVIDER = 'azure_openai'
    $profile | ConvertTo-Json -Depth 20 | Set-Content $profilePath -Encoding utf8
    "MODEL_PROVIDER=<CHOOSE_PROVIDER>`nGROUNDEDNESS_CHECK_ENABLED=`nCOMPASS_API_KEY=" | Set-Content $envFile -Encoding utf8
    $global:DalilDeploymentTestState.AzureCalls.Clear()
    & (Join-Path $root 'deploy.ps1') -Config $profilePath -EnvFile $envFile -ResourceGroup 'test-rg' -ContainerApp 'test-app' -Registry 'testregistry' -SyncEnv
    $sync = $global:DalilDeploymentTestState.AzureCalls | Where-Object { $_ -like '*--set-env-vars*' }
    Assert-True ($sync -match 'MODEL_PROVIDER=azure_openai') 'Placeholder .env value suppressed the profile provider'
    Assert-True ($sync -match 'GROUNDEDNESS_CHECK_ENABLED=true') 'Blank .env value suppressed profile groundedness'
    Assert-True ($sync -notmatch 'COMPASS_API_KEY=') 'Blank secret was synced'
    Write-Output 'Blank and placeholder .env fallback: PASS'
}
finally {
    Remove-Item $profilePath, $envFile -ErrorAction SilentlyContinue
    Remove-Variable DalilDeploymentTestState -Scope Global -ErrorAction SilentlyContinue
    Pop-Location
}