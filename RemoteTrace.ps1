# RemoteTrace v1.0.0
# Remote tcpdump to Wireshark — Windows PowerShell
# Uses built-in OpenSSH (ssh.exe, ships with Windows 10 1803+)
# No plink, no sshpass, no extra dependencies.

#Requires -Version 5.1

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$VERSION = "1.0.0"

# ---------- GUI ----------

function Show-ConfigForm {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "RemoteTrace v$VERSION"
    $form.Size = New-Object System.Drawing.Size(520, 660)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    $y  = 20
    $lw = 145   # label width
    $iw = 310   # input width
    $sp = 34    # row spacing

    function Add-Row {
        param([string]$Label, [string]$Default, [switch]$Password, [switch]$ReadOnly)
        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Location = New-Object System.Drawing.Point(15, $script:y)
        $lbl.Size = New-Object System.Drawing.Size($lw, 20)
        $lbl.Text = $Label
        $form.Controls.Add($lbl)

        $txt = New-Object System.Windows.Forms.TextBox
        $txt.Location = New-Object System.Drawing.Point(165, $script:y)
        $txt.Size = New-Object System.Drawing.Size($iw, 20)
        $txt.Text = $Default
        if ($Password)  { $txt.PasswordChar = '*' }
        if ($ReadOnly)  { $txt.ReadOnly = $true; $txt.BackColor = [System.Drawing.SystemColors]::Control }
        $form.Controls.Add($txt)

        $script:y += $sp
        return @{ Label = $lbl; Input = $txt }
    }

    # Connection mode
    $modeLbl = New-Object System.Windows.Forms.Label
    $modeLbl.Location = New-Object System.Drawing.Point(15, $y)
    $modeLbl.Size = New-Object System.Drawing.Size($lw, 20)
    $modeLbl.Text = 'Connection Mode:'
    $form.Controls.Add($modeLbl)
    $modeCombo = New-Object System.Windows.Forms.ComboBox
    $modeCombo.Location = New-Object System.Drawing.Point(165, $y)
    $modeCombo.Size = New-Object System.Drawing.Size($iw, 20)
    $modeCombo.DropDownStyle = 'DropDownList'
    $modeCombo.Items.AddRange(@('Jump Server + Auto-Discovery', 'Jump Server + Manual Target', 'Direct Connection'))
    $modeCombo.SelectedIndex = 0
    $form.Controls.Add($modeCombo)
    $y += $sp

    $jumpHostRow   = Add-Row 'Jump Host:'       '***REMOVED***'
    $jumpUserRow   = Add-Row 'Jump User:'       'jteeuwen'
    $jumpPassRow   = Add-Row 'Jump Password:'   '' -Password
    $targetNameRow = Add-Row 'Target Name:'     'demo'
    $targetHostRow = Add-Row 'Target Host:'     '(auto-discovered)' -ReadOnly
    $targetUserRow = Add-Row 'Target User:'     'root'
    $targetPassRow = Add-Row 'Target Password:' '(auto-discovered)' -Password -ReadOnly
    $targetPortRow = Add-Row 'Target Port:'     '22'
    $ifaceRow      = Add-Row 'Interface:'       'eth0'
    $filterRow     = Add-Row 'Capture Filter:'  'icmp'
    $snapRow       = Add-Row 'Snap Length:'     '0'

    # Sudo checkbox
    $sudoLbl = New-Object System.Windows.Forms.Label
    $sudoLbl.Location = New-Object System.Drawing.Point(15, $y)
    $sudoLbl.Size = New-Object System.Drawing.Size($lw, 20)
    $sudoLbl.Text = 'Use Sudo:'
    $form.Controls.Add($sudoLbl)
    $sudoBox = New-Object System.Windows.Forms.CheckBox
    $sudoBox.Location = New-Object System.Drawing.Point(165, $y)
    $sudoBox.Size = New-Object System.Drawing.Size(20, 20)
    $sudoBox.Checked = $false
    $form.Controls.Add($sudoBox)
    $sudoHint = New-Object System.Windows.Forms.Label
    $sudoHint.Location = New-Object System.Drawing.Point(190, $y)
    $sudoHint.Size = New-Object System.Drawing.Size(290, 20)
    $sudoHint.Text = '(if tcpdump requires sudo on target)'
    $sudoHint.ForeColor = [System.Drawing.Color]::Gray
    $form.Controls.Add($sudoHint)
    $y += $sp

    $wsRow = Add-Row 'Wireshark Path:' 'C:\Program Files\Wireshark\Wireshark.exe'

    # Buttons
    $y += 10
    $okBtn = New-Object System.Windows.Forms.Button
    $okBtn.Location = New-Object System.Drawing.Point(315, $y)
    $okBtn.Size = New-Object System.Drawing.Size(75, 25)
    $okBtn.Text = 'Start'
    $okBtn.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $okBtn
    $form.Controls.Add($okBtn)

    $cancelBtn = New-Object System.Windows.Forms.Button
    $cancelBtn.Location = New-Object System.Drawing.Point(400, $y)
    $cancelBtn.Size = New-Object System.Drawing.Size(75, 25)
    $cancelBtn.Text = 'Cancel'
    $cancelBtn.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancelBtn
    $form.Controls.Add($cancelBtn)

    # Dynamic field visibility
    $UpdateVisibility = {
        $mode   = $modeCombo.SelectedItem
        $isJump = $mode -ne 'Direct Connection'
        $isAuto = $mode -eq 'Jump Server + Auto-Discovery'

        foreach ($row in @($jumpHostRow, $jumpUserRow, $jumpPassRow)) {
            $row.Label.Visible = $isJump
            $row.Input.Visible = $isJump
        }
        $targetNameRow.Label.Visible = $isAuto
        $targetNameRow.Input.Visible = $isAuto

        if ($isAuto) {
            $targetHostRow.Input.Text      = '(auto-discovered)'
            $targetHostRow.Input.ReadOnly  = $true
            $targetHostRow.Input.BackColor = [System.Drawing.SystemColors]::Control
            $targetPassRow.Input.Text      = '(auto-discovered)'
            $targetPassRow.Input.ReadOnly  = $true
            $targetPassRow.Input.BackColor = [System.Drawing.SystemColors]::Control
        } else {
            $targetHostRow.Input.Text      = '192.168.1.100'
            $targetHostRow.Input.ReadOnly  = $false
            $targetHostRow.Input.BackColor = [System.Drawing.SystemColors]::Window
            $targetPassRow.Input.Text      = ''
            $targetPassRow.Input.ReadOnly  = $false
            $targetPassRow.Input.BackColor = [System.Drawing.SystemColors]::Window
        }
    }
    $modeCombo.add_SelectedIndexChanged($UpdateVisibility)
    & $UpdateVisibility

    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return $null }

    return @{
        Mode           = $modeCombo.SelectedItem
        JumpHost       = $jumpHostRow.Input.Text
        JumpUser       = $jumpUserRow.Input.Text
        JumpPassword   = $jumpPassRow.Input.Text
        TargetName     = $targetNameRow.Input.Text
        TargetHost     = $targetHostRow.Input.Text
        TargetUser     = $targetUserRow.Input.Text
        TargetPassword = $targetPassRow.Input.Text
        TargetPort     = $targetPortRow.Input.Text
        Interface      = $ifaceRow.Input.Text
        Filter         = $filterRow.Input.Text
        SnapLength     = $snapRow.Input.Text
        UseSudo        = $sudoBox.Checked
        WiresharkPath  = $wsRow.Input.Text
    }
}

# ---------- Helpers ----------

function Find-Ssh {
    $candidates = @(
        "$env:SystemRoot\System32\OpenSSH\ssh.exe",
        "$env:ProgramFiles\OpenSSH\ssh.exe",
        "$env:ProgramFiles\OpenSSH-Win64\ssh.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    $inPath = Get-Command ssh -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }
    return $null
}

function Find-Wireshark {
    param([string]$Hint)
    foreach ($c in @(
        $Hint,
        "C:\Program Files\Wireshark\Wireshark.exe",
        "C:\Program Files (x86)\Wireshark\Wireshark.exe",
        "$env:ProgramFiles\Wireshark\Wireshark.exe",
        "${env:ProgramFiles(x86)}\Wireshark\Wireshark.exe"
    )) {
        if ($c -and (Test-Path $c -PathType Leaf)) { return $c }
    }
    return $null
}

# Escape a string for safe embedding inside a remote double-quoted shell argument.
# Escapes: backslash, double-quote, dollar, backtick.
function ConvertTo-RemoteEscaped {
    param([string]$Value)
    $Value = $Value -replace '\\',  '\\'
    $Value = $Value -replace '"',   '\"'
    $Value = $Value -replace '\$',  '\$'
    $Value = $Value -replace '`',   '\`'
    return $Value
}

function Build-TcpdumpCommand {
    param([string]$Interface, [string]$Filter, [string]$SnapLength, [bool]$UseSudo)
    $ei   = ConvertTo-RemoteEscaped $Interface
    $ef   = ConvertTo-RemoteEscaped $Filter
    $sudo = if ($UseSudo) { 'sudo ' } else { '' }
    return "${sudo}tcpdump -i `"$ei`" -U -s $SnapLength -w - -- `"$ef`""
}

# Write a temporary SSH_ASKPASS helper script and set the required env vars.
# Returns the temp file path so the caller can clean it up.
function Set-SshAskPass {
    param([string]$Password)
    $path = Join-Path $env:TEMP "rt_askpass_$PID.cmd"
    "@echo off`r`necho $Password" | Set-Content $path -Encoding ASCII
    $env:SSH_ASKPASS         = $path
    $env:SSH_ASKPASS_REQUIRE = 'force'
    $env:DISPLAY             = 'dummy'
    return $path
}

function Remove-SshAskPass {
    param([string]$Path)
    Remove-Item $Path -ErrorAction SilentlyContinue
    Remove-Item env:SSH_ASKPASS         -ErrorAction SilentlyContinue
    Remove-Item env:SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue
    Remove-Item env:DISPLAY             -ErrorAction SilentlyContinue
}

# Run auto-discovery 'f' script on jump host, return @{IP; Password}.
function Get-TargetDetails {
    param([string]$SshExe, [string[]]$SshOpts,
          [string]$JumpUser, [string]$JumpPassword,
          [string]$JumpHost, [string]$TargetName)

    Write-Host "Discovering '$TargetName' via jump host..." -ForegroundColor Yellow

    $askpass = Set-SshAskPass -Password $JumpPassword
    try {
        $sshArgs = $SshOpts + @("$JumpUser@$JumpHost", "f $(ConvertTo-RemoteEscaped $TargetName) all 2>/dev/null")
        $output  = & $SshExe @sshArgs 2>$null
    } finally {
        Remove-SshAskPass -Path $askpass
    }

    $clean = $output -replace '\x1b\[[0-9;]*[a-zA-Z]', ''
    $ip    = ($clean | Where-Object { $_ -match 'ssh_ip\s*:\s*(.+)' }     | Select-Object -First 1) -replace '.*:\s*','' -replace '[^\d\.]',''
    $pwd   = ($clean | Where-Object { $_ -match 'access_pwd\s*:\s*(.+)' } | Select-Object -First 1) -replace '.*access_pwd\s*:\s*','' -replace '\s*$',''

    if (-not $ip -or -not $pwd) {
        Write-Host "Raw output:" -ForegroundColor Yellow
        $clean | ForEach-Object { Write-Host "  $_" }
        throw "Could not parse ssh_ip or access_pwd from 'f' script output."
    }

    Write-Host "Target IP: $ip" -ForegroundColor Green
    return @{ IP = $ip; Password = $pwd }
}

# Binary-safe capture: wires ssh.exe stdout directly to Wireshark stdin
# using System.Diagnostics.Process raw streams — bypasses PowerShell's
# text-mode pipeline and cmd.exe entirely.
function Start-Capture {
    param([string]$SshExe, [string[]]$SshArgs, [string]$WiresharkPath)

    Write-Host "Starting capture — press Ctrl+C or close Wireshark to stop." -ForegroundColor Yellow

    # Build argument string (quote args that contain spaces)
    $argStr = ($SshArgs | ForEach-Object {
        if ($_ -match '\s') { "`"$_`"" } else { $_ }
    }) -join ' '

    $sshProc = New-Object System.Diagnostics.Process
    $sshProc.StartInfo.FileName               = $SshExe
    $sshProc.StartInfo.Arguments              = $argStr
    $sshProc.StartInfo.UseShellExecute        = $false
    $sshProc.StartInfo.RedirectStandardOutput = $true
    $sshProc.StartInfo.RedirectStandardError  = $false
    $sshProc.StartInfo.CreateNoWindow         = $true

    $wsProc = New-Object System.Diagnostics.Process
    $wsProc.StartInfo.FileName              = $WiresharkPath
    $wsProc.StartInfo.Arguments             = '-k -i -'
    $wsProc.StartInfo.UseShellExecute       = $false
    $wsProc.StartInfo.RedirectStandardInput = $true
    $wsProc.StartInfo.CreateNoWindow        = $false

    $sshProc.Start() | Out-Null
    $wsProc.Start()  | Out-Null

    $sshStream = $sshProc.StandardOutput.BaseStream
    $wsStream  = $wsProc.StandardInput.BaseStream
    $buf       = New-Object byte[] 65536

    try {
        while ($true) {
            $n = $sshStream.Read($buf, 0, $buf.Length)
            if ($n -le 0) { break }
            $wsStream.Write($buf, 0, $n)
            $wsStream.Flush()
        }
    } catch {
        # Stream closed — normal shutdown path
    } finally {
        try { $wsStream.Close()  } catch {}
        try { $sshProc.Kill()    } catch {}
        try { $wsProc.WaitForExit(3000) } catch {}
    }
}

# ---------- Main ----------

$cfg = Show-ConfigForm
if (-not $cfg) { Write-Host "Cancelled." -ForegroundColor Yellow; exit }

$sshExe = Find-Ssh
if (-not $sshExe) {
    [System.Windows.Forms.MessageBox]::Show(
        "ssh.exe not found.`n`nOpenSSH ships with Windows 10 (1803+) and Windows 11.`n" +
        "Enable via: Settings -> Apps -> Optional Features -> OpenSSH Client",
        "RemoteTrace — Missing ssh.exe",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
Write-Host "SSH:       $sshExe"  -ForegroundColor Gray

$wsPath = Find-Wireshark -Hint $cfg.WiresharkPath
if (-not $wsPath) {
    [System.Windows.Forms.MessageBox]::Show(
        "Wireshark not found.`n`nDownload from https://www.wireshark.org/`nor update the path in the form.",
        "RemoteTrace — Missing Wireshark",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
Write-Host "Wireshark: $wsPath" -ForegroundColor Gray

$sshOpts    = @('-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10', '-o', 'LogLevel=ERROR')
$tcpdumpCmd = Build-TcpdumpCommand -Interface $cfg.Interface -Filter $cfg.Filter `
                                   -SnapLength $cfg.SnapLength -UseSudo $cfg.UseSudo

Write-Host ""
Write-Host "=== RemoteTrace v$VERSION ===" -ForegroundColor Green
Write-Host "Mode:      $($cfg.Mode)"       -ForegroundColor Cyan
Write-Host "Interface: $($cfg.Interface)"  -ForegroundColor Cyan
Write-Host "Filter:    $($cfg.Filter)"     -ForegroundColor Cyan
Write-Host ""

try {
    switch ($cfg.Mode) {

        'Direct Connection' {
            $sshArgs = $sshOpts + @('-p', $cfg.TargetPort, "$($cfg.TargetUser)@$($cfg.TargetHost)", $tcpdumpCmd)
            $askpass = $null
            if ($cfg.TargetPassword) {
                $askpass = Set-SshAskPass -Password $cfg.TargetPassword
            }
            try   { Start-Capture -SshExe $sshExe -SshArgs $sshArgs -WiresharkPath $wsPath }
            finally { if ($askpass) { Remove-SshAskPass -Path $askpass } }
        }

        'Jump Server + Manual Target' {
            $sshArgs = $sshOpts + @(
                '-J', "$($cfg.JumpUser)@$($cfg.JumpHost)",
                '-p', $cfg.TargetPort,
                "$($cfg.TargetUser)@$($cfg.TargetHost)",
                $tcpdumpCmd
            )
            $askpass = Set-SshAskPass -Password $cfg.JumpPassword
            try   { Start-Capture -SshExe $sshExe -SshArgs $sshArgs -WiresharkPath $wsPath }
            finally { Remove-SshAskPass -Path $askpass }
        }

        'Jump Server + Auto-Discovery' {
            $details = Get-TargetDetails -SshExe $sshExe -SshOpts $sshOpts `
                -JumpUser $cfg.JumpUser -JumpPassword $cfg.JumpPassword `
                -JumpHost $cfg.JumpHost -TargetName $cfg.TargetName

            $sshArgs = $sshOpts + @(
                '-J', "$($cfg.JumpUser)@$($cfg.JumpHost)",
                '-p', '22',
                "root@$($details.IP)",
                $tcpdumpCmd
            )
            $askpass = Set-SshAskPass -Password $cfg.JumpPassword
            try   { Start-Capture -SshExe $sshExe -SshArgs $sshArgs -WiresharkPath $wsPath }
            finally { Remove-SshAskPass -Path $askpass }
        }
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "Capture session ended." -ForegroundColor Green
