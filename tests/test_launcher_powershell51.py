"""The owner's machine has only Windows PowerShell 5.1; the launcher must work there."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Start-SORA.ps1"
windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell 5.1")


def test_launcher_does_not_use_powershell7_only_argument_list() -> None:
    # ProcessStartInfo.ArgumentList is null on Windows PowerShell 5.1 (.NET Framework), which
    # made `.\Start-SORA.ps1` fail with "You cannot call a method on a null-valued expression".
    code = [line for line in LAUNCHER.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")]
    assert not [line for line in code if ".ArgumentList" in line]


@windows_only
def test_native_argument_quoting_round_trips_in_windows_powershell(tmp_path: Path) -> None:
    values = ["plain", "has space", "C:\\Program Files\\SORA\\", 'say "hi"', "tail\\", "",
              'a\\"b', "C:\\Users\\x y\\token"]
    (tmp_path / "values.json").write_text(json.dumps(values), encoding="utf-8")
    script = tmp_path / "round_trip.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$text = Get-Content -Raw '{LAUNCHER}'\n"
        "$start = $text.IndexOf('function ConvertTo-NativeArgument')\n"
        "$end = $text.IndexOf(\"`n}\", $start) + 2\n"
        "Invoke-Expression $text.Substring($start, $end - $start)\n"
        f"$values = Get-Content -Raw '{tmp_path / 'values.json'}' | ConvertFrom-Json\n"
        f"$info = [Diagnostics.ProcessStartInfo]::new('{sys.executable}')\n"
        "$info.UseShellExecute = $false; $info.RedirectStandardOutput = $true\n"
        "$quoted = @($values | ForEach-Object { ConvertTo-NativeArgument ([string]$_) })\n"
        "$echo = '-c \"import sys,json;print(json.dumps(sys.argv[1:]))\" '\n"
        "$info.Arguments = $echo + ($quoted -join ' ')\n"
        "$p = [Diagnostics.Process]::Start($info)\n"
        "$p.StandardOutput.ReadToEnd(); $p.WaitForExit()\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == values
