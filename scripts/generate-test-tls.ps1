[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$fixtureRoot = Join-Path $projectRoot "tests/fixtures/tls"
$certificatePath = Join-Path $fixtureRoot "localhost-test-cert.pem"
$privateKeyPath = Join-Path $fixtureRoot "localhost-test-key.pem"

New-Item -ItemType Directory -Force -Path $fixtureRoot | Out-Null
$rsa = [System.Security.Cryptography.RSA]::Create(2048)
try {
    $name = [System.Security.Cryptography.X509Certificates.X500DistinguishedName]::new(
        "CN=SORA P15 TEST ONLY"
    )
    $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        $name,
        $rsa,
        [System.Security.Cryptography.HashAlgorithmName]::SHA256,
        [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
    )
    $san = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
    $san.AddDnsName("localhost")
    $san.AddIpAddress([System.Net.IPAddress]::Loopback)
    $request.CertificateExtensions.Add($san.Build())
    $request.CertificateExtensions.Add(
        [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
            [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature,
            $true
        )
    )
    $certificate = $request.CreateSelfSigned(
        [System.DateTimeOffset]::UtcNow.AddDays(-1),
        [System.DateTimeOffset]::UtcNow.AddYears(20)
    )
    try {
        [System.IO.File]::WriteAllText($certificatePath, $certificate.ExportCertificatePem())
        [System.IO.File]::WriteAllText($privateKeyPath, $rsa.ExportPkcs8PrivateKeyPem())
    }
    finally {
        $certificate.Dispose()
    }
}
finally {
    $rsa.Dispose()
}

Write-Output "Generated test-only localhost TLS fixture. Never use it outside automated tests."
