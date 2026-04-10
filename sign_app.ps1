# Script para autofirmar el ejecutivo y reducir alertas de antivirus
# Creado por: Dev White (Hector Zambrano)
# Requiere Windows SDK para 'signtool.exe'

# Forzar el directorio de trabajo al de la ubicación del script
Set-Location $PSScriptRoot

$exePath = "dist\EpubToMP3.exe"
$certName = "EpubToMP3Cert"

# 0. Verificar y auto-lanzar como Administrador si es necesario
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Lanzando script como administrador..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

if (-not (Test-Path $exePath)) {
    Write-Host "No se encontró el archivo EXE en 'dist\'." -ForegroundColor Yellow
    $choice = Read-Host "¿Deseas ejecutar la compilación ahora? (S/N)"
    if ($choice -eq "S" -or $choice -eq "s") {
        Write-Host "Iniciando compilación..." -ForegroundColor Cyan
        if (Test-Path ".\.venv\Scripts\python.exe") {
            & ".\.venv\Scripts\python.exe" build.py
        } else {
            python build.py
        }
        
        if (-not (Test-Path $exePath)) {
            Write-Host "ERROR: La compilación falló o no generó el archivo esperado." -ForegroundColor Red
            Read-Host "Presiona Enter para salir"
            exit
        }
    } else {
        Write-Host "Por favor, ejecuta la compilación primero (python build.py)." -ForegroundColor White
        Read-Host "Presiona Enter para salir"
        exit
    }
}

# 1. Limpiar y buscar Certificado Autofirmado
$oldCerts = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My | Where-Object { $_.Subject -like "*CN=$certName*" }

# Si el certificado vence en menos de 4 años, asumimos que es el viejo de 1 año y lo renovamos
if ($oldCerts.Count -eq 1 -and $oldCerts[0].NotAfter -lt (Get-Date).AddYears(4)) {
    Write-Host "Certificado de corta duración detectado. Renovando a 5 años..." -ForegroundColor Gray
    Remove-Item $oldCerts[0].PSPath -ErrorAction SilentlyContinue
    $cert = $null
} elseif ($oldCerts.Count -gt 1) {
    Write-Host "Limpiando certificados duplicados antiguos..." -ForegroundColor Gray
    $oldCerts | ForEach-Object { Remove-Item $_.PSPath -ErrorAction SilentlyContinue }
    $cert = $null
} else {
    $cert = $oldCerts | Select-Object -First 1
}

if (-not $cert) {
    Write-Host "Creando nuevo certificado autofirmado en el almacén de la máquina..." -ForegroundColor Cyan
    try {
        $expiration = (Get-Date).AddYears(5)
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=$certName" -CertStoreLocation "Cert:\LocalMachine\My" -NotAfter $expiration
    } catch {
        Write-Host "Error al crear el certificado: $($_.Exception.Message)" -ForegroundColor Red
        Read-Host "Presiona Enter para salir"
        exit
    }
} else {
    Write-Host "Cargando certificado existente ($($cert.Thumbprint))..." -ForegroundColor Cyan
}

# Determinar si necesitamos el flag /sm (System Store)
$useLocalMachine = $cert.PSParentPath -like "*LocalMachine*"

# 2. Buscar signtool.exe — primero en PATH, luego en rutas conocidas del Windows SDK
$signtool = $null

# Intentar desde PATH directamente
$fromPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
if ($fromPath) {
    $signtool = $fromPath.Source
}

# Si no está en PATH, buscar en rutas conocidas del SDK (x64 preferido, luego x86)
if (-not $signtool) {
    $sdkRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (Test-Path $sdkRoot) {
        # Buscar todas las versiones disponibles y tomar la más reciente (x64 preferido)
        $found = Get-ChildItem -Path $sdkRoot -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -like "*\x64\*" } |
                 Sort-Object FullName -Descending |
                 Select-Object -First 1

        # Si no hay x64, intentar x86
        if (-not $found) {
            $found = Get-ChildItem -Path $sdkRoot -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
                     Where-Object { $_.FullName -like "*\x86\*" } |
                     Sort-Object FullName -Descending |
                     Select-Object -First 1
        }

        if ($found) {
            $signtool = $found.FullName
        }
    }
}

if ($signtool) {
    Write-Host "signtool.exe encontrado en: $signtool" -ForegroundColor Green
    Write-Host "Firmando ejecutable..." -ForegroundColor Green

    # Construir argumentos — /sm solo si el cert está en LocalMachine
    $signArgs = @(
        "sign",
        "/fd", "SHA256",
        "/sha1", $cert.Thumbprint,
        "/tr", "http://timestamp.digicert.com",
        "/td", "sha256",
        "/s", "My",
        "/v"
    )
    if ($useLocalMachine) {
        $signArgs += "/sm"
    }
    $signArgs += $exePath

    & $signtool @signArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Ejecutable firmado correctamente." -ForegroundColor Green
    } else {
        Write-Host "❌ Error al firmar. Código de salida: $LASTEXITCODE" -ForegroundColor Red
    }
} else {
    Write-Host "ADVERTENCIA: No se encontró 'signtool.exe'. El ejecutable no estará firmado." -ForegroundColor Yellow
    Write-Host "Esta herramienta es parte del Windows SDK." -ForegroundColor Gray
    Write-Host "Link de descarga: https://developer.microsoft.com/es-es/windows/downloads/windows-sdk/" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Proceso terminado." -ForegroundColor White
Read-Host "Presiona Enter para cerrar esta ventana"
