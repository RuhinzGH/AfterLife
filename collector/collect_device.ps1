<#
    Afterlife device collector.

    Read-only. Emits one JSON object describing the machine it runs on:
    identity, CPU, TPM, firmware, memory, storage and battery wear.
    Without -PostUrl it only prints the JSON. With -PostUrl and -Token (how the
    deep-scan page runs it) it sends that one JSON object to AfterLife, and
    nothing else: no file contents, names or browsing history.

    Every probe is wrapped: on a locked-down or older box, an unavailable
    class yields null for that field rather than killing the run.
#>

[CmdletBinding()]
param(
    [switch]$Pretty,
    [string]$PostUrl,   # if set, POST the scan here instead of only printing
    [string]$Token      # session token the web app is polling for
)

function Try-Get {
    param([scriptblock]$Block, $Default = $null)
    try { $v = & $Block; if ($null -eq $v) { return $Default }; return $v }
    catch { return $Default }
}

# Sentinel distinct from $null/$false so downstream code (and humans) can tell
# "the machine has none of this" apart from "the probe was denied/unavailable".
# ConvertTo-Json renders this as the string "UNKNOWN", never a bare false.
$Unknown = "UNKNOWN"

# ---------- TPM probe, started first and read last ----------
# Querying root\cimv2\security\microsofttpm blocks for about 5.6 seconds on a
# typical machine -- it is WMI provider start-up, not the amount of data, so it
# costs the same however little you ask for. Measured repeatedly at ~5.0-5.6 s,
# well clear of run-to-run noise, which is what makes it worth overlapping when
# the earlier attempt at parallelising a ~3 s block was not.
#
# It is started here and read at the TPM section below. By then the rest of the
# script has been working for many seconds, so the wait is normally already over.
$tpmJob = Start-Job -ScriptBlock {
    try {
        $t = Get-CimInstance -Namespace "root\cimv2\security\microsofttpm" `
                             -ClassName Win32_Tpm -ErrorAction Stop
        if ($t) {
            [ordered]@{ ok = $true; present = $true
                        spec = if ($t.SpecVersion) { ($t.SpecVersion -split ",")[0].Trim() } else { $null }
                        enabled = [bool]$t.IsEnabled_InitialValue }
        } else {
            [ordered]@{ ok = $true; present = $false; spec = $null; enabled = $false }
        }
    } catch {
        # Almost always access denied without elevation. Reported as "could not
        # read", never as "no TPM" -- the difference decides a Windows 11 verdict.
        [ordered]@{ ok = $false }
    }
}

# ---------- identity ----------
$cs  = Try-Get { Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop }
$os  = Try-Get { Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop }
$bios = Try-Get { Get-CimInstance -ClassName Win32_BIOS -ErrorAction Stop }

# Win32_ComputerSystem.Model is often a cryptic board/SKU code (e.g. "8A78"),
# not the name printed on the box. Most OEMs (HP, Lenovo, ASUS, Dell) also
# populate a friendlier consumer-facing family/series name in the firmware --
# this is where "Victus", "ThinkPad X1 Carbon", "ROG Strix" etc. actually live.
# Not universal (some boards leave it blank or generic), so this is a second
# candidate for the backend to pick from, not a guaranteed replacement.
$systemFamily = Try-Get {
    (Get-ItemProperty -Path "HKLM:\HARDWARE\DESCRIPTION\System\BIOS" -Name SystemFamily -ErrorAction Stop).SystemFamily
}

# Windows feature-update id (22H2 / 24H2 ...) lives in the registry, not CIM.
$cv = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"
$releaseId = Try-Get { (Get-ItemProperty -Path $cv -Name DisplayVersion -ErrorAction Stop).DisplayVersion }
if (-not $releaseId) {
    $releaseId = Try-Get { (Get-ItemProperty -Path $cv -Name ReleaseId -ErrorAction Stop).ReleaseId }
}

# ---------- cpu ----------
$cpu = Try-Get { Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop | Select-Object -First 1 }

# ---------- gpu ----------
# First non-Microsoft Basic Render Driver adapter -- good enough for a rough
# GPU tier bucket, not meant to distinguish exact models.
$gpu = Try-Get {
    Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop |
        Where-Object { $_.Name -notlike "*Basic Render*" } | Select-Object -First 1
}

# ---------- elevation ----------
# Several probes below are readable only by an administrator. Record which we are,
# so a denied probe is never mistaken for a negative finding.
$isElevated = Try-Get {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} $false

# ---------- firmware / secure boot ----------
$sbState = "HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State"
$secureBootEnabled = Try-Get { (Get-ItemProperty -Path $sbState -Name UEFISecureBootEnabled -ErrorAction Stop).UEFISecureBootEnabled }
# Presence of the SecureBoot\State key implies UEFI firmware; legacy BIOS lacks it.
$isUefi = Test-Path $sbState

# ---------- secure boot certificate expiry (the 2026 cliff) ----------
# Microsoft's 2011 Secure Boot certificates retire through 2026; the 2023
# replacements arrive via Windows Update but some older firmware will not accept
# them without a vendor BIOS update first. A machine that misses this keeps
# booting -- it just stops getting early-boot security fixes, which is exactly the
# kind of quiet degradation that gets working hardware written off.
#
# Get-SecureBootUEFI returns the raw signature database; we look for the 2023
# issuer strings inside it. Needs elevation, so a non-admin scan reports UNKNOWN
# rather than guessing -- telling someone they are covered when we never looked is
# the one wrong answer here.
$sbCerts = [ordered]@{ checked = $false; db_2023 = $null; kek_2023 = $null; subjects = @() }

# Walk the EFI_SIGNATURE_LIST structures and pull out real certificates, rather
# than string-matching the raw bytes. Those bytes are DER: names inside are
# PrintableString/UTF8String (single byte), so decoding the blob as UTF-16 and
# searching it finds nothing even when the certificate is sitting right there --
# which would report every machine as missing the 2023 set. Parsing properly
# removes the guesswork.
#
# Layout per list: SignatureType GUID (16) | ListSize (4) | HeaderSize (4) |
# SigSize (4) | header | entries of [owner GUID (16) + DER cert].
function Get-SecureBootCertSubjects($varName) {
    $out = @()
    $raw = (Get-SecureBootUEFI -Name $varName -ErrorAction Stop).Bytes
    $X509_GUID = [Guid]"a5c059a1-94e4-4aa7-87b5-ab155c2bf072"
    $i = 0
    while ($i + 28 -le $raw.Length) {
        $type     = [Guid][byte[]]$raw[$i..($i+15)]
        $listSize = [BitConverter]::ToUInt32($raw, $i + 16)
        $hdrSize  = [BitConverter]::ToUInt32($raw, $i + 20)
        $sigSize  = [BitConverter]::ToUInt32($raw, $i + 24)
        if ($listSize -le 0 -or $sigSize -le 16 -or ($i + $listSize) -gt $raw.Length) { break }
        if ($type -eq $X509_GUID) {
            $p   = $i + 28 + $hdrSize
            $end = $i + $listSize
            while ($p + $sigSize -le $end) {
                try {
                    $der = [byte[]]$raw[($p + 16)..($p + $sigSize - 1)]   # skip owner GUID
                    $c = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 (,$der)
                    $out += $c.Subject
                } catch { }
                $p += $sigSize
            }
        }
        $i += $listSize
    }
    return $out
}

if ($isUefi) {
    try {
        $dbSubjects  = @(Get-SecureBootCertSubjects 'db')
        $kekSubjects = @(Get-SecureBootCertSubjects 'KEK')
        # Parsing nothing at all means our parser failed, NOT that the machine has
        # no certificates -- a device with Secure Boot on always has some. Treating
        # that as "missing" would tell a perfectly healthy PC it is at risk, so it
        # stays unchecked instead.
        if ($dbSubjects.Count -gt 0 -or $kekSubjects.Count -gt 0) {
            $sbCerts.checked  = $true
            $sbCerts.db_2023  = [bool]($dbSubjects  -match '2023')
            $sbCerts.kek_2023 = [bool]($kekSubjects -match '2023')
            $sbCerts.subjects = @($dbSubjects + $kekSubjects)
        }
    } catch {
        # Not elevated, or the cmdlet is unavailable on this build. Stays unchecked.
    }
}

# ---------- which hardening levers are already pulled ----------
# Read-only. Each key matches afterlife/hardening.py LEVERS so the backend can say
# "already handled" vs "still open" instead of listing every action blindly.
# $true means the surface is already closed. $null means we could not tell.
# Every service is fetched ONCE, up front, and looked up from a hashtable after.
#
# This used to run one filtered CIM query per service. Six of those measured
# 6,265 ms against 1,235 ms for a single unfiltered query returning all of them --
# the cost is per-query setup, not the amount of data, so asking six precise
# questions is five times slower than asking one broad one and filtering here.
# Easily the largest single saving available in this script.
$svcByName = @{}
try {
    foreach ($s in Get-CimInstance Win32_Service -ErrorAction Stop) {
        $svcByName[$s.Name.ToLower()] = $s
    }
} catch { }

function Test-ServiceOff($name) {
    $s = $svcByName[$name.ToLower()]
    # Absent from the table means either the service genuinely is not installed --
    # which is "off" in every sense that matters to a hardening question -- or the
    # query above failed wholesale. Those are distinguished by whether the table
    # has anything in it at all, so a failed query still reports "unknown" rather
    # than declaring every lever safely closed.
    if (-not $s) { return $(if ($svcByName.Count -gt 0) { $true } else { $null }) }
    return ($s.State -ne 'Running' -and $s.StartMode -eq 'Disabled')
}
function Test-FeatureOff($name) {
    try {
        $f = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction Stop
        return ($f.State -ne 'Enabled')
    } catch { return $null }
}
function Test-RegEquals($path, $name, $want) {
    try { return ((Get-ItemProperty -Path $path -Name $name -ErrorAction Stop).$name -eq $want) }
    catch { return $null }
}
# Some of these values only exist once somebody has explicitly set them, and their
# absence has a documented default. Windows Script Host, for instance, is enabled
# unless Enabled=0 is present -- so reporting "unknown" there would hide a surface
# that is definitely open. $MissingMeans is what absence proves, not a guess.
function Test-RegEqualsOrDefault($path, $name, $want, $MissingMeans) {
    try { return ((Get-ItemProperty -Path $path -Name $name -ErrorAction Stop).$name -eq $want) }
    catch { if (Test-Path $path) { return $MissingMeans } else { return $MissingMeans } }
}

$mitigationState = [ordered]@{
    spooler         = Test-ServiceOff 'Spooler'
    webdav          = Test-ServiceOff 'WebClient'
    remote_registry = Test-ServiceOff 'RemoteRegistry'
    search          = Test-ServiceOff 'WSearch'
    fax             = Test-ServiceOff 'Fax'
    bluetooth       = Test-ServiceOff 'bthserv'
    smbv1           = Test-FeatureOff 'SMB1Protocol'
    psv2            = Test-FeatureOff 'MicrosoftWindowsPowerShellV2Root'
    rdp             = Test-RegEquals 'HKLM:\System\CurrentControlSet\Control\Terminal Server' 'fDenyTSConnections' 1
    # WSH ships enabled; the Enabled value only appears once someone disables it.
    wsh             = Test-RegEqualsOrDefault 'HKLM:\SOFTWARE\Microsoft\Windows Script Host\Settings' 'Enabled' 0 $false
    # Same shape: Remote Assistance is permitted unless fAllowToGetHelp=0 is set.
    remote_assist   = Test-RegEqualsOrDefault 'HKLM:\SYSTEM\CurrentControlSet\Control\Remote Assistance' 'fAllowToGetHelp' 0 $false
}

# ---------- storage ----------
$sysDrive = Try-Get { Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'" -ErrorAction Stop }
$physical = Try-Get { Get-PhysicalDisk -ErrorAction Stop | Select-Object -First 1 }

# disk_health above is Storage Management's coarse Healthy/Warning/Unhealthy enum --
# it only flips once Windows itself has given up on the drive. StorageReliabilityCounter
# is the actual SMART-derived telemetry underneath it (wear %, uncorrected read/write
# errors, temperature, power-on hours) and can show degradation well before the coarse
# enum ever changes. Admin-gated on most builds -- degrades to an empty list, not fatal.
#
# Built with a direct try/catch + @(), deliberately NOT routed through Try-Get: a
# PowerShell function/scriptblock's implicit RETURN silently unwraps a single-element
# array into a bare scalar (well-known gotcha), but only reconstructs correctly at
# either end (0 or 2+ items) -- so with N=1 disk this array would serialize as a bare
# JSON object instead of a one-item array, and downstream code expecting an array
# would break on exactly the single-disk case. A direct assignment inside try/catch
# never crosses that function-return boundary, so @() here means what it says at any
# count (0, 1, or many) -- same reasoning applies to every array field below.
$reliability = @()
try {
    $reliability = @(Get-PhysicalDisk -ErrorAction Stop | ForEach-Object {
        $pd = $_
        $rc = Get-StorageReliabilityCounter -PhysicalDisk $pd -ErrorAction Stop
        [ordered]@{
            disk_number             = $pd.DeviceId
            model                   = $pd.FriendlyName
            wear_pct                = if ($null -ne $rc.Wear) { $rc.Wear } else { $null }
            temperature_c           = if ($null -ne $rc.Temperature) { $rc.Temperature } else { $null }
            power_on_hours          = if ($null -ne $rc.PowerOnHours) { $rc.PowerOnHours } else { $null }
            read_errors_uncorrected = $rc.ReadErrorsUncorrected
            write_errors_uncorrected = $rc.WriteErrorsUncorrected
            read_errors_corrected   = $rc.ReadErrorsCorrected
            write_errors_corrected  = $rc.WriteErrorsCorrected
        }
    })
} catch { }

# ---------- NVMe SMART / Health Information log (page 0x02) ----------
# StorageReliabilityCounter above is a *translation layer* and drops most of what
# an NVMe drive actually reports -- on the dev machine it returned nulls for
# power-on hours and every error counter, and rounded wear to 0 when the drive's
# own figure was 3%. Querying the drive's native health log directly recovers all
# of it: critical warning, media errors, error-log entries, unsafe shutdowns,
# available spare, and true percentage-used.
#
# AfterLife reads two of them today -- the critical-warning flag and the share of
# rated write life used -- to describe storage health. The rest are collected so a
# future drive-failure score has the inputs it would need.
#
# IOCTL_STORAGE_QUERY_PROPERTY with StorageDeviceProtocolSpecificProperty is a
# metadata query rather than a data read, so it succeeds with dwDesiredAccess=0 --
# verified working WITHOUT elevation, which is what makes it usable in the
# unprivileged scan path. Requesting GENERIC_READ|GENERIC_WRITE here instead would
# force a UAC prompt for no benefit.
$nvmeHealth = @()
try {
    if (-not ("AfterlifeNvme" -as [type])) {
        Add-Type -ErrorAction Stop -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class AfterlifeNvme {
    [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Auto)]
    public static extern IntPtr CreateFile(string lpFileName, uint dwDesiredAccess,
        uint dwShareMode, IntPtr lpSecurityAttributes, uint dwCreationDisposition,
        uint dwFlagsAndAttributes, IntPtr hTemplateFile);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool DeviceIoControl(IntPtr hDevice, uint dwIoControlCode,
        byte[] lpInBuffer, uint nInBufferSize, byte[] lpOutBuffer, uint nOutBufferSize,
        ref uint lpBytesReturned, IntPtr lpOverlapped);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr hObject);
}
"@
    }

    # Enumerate real drive numbers rather than assuming PhysicalDrive0 -- a machine
    # with an SD-card reader or a secondary disk can shift the NVMe boot drive.
    $driveNumbers = Try-Get {
        @(Get-CimInstance -ClassName Win32_DiskDrive -ErrorAction Stop |
            ForEach-Object { $_.Index })
    } @(0)

    foreach ($dn in $driveNumbers) {
        $h = [AfterlifeNvme]::CreateFile("\\.\PhysicalDrive$dn", [uint32]0, [uint32]3,
                [IntPtr]::Zero, 3, 0, [IntPtr]::Zero)
        if ($h -eq [IntPtr]::Zero -or $h -eq [IntPtr](-1)) { continue }

        $bufSize = 4096
        $inBuf = New-Object byte[] $bufSize
        [BitConverter]::GetBytes([int]50).CopyTo($inBuf, 0)   # StorageDeviceProtocolSpecificProperty
        [BitConverter]::GetBytes([int]0).CopyTo($inBuf, 4)    # PropertyStandardQuery
        [BitConverter]::GetBytes([int]3).CopyTo($inBuf, 8)    # ProtocolTypeNvme
        [BitConverter]::GetBytes([int]2).CopyTo($inBuf, 12)   # NVMeDataTypeLogPage
        [BitConverter]::GetBytes([int]2).CopyTo($inBuf, 16)   # log page 0x02
        [BitConverter]::GetBytes([int]0).CopyTo($inBuf, 20)
        [BitConverter]::GetBytes([int]48).CopyTo($inBuf, 24)
        [BitConverter]::GetBytes([int]512).CopyTo($inBuf, 28)

        $outBuf = New-Object byte[] $bufSize
        $ret = [uint32]0
        $ok = [AfterlifeNvme]::DeviceIoControl($h, [uint32]0x2D1400, $inBuf, [uint32]$bufSize,
                $outBuf, [uint32]$bufSize, [ref]$ret, [IntPtr]::Zero)
        [void][AfterlifeNvme]::CloseHandle($h)
        # A SATA disk answers the same IOCTL with failure or an empty payload rather
        # than an error, so both are treated as simply "not an NVMe drive".
        if (-not $ok -or $ret -lt 64) { continue }

        # ProtocolDataOffset is relative to STORAGE_PROTOCOL_SPECIFIC_DATA, which
        # starts 8 bytes into the descriptor -- hence 8 + offset, not the offset
        # alone. Reading it back from the response rather than hardcoding 56 keeps
        # this correct if a driver lays the buffer out differently.
        $p = 8 + [BitConverter]::ToUInt32($outBuf, 24)
        if ($p + 192 -gt $outBuf.Length) { continue }

        $tempK = [BitConverter]::ToUInt16($outBuf, $p + 1)
        # Counters are 128-bit little-endian; the low 64 bits cannot realistically
        # overflow on consumer hardware, so read the low half and skip BigInteger.
        $nvmeHealth += [ordered]@{
            drive_number        = $dn
            critical_warning    = $outBuf[$p]
            composite_temp_c    = if ($tempK -gt 0) { $tempK - 273 } else { $null }
            available_spare_pct = $outBuf[$p + 3]
            spare_threshold_pct = $outBuf[$p + 4]
            percentage_used     = $outBuf[$p + 5]
            data_units_read     = [BitConverter]::ToUInt64($outBuf, $p + 32)
            data_units_written  = [BitConverter]::ToUInt64($outBuf, $p + 48)
            power_cycles        = [BitConverter]::ToUInt64($outBuf, $p + 112)
            power_on_hours      = [BitConverter]::ToUInt64($outBuf, $p + 128)
            unsafe_shutdowns    = [BitConverter]::ToUInt64($outBuf, $p + 144)
            media_errors        = [BitConverter]::ToUInt64($outBuf, $p + 160)
            error_log_entries   = [BitConverter]::ToUInt64($outBuf, $p + 176)
        }
    }
} catch {
    # Add-Type unavailable (constrained language mode / locked-down host) or no
    # NVMe drive present -- an empty list, never a failed run.
}

# Legacy SATA SMART predictive-failure flag -- a second, older signal source (present
# on some drives StorageReliabilityCounter doesn't cover, e.g. some older SATA SSDs).
# A $true here is a drive telling Windows it expects to fail soon -- rare, but when
# present it's the single strongest fault signal this whole collector can produce.
$smartPredictFailure = Try-Get {
    Get-CimInstance -Namespace "root\wmi" -ClassName MSStorageDriver_FailurePredictStatus -ErrorAction Stop |
        Select-Object -First 1 | ForEach-Object { [bool]$_.PredictFailure }
}

# ---------- hardware error events ----------
# WHEA-Logger is Windows' own hardware-error-correction subsystem -- CPU cache/PCIe/
# memory errors the platform detected and (usually) corrected land here. Disk/Ntfs
# source errors are the OS complaining about the storage controller or filesystem.
# Kernel-Power event 41 is an unexpected shutdown (crash, power loss, or a hardware
# fault severe enough to kill the machine) -- distinct from a clean shutdown/restart.
# All three are read-only Event Log queries; no admin required to read the System log.
# 90-day window: long enough to catch an intermittent fault, short enough that a
# five-year-old one-off blip from a forgotten power outage doesn't read as "failing now".
function Count-RecentEvents {
    param([string]$LogName, [string]$ProviderName = $null, [int]$EventId = 0, [int]$Days = 90)
    try {
        $filter = @{ LogName = $LogName; StartTime = (Get-Date).AddDays(-$Days) }
        if ($ProviderName) { $filter.ProviderName = $ProviderName }
        if ($EventId -gt 0) { $filter.Id = $EventId }
        $events = Get-WinEvent -FilterHashtable $filter -ErrorAction Stop
        $arr = @($events)
        return [ordered]@{
            count      = $arr.Count
            last_seen  = if ($arr.Count -gt 0) { $arr[0].TimeCreated.ToString("s") } else { $null }
        }
    } catch {
        # Get-WinEvent throws for BOTH "nothing matched" and "could not read the
        # log", and conflating them is how a card ends up confidently announcing
        # "no hardware faults" on a machine whose event log was never readable.
        # The no-match case has a distinct message, so separate them: a genuine
        # empty result is 0, anything else is UNKNOWN and renders as "not read".
        if ($_.Exception.Message -like "*No events were found*" -or
            $_.Exception.Message -like "*did not match*") {
            return [ordered]@{ count = 0; last_seen = $null }
        }
        return [ordered]@{ count = $Unknown; last_seen = $null }
    }
}

# How far back the System log ACTUALLY reaches. Windows caps it (20 MB by
# default) and rolls old records out, so a "last 90 days" query silently becomes
# "last N days" wherever N is smaller -- on the dev machine the log held only 13
# days, and an event from 14 days earlier vanished between two scans hours apart.
# Reporting zero findings over a window the log never covered would be a claim the
# data cannot support, so the real window is captured and surfaced alongside.
$logWindowDays = Try-Get {
    $oldest = Get-WinEvent -LogName System -Oldest -MaxEvents 1 -ErrorAction Stop
    [math]::Round(((Get-Date) - $oldest.TimeCreated).TotalDays, 1)
}

$wheaErrors        = Count-RecentEvents -LogName "System" -ProviderName "Microsoft-Windows-WHEA-Logger"
$diskErrors        = Count-RecentEvents -LogName "System" -ProviderName "disk"
$ntfsErrors        = Count-RecentEvents -LogName "System" -ProviderName "Ntfs"
$unexpectedShutdowns = Count-RecentEvents -LogName "System" -ProviderName "Microsoft-Windows-Kernel-Power" -EventId 41
# Event ID 4101 = "the GPU stopped responding and was successfully recovered" (a TDR).
# Distinct from a WHEA-logged hardware fault -- this is a driver/GPU-load instability
# signal, common on aging or thermally-stressed GPUs even when the hardware itself
# never triggers a WHEA event.
$gpuTdrEvents      = Count-RecentEvents -LogName "System" -ProviderName "Display"

# BSOD crash dumps -- Windows drops one *.dmp per crash in this folder by default.
# A real, on-disk crash history independent of (and often longer-lived than) the
# System event log, which can roll over and lose old Kernel-Power/WHEA entries first.
$crashDumps = Try-Get {
    $dir = "$env:SystemRoot\Minidump"
    if (Test-Path $dir) {
        $files = Get-ChildItem $dir -Filter "*.dmp" -ErrorAction Stop
        [ordered]@{ count = $files.Count
                    last_seen = if ($files.Count -gt 0) { ($files | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime.ToString("s") } else { $null } }
    } else { [ordered]@{ count = 0; last_seen = $null } }
} ([ordered]@{ count = 0; last_seen = $null })

# ---------- Device Manager errors ----------
# ConfigManagerErrorCode != 0 is exactly what shows up as a yellow-bang / red-X in
# Device Manager -- a device Windows itself has flagged. Direct, unprivileged, real
# fault signal (not inferred from age) -- for genuine malfunctions. Code 22 ("this
# device is disabled") is deliberately excluded: Windows ships several virtual WAN
# Miniport adapters (L2TP/PPTP/IP/IPv6) pre-installed and disabled by default on
# essentially every machine, so unfiltered this field would flag nearly 100% of
# healthy Windows installs as having a hardware fault. A disabled device reflects a
# configuration choice, not a malfunction -- codes like 10 (can't start), 31 (not
# working), 43 (stopped due to a reported problem) are the ones worth surfacing.
$deviceErrors = @()
try {
    $deviceErrors = @(Get-CimInstance -ClassName Win32_PNPEntity -ErrorAction Stop |
        Where-Object { $_.ConfigManagerErrorCode -ne 0 -and $_.ConfigManagerErrorCode -ne 22 } |
        ForEach-Object { [ordered]@{ name = $_.Name; error_code = $_.ConfigManagerErrorCode } })
} catch { }

# ---------- reliability index ----------
# Windows' own Reliability Monitor score: a 1-10 rolling stability index that factors
# in app crashes, driver failures, OS failures and hardware-related events together.
# Cheap, unprivileged, and already exactly the kind of composite signal a trust score
# wants -- take the most recent day that has a real (non -1) index.
$reliabilityIndex = Try-Get {
    Get-CimInstance -ClassName Win32_ReliabilityStabilityMetrics -ErrorAction Stop |
        Where-Object { $_.SystemStabilityIndex -ge 0 } |
        Sort-Object TimeGenerated -Descending | Select-Object -First 1 |
        ForEach-Object { [math]::Round($_.SystemStabilityIndex, 1) }
}

# ---------- memory (per-stick) ----------
$memorySticks = @()
try {
    $memorySticks = @(Get-CimInstance -ClassName Win32_PhysicalMemory -ErrorAction Stop | ForEach-Object {
        [ordered]@{
            capacity_gb = [math]::Round($_.Capacity / 1GB, 1)
            speed_mhz   = $_.Speed
            manufacturer = $_.Manufacturer
            part_number  = if ($_.PartNumber) { $_.PartNumber.Trim() } else { $null }
        }
    })
} catch { }

# ---------- fans ----------
# Win32_Fan is almost never populated on consumer laptops (OEMs hide fan control
# behind vendor ACPI/EC methods this generic class can't reach) -- worth trying
# anyway since it costs nothing and some desktops/workstations do expose it.
$fans = @()
try {
    $fans = @(Get-CimInstance -ClassName Win32_Fan -ErrorAction Stop | ForEach-Object {
        [ordered]@{ name = $_.Name; status = $_.Status; rpm = $_.DesiredSpeed }
    })
} catch { }

# ---------- thermal ----------
# Deliberately NOT collecting MSAcpi_ThermalZoneTemperature: tested on this machine
# and it returned 95.1C, which is implausible as a live reading (that's throttle/
# shutdown territory, contradicted by every other signal here -- 0% disk wear, no
# WHEA errors, no unexpected shutdowns beyond the one already logged). This is a
# known ACPI quirk: many OEM firmwares wire CurrentTemperature to a static critical
# trip point rather than a live sample, so the field looks legitimate (a plausible-
# looking number) while actually being meaningless -- worse than an honest UNKNOWN,
# since nothing marks it as untrustworthy. disk_reliability's per-drive temperature
# (real SMART data, already collected above) is the trustworthy thermal signal here.

# ---------- battery wear ----------
# root\wmi battery classes are elevation-gated on most builds. Fall back to
# Win32_Battery (unprivileged) to at least establish presence.
$batteryPresent = $Unknown
$batteryHealthPct = $Unknown
$batteryDetail = $null

$batBasic = Try-Get { Get-CimInstance -ClassName Win32_Battery -ErrorAction Stop | Select-Object -First 1 }
if ($batBasic) { $batteryPresent = $true }

try {
    $batStatic = Get-CimInstance -Namespace "root\wmi" -ClassName BatteryStaticData -ErrorAction Stop | Select-Object -First 1
    $batFull   = Get-CimInstance -Namespace "root\wmi" -ClassName BatteryFullChargedCapacity -ErrorAction Stop | Select-Object -First 1
    if ($batStatic -and $batFull -and $batStatic.DesignedCapacity -gt 0) {
        $batteryPresent = $true
        $batteryHealthPct = [math]::Round(100.0 * $batFull.FullChargedCapacity / $batStatic.DesignedCapacity, 1)
        $batteryDetail = [ordered]@{
            designed_capacity_mwh = [int]$batStatic.DesignedCapacity
            full_charge_mwh       = [int]$batFull.FullChargedCapacity
        }
    } elseif (-not $batBasic) {
        $batteryPresent = $false
        $batteryHealthPct = $null
    }
} catch {
    # health stays UNKNOWN; presence keeps whatever Win32_Battery told us
}

# Cycle count is the other half of "how worn is this battery" alongside capacity --
# two batteries at the same health % can have very different cycle counts (fast
# degraders vs. genuinely old-but-gentle use). Same admin-gated root\wmi namespace
# as the capacity classes above, so it fails the same way on the same OEMs.
$batteryCycleCount = Try-Get {
    (Get-CimInstance -Namespace "root\wmi" -ClassName BatteryCycleCount -ErrorAction Stop |
        Select-Object -First 1).CycleCount
}

# Many OEMs (incl. HP) do not populate the root\wmi battery classes. powercfg reads
# design vs full-charge capacity from a different source and works without admin.
if ($batteryHealthPct -eq $Unknown -or $null -eq $batteryHealthPct) {
    try {
        $rpt = Join-Path $env:TEMP ("afl_batt_{0}.xml" -f $PID)
        $null = & powercfg /batteryreport /output $rpt /xml 2>$null
        if (Test-Path $rpt) {
            [xml]$bx = Get-Content $rpt -Raw
            $bat = $bx.BatteryReport.Batteries.Battery | Select-Object -First 1
            $design = [double]$bat.DesignCapacity
            $full   = [double]$bat.FullChargeCapacity
            if ($design -gt 0 -and $full -gt 0) {
                $batteryPresent = $true
                $batteryHealthPct = [math]::Round(100.0 * $full / $design, 1)
                $batteryDetail = [ordered]@{
                    designed_capacity_mwh = [int]$design
                    full_charge_mwh       = [int]$full
                    source                = "powercfg"
                }
            }
            Remove-Item $rpt -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # powercfg unavailable (e.g. desktop with no battery) - stays as-is
    }
}

# ---------- installed browser versions (app-layer CVE surface) ----------
# One pass over the uninstall keys for both browsers, via the .NET registry API.
# This was two separate Get-ItemProperty wildcard enumerations -- each one
# materialising every value of every uninstall key, then discarding all but one
# property, and doing it twice over the identical key set. Measured at 3.9 s for
# two version strings; this reads the same two values in tens of milliseconds.
$chromeVer = $null
$edgeVer   = $null
try {
    $unKey = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey(
        'SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall')
    if ($unKey) {
        try {
            foreach ($sub in $unKey.GetSubKeyNames()) {
                if ($chromeVer -and $edgeVer) { break }
                $k = $unKey.OpenSubKey($sub)
                if (-not $k) { continue }
                try {
                    $name = [string]$k.GetValue('DisplayName')
                    if (-not $name) { continue }
                    if (-not $chromeVer -and $name -like 'Google Chrome*') { $chromeVer = [string]$k.GetValue('DisplayVersion') }
                    elseif (-not $edgeVer -and $name -like 'Microsoft Edge*') { $edgeVer = [string]$k.GetValue('DisplayVersion') }
                } finally { $k.Close() }
            }
        } finally { $unKey.Close() }
    }
} catch {}

# ---------- usage-persona signals ----------
# Only categorized matches + counts are kept, never the full installed-program
# list -- this reveals "which category of tool you have", not "here's a full
# inventory of your machine". Same registry read used for the browser-version
# check above, just matched against a broader curated keyword list.
$GamerKeywords  = @("Steam","Epic Games Launcher","Battle.net","GOG Galaxy","Riot Client","Ubisoft Connect","EA app","EA Desktop","Origin")
$CoderKeywords  = @("Visual Studio Code","Visual Studio ","PyCharm","IntelliJ IDEA","WebStorm","Android Studio","Docker Desktop","GitHub Desktop","Git version","Node.js","Python 3","Sublime Text","Postman","Windows Terminal")
$EditorKeywords = @("Adobe Premiere Pro","Adobe After Effects","Adobe Photoshop","Adobe Lightroom","Adobe Illustrator","DaVinci Resolve","Blender","Audacity","OBS Studio","Cinema 4D","Autodesk Maya")

$installedNames = @()
foreach ($path in @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
)) {
    $installedNames += Try-Get {
        Get-ItemProperty -Path $path -ErrorAction Stop |
            Where-Object { $_.DisplayName } | Select-Object -ExpandProperty DisplayName
    } @()
}
$installedNames = $installedNames | Select-Object -Unique

function Match-Keywords($names, $keywords) {
    $hits = @()
    foreach ($kw in $keywords) {
        if ($names | Where-Object { $_ -like "*$($kw.Trim())*" } | Select-Object -First 1) { $hits += $kw.Trim() }
    }
    # Comma-prefix: PowerShell unrolls a 0- or 1-item array on function return
    # by default, which ConvertTo-Json then serializes as a bare value instead
    # of a list -- breaking any consumer that expects an array, always.
    return ,$hits
}

$gamerHits  = Match-Keywords $installedNames $GamerKeywords
$coderHits  = Match-Keywords $installedNames $CoderKeywords
$editorHits = Match-Keywords $installedNames $EditorKeywords

# Installed Steam game count (one appmanifest_*.acf per game) -- a real
# magnitude signal, not just "Steam happens to be installed".
$steamGameCount = 0
try {
    $steamPath = Try-Get { (Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam" -ErrorAction Stop).InstallPath }
    if (-not $steamPath) { $steamPath = Try-Get { (Get-ItemProperty "HKLM:\SOFTWARE\Valve\Steam" -ErrorAction Stop).InstallPath } }
    if ($steamPath -and (Test-Path "$steamPath\steamapps")) {
        $steamGameCount = (Get-ChildItem "$steamPath\steamapps" -Filter "appmanifest_*.acf" -ErrorAction SilentlyContinue | Measure-Object).Count
    }
} catch {}

# WSL distro count -- "lots of idles and servers" signal for a coder persona.
$wslDistroCount = Try-Get {
    (Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss" -ErrorAction Stop | Measure-Object).Count
} 0

# ---------- factory-fresh indicators (wipe verification) ----------
# Answers one question: does this machine look like it has just come out of
# "Reset this PC - remove everything"? That is a far weaker claim than forensic
# erasure verification, and the app says so in those words -- we are not
# recovering deleted sectors, we are checking that the obvious traces of a
# previous owner are gone.
#
# Every field here is a COUNT. No filename, no account name, no network name and
# no application name is read, transmitted or stored -- which matters more here
# than anywhere else in this script, because this is the one section that looks
# at personal directories at all. A count answers "is this clean?" completely; a
# list would answer it no better and would be a genuine privacy problem.
$cleanState = Try-Get {
    $sysProfiles = @('Public','Default','Default User','All Users','defaultuser0','WDAGUtilityAccount')
    $profiles = @(Get-ChildItem "$env:SystemDrive\Users" -Directory -Force -ErrorAction Stop |
                  Where-Object { $sysProfiles -notcontains $_.Name })

    # Documents / Desktop / Downloads / Pictures across every real profile, counted
    # only -- and deliberately NOT counted to completion.
    #
    # The question is "are there more than a handful of files here", not "how many
    # exactly". Counting to completion on a machine in daily use meant recursing a
    # full Pictures library: measured at 10.5 SECONDS for 41,662 files on an
    # ordinary laptop, and unbounded on a worse one -- all of it spent computing a
    # precise number that gets compared against a threshold of 12 and thrown away.
    # Stopping at the cap answers the same question in ~120 ms. Select-Object -First
    # halts the upstream pipeline rather than filtering after the fact, so the
    # enumeration genuinely stops instead of just discarding the rest.
    $fileCap = 30
    $userFiles = 0
    foreach ($p in $profiles) {
        foreach ($sub in @('Desktop','Documents','Downloads','Pictures')) {
            if ($userFiles -ge $fileCap) { break }
            $dir = Join-Path $p.FullName $sub
            if (Test-Path $dir) {
                # -Force so hidden files still count; desktop.ini is excluded because
                # Windows itself creates it in a freshly-reset profile, so counting it
                # would report every clean machine as still holding user data.
                $userFiles += @(Get-ChildItem $dir -Force -Recurse -File -ErrorAction SilentlyContinue |
                                Where-Object { $_.Name -ne 'desktop.ini' } |
                                Select-Object -First ($fileCap - $userFiles)).Count
            }
        }
        if ($userFiles -ge $fileCap) { break }
    }

    $wifiCount = $null
    try {
        $wifiCount = @(netsh wlan show profiles 2>$null | Select-String 'All User Profile').Count
    } catch {}

    # Store apps are ignored -- Windows reinstalls a pile of them on first boot, so
    # they are noise. Only classic installed programs are counted.
    #
    # Uses the .NET registry API rather than Get-ItemProperty on a wildcard path.
    # Get-ItemProperty materialises every value of every uninstall key as a
    # PSObject just so two of them can be read: measured at 836 ms warm (2.6 s
    # cold) against 37 ms here, for an identical count.
    $installed = Try-Get {
        $n = 0
        foreach ($root in @('SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                            'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')) {
            $key = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey($root)
            if (-not $key) { continue }
            try {
                foreach ($sub in $key.GetSubKeyNames()) {
                    $k = $key.OpenSubKey($sub)
                    if (-not $k) { continue }
                    try {
                        if ($k.GetValue('DisplayName') -and -not $k.GetValue('SystemComponent')) { $n++ }
                    } finally { $k.Close() }
                }
            } finally { $key.Close() }
        }
        $n
    }

    $installDate = if ($os -and $os.InstallDate) { $os.InstallDate } else { $null }

    [ordered]@{
        checked          = $true
        user_profiles    = $profiles.Count
        user_files       = $userFiles
        # True when counting stopped at the cap, so the UI can say "30+" instead of
        # reporting a bounded count as if it were the real total.
        user_files_capped = ($userFiles -ge $fileCap)
        wifi_profiles    = $wifiCount
        installed_apps   = $installed
        os_install_date  = if ($installDate) { $installDate.ToString("s") } else { $null }
        os_install_days  = if ($installDate) { [math]::Round(((Get-Date) - $installDate).TotalDays, 1) } else { $null }
    }
} ([ordered]@{ checked = $false })

# ---------- tpm: read the job started at the top ----------
# Read here, at the very end, rather than where the TPM section used to sit.
# The values are only ever used in the payload below, so waiting for them
# early threw away most of the point of starting the job first: it was being
# collected about two seconds in and still blocking for three. Read last, the
# job overlaps the entire rest of the script and the wait is normally zero.
# Three outcomes, deliberately distinguished:
#   present -> present
#   absent  -> genuinely absent
#   ok=false or no result -> UNKNOWN (almost always access denied without elevation)
$tpmPresent = $Unknown
$tpmSpec = $Unknown
$tpmEnabled = $Unknown
if ($tpmJob) {
    try {
        # Generous backstop only. This has normally finished long before now; the
        # timeout exists so a wedged WMI provider cannot hang an entire scan.
        if (Wait-Job $tpmJob -Timeout 25) {
            $r = Receive-Job $tpmJob -ErrorAction SilentlyContinue
            if ($r -and $r.ok) {
                $tpmPresent = $r.present
                $tpmSpec    = if ($r.present) { $r.spec } else { $null }
                $tpmEnabled = if ($r.present) { $r.enabled } else { $false }
            }
        }
    } catch {
    } finally {
        Remove-Job $tpmJob -Force -ErrorAction SilentlyContinue
    }
}

$ageYears = $null
if ($bios -and $bios.ReleaseDate) {
    $ageYears = [math]::Round(((Get-Date) - $bios.ReleaseDate).TotalDays / 365.25, 1)
}

$result = [ordered]@{
    collected_at      = (Get-Date).ToString("s")
    manufacturer      = if ($cs) { $cs.Manufacturer } else { $null }
    model             = if ($cs) { $cs.Model } else { $null }
    system_family     = $systemFamily
    bios_release_date = if ($bios -and $bios.ReleaseDate) { $bios.ReleaseDate.ToString("yyyy-MM-dd") } else { $null }
    approx_age_years  = $ageYears

    os_caption        = if ($os) { $os.Caption } else { $null }
    os_version        = if ($os) { $os.Version } else { $null }
    os_build          = if ($os) { $os.BuildNumber } else { $null }
    os_release_id     = $releaseId
    os_architecture   = if ($os) { $os.OSArchitecture } else { $null }

    cpu_name          = if ($cpu) { $cpu.Name.Trim() } else { $null }
    cpu_manufacturer  = if ($cpu) { $cpu.Manufacturer } else { $null }
    cpu_cores         = if ($cpu) { $cpu.NumberOfCores } else { $null }
    cpu_logical       = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $null }
    cpu_max_mhz       = if ($cpu) { $cpu.MaxClockSpeed } else { $null }
    cpu_address_width = if ($cpu) { $cpu.AddressWidth } else { $null }

    gpu_name          = if ($gpu) { $gpu.Name } else { $null }

    collected_elevated = $isElevated
    tpm_present       = $tpmPresent
    tpm_spec_version  = $tpmSpec
    tpm_enabled       = $tpmEnabled

    uefi              = $isUefi
    secure_boot_on    = if ($null -ne $secureBootEnabled) { [bool]$secureBootEnabled } else { $null }
    secure_boot_certs = $sbCerts
    mitigation_state  = $mitigationState

    ram_gb            = if ($cs) { [math]::Round($cs.TotalPhysicalMemory / 1GB, 1) } else { $null }
    sysdrive_total_gb = if ($sysDrive) { [math]::Round($sysDrive.Size / 1GB, 1) } else { $null }
    sysdrive_free_gb  = if ($sysDrive) { [math]::Round($sysDrive.FreeSpace / 1GB, 1) } else { $null }
    disk_media_type   = if ($physical) { [string]$physical.MediaType } else { $null }
    disk_health       = if ($physical) { [string]$physical.HealthStatus } else { $null }
    disk_reliability  = $reliability
    nvme_health       = @($nvmeHealth)
    smart_predict_failure = $smartPredictFailure

    hardware_errors   = [ordered]@{
        whea_90d                = $wheaErrors
        disk_90d                = $diskErrors
        ntfs_90d                 = $ntfsErrors
        unexpected_shutdowns_90d = $unexpectedShutdowns
        gpu_tdr_90d              = $gpuTdrEvents
        log_window_days          = $logWindowDays
    }
    crash_dumps       = $crashDumps
    device_errors     = $deviceErrors
    reliability_index = $reliabilityIndex
    fans              = $fans

    memory_sticks     = $memorySticks

    battery_present     = $batteryPresent
    battery_health_pct  = $batteryHealthPct
    battery_cycle_count = $batteryCycleCount
    battery_detail      = $batteryDetail

    chrome_version    = $chromeVer
    edge_version      = $edgeVer

    clean_state       = $cleanState

    persona_signals   = [ordered]@{
        gamer_matches    = $gamerHits
        coder_matches    = $coderHits
        editor_matches   = $editorHits
        steam_game_count = $steamGameCount
        wsl_distro_count = $wslDistroCount
    }
}

$json = $result | ConvertTo-Json -Depth 5 -Compress

if ($PostUrl) {
    # Deep-scan handshake: deliver straight to the web app, no manual file handling.
    $target = if ($Token) { "$PostUrl/$Token" } else { $PostUrl }
    try {
        # Generous timeout: the backend may be asleep (free-tier cold start) and take
        # a while to wake up before it even starts processing this request.
        $resp = Invoke-RestMethod -Uri $target -Method Post -Body $json -ContentType "application/json" -TimeoutSec 90
        Write-Host "`n  Delivered to Afterlife. Device: $($resp.device_id)" -ForegroundColor Green
        Write-Host "  Return to the browser tab - your verified passport is ready." -ForegroundColor Green
    } catch {
        Write-Host "  Could not reach $target. Is the app running? $_" -ForegroundColor Red
    }
}
elseif ($Pretty) { $result | ConvertTo-Json -Depth 5 }
else { $json }
