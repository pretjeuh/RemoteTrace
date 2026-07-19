# RemoteTrace v2.0.0
# Remote tcpdump to Wireshark -- Windows PowerShell
# Uses built-in OpenSSH (ssh.exe, ships with Windows 10 1803+)
# No plink, no sshpass, no extra dependencies.

#Requires -Version 5.1

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$VERSION = "2.2.2"

# ---------- GUI ----------

function Show-ConfigForm {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "RemoteTrace v$VERSION"
    $form.Size = New-Object System.Drawing.Size(560, 760)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    $y  = 20
    $lw = 155
    $iw = 300
    $sp = 34

    function Add-Row {
        param([string]$Label, [string]$Default, [switch]$Password, [switch]$ReadOnly)
        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Location = New-Object System.Drawing.Point(15, $script:y)
        $lbl.Size = New-Object System.Drawing.Size($lw, 20)
        $lbl.Text = $Label
        $form.Controls.Add($lbl)

        $txt = New-Object System.Windows.Forms.TextBox
        $txt.Location = New-Object System.Drawing.Point(175, $script:y)
        $txt.Size = New-Object System.Drawing.Size($iw, 20)
        $txt.Text = $Default
        if ($Password) { $txt.PasswordChar = '*' }
        if ($ReadOnly) { $txt.ReadOnly = $true; $txt.BackColor = [System.Drawing.SystemColors]::Control }
        $form.Controls.Add($txt)

        $script:y += $sp
        return @{ Label = $lbl; Input = $txt }
    }

    function Add-ComboRow {
        param([string]$Label, [string[]]$Items)
        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Location = New-Object System.Drawing.Point(15, $script:y)
        $lbl.Size = New-Object System.Drawing.Size($lw, 20)
        $lbl.Text = $Label
        $form.Controls.Add($lbl)

        $cb = New-Object System.Windows.Forms.ComboBox
        $cb.Location = New-Object System.Drawing.Point(175, $script:y)
        $cb.Size = New-Object System.Drawing.Size($iw, 20)
        $cb.DropDownStyle = 'DropDownList'
        $cb.Items.AddRange($Items)
        $cb.SelectedIndex = 0
        $form.Controls.Add($cb)

        $script:y += $sp
        return @{ Label = $lbl; Input = $cb }
    }

    function Add-KeyFileRow {
        param([string]$Label)
        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Location = New-Object System.Drawing.Point(15, $script:y)
        $lbl.Size = New-Object System.Drawing.Size($lw, 20)
        $lbl.Text = $Label
        $form.Controls.Add($lbl)

        $txt = New-Object System.Windows.Forms.TextBox
        $txt.Location = New-Object System.Drawing.Point(175, $script:y)
        $txt.Size = New-Object System.Drawing.Size(235, 20)
        $form.Controls.Add($txt)

        $btn = New-Object System.Windows.Forms.Button
        $btn.Location = New-Object System.Drawing.Point(415, $script:y - 2)
        $btn.Size = New-Object System.Drawing.Size(60, 24)
        $btn.Text = 'Browse'
        $form.Controls.Add($btn)

        $capturedTxt = $txt
        $btn.Add_Click({
            $dlg = New-Object System.Windows.Forms.OpenFileDialog
            $dlg.Title = 'Select SSH Private Key'
            $dlg.Filter = 'Key files (*.pem;*.ppk;*.key;*)|*.pem;*.ppk;*.key;*'
            if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
                $capturedTxt.Text = $dlg.FileName
            }
        })

        $script:y += $sp
        return @{ Label = $lbl; Input = $txt; Button = $btn }
    }

    function Add-SepLabel {
        param([string]$Text)
        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Location = New-Object System.Drawing.Point(15, $script:y)
        $lbl.Size = New-Object System.Drawing.Size(510, 16)
        $lbl.Text = $Text
        $lbl.ForeColor = [System.Drawing.Color]::Gray
        $form.Controls.Add($lbl)
        $script:y += 22
        return $lbl
    }

    # Connection mode
    $modeRow = Add-ComboRow 'Connection Mode:' @('Direct Connection', 'Jump Server')

    # Jump server section
    $jumpSep     = Add-SepLabel '--- Jump Server ---'
    $jumpHostRow = Add-Row      'Jump Host:'  ''
    $jumpUserRow = Add-Row      'Jump User:'  ''
    $jumpAuthRow = Add-ComboRow 'Jump Auth:'  @('Password', 'SSH Key (Agent)', 'Key File')
    $jumpPassRow = Add-Row      'Jump Password:' '' -Password
    $jumpKeyRow  = Add-KeyFileRow 'Jump Key File:'

    # Target host section
    $targetSep     = Add-SepLabel '--- Target Host ---'
    $targetHostRow = Add-Row      'Target Host:'     ''
    $targetUserRow = Add-Row      'Target User:'     'root'
    $targetAuthRow = Add-ComboRow 'Target Auth:'     @('Password', 'SSH Key (Agent)', 'Key File')
    $targetPassRow = Add-Row      'Target Password:' '' -Password
    $targetKeyRow  = Add-KeyFileRow 'Target Key File:'
    $targetPortRow = Add-Row      'Target Port:'     '22'

    # Capture section
    $capSep    = Add-SepLabel '--- Capture ---'
    $ifaceRow  = Add-Row 'Interface:'      'eth0'
    $filterRow = Add-Row 'Capture Filter:' ''
    $snapRow   = Add-Row 'Snap Length:'    '0'

    # Sudo checkbox
    $sudoLbl = New-Object System.Windows.Forms.Label
    $sudoLbl.Location = New-Object System.Drawing.Point(15, $y)
    $sudoLbl.Size = New-Object System.Drawing.Size($lw, 20)
    $sudoLbl.Text = 'Use Sudo:'
    $form.Controls.Add($sudoLbl)
    $sudoBox = New-Object System.Windows.Forms.CheckBox
    $sudoBox.Location = New-Object System.Drawing.Point(175, $y)
    $sudoBox.Size = New-Object System.Drawing.Size(20, 20)
    $form.Controls.Add($sudoBox)
    $sudoHint = New-Object System.Windows.Forms.Label
    $sudoHint.Location = New-Object System.Drawing.Point(200, $y)
    $sudoHint.Size = New-Object System.Drawing.Size(290, 20)
    $sudoHint.Text = '(if tcpdump requires sudo on target)'
    $sudoHint.ForeColor = [System.Drawing.Color]::Gray
    $form.Controls.Add($sudoHint)
    $y += $sp

    $wsRow = Add-Row 'Wireshark Path:' 'C:\Program Files\Wireshark\Wireshark.exe'

    # Buttons
    $y += 10
    $okBtn = New-Object System.Windows.Forms.Button
    $okBtn.Location = New-Object System.Drawing.Point(355, $y)
    $okBtn.Size = New-Object System.Drawing.Size(75, 25)
    $okBtn.Text = 'Start'
    $okBtn.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $okBtn
    $form.Controls.Add($okBtn)

    $cancelBtn = New-Object System.Windows.Forms.Button
    $cancelBtn.Location = New-Object System.Drawing.Point(440, $y)
    $cancelBtn.Size = New-Object System.Drawing.Size(75, 25)
    $cancelBtn.Text = 'Cancel'
    $cancelBtn.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancelBtn
    $form.Controls.Add($cancelBtn)

    # Dynamic visibility
    $UpdateVisibility = {
        $isJump = $modeRow.Input.SelectedItem -eq 'Jump Server'

        foreach ($ctrl in @($jumpSep,
                             $jumpHostRow.Label, $jumpHostRow.Input,
                             $jumpUserRow.Label, $jumpUserRow.Input,
                             $jumpAuthRow.Label, $jumpAuthRow.Input)) {
            $ctrl.Visible = $isJump
        }

        $jumpAuth  = $jumpAuthRow.Input.SelectedItem
        $jumpPass  = $jumpAuth -eq 'Password'
        $jumpKey   = $jumpAuth -eq 'Key File'
        $jumpPassRow.Label.Visible = $isJump -and $jumpPass
        $jumpPassRow.Input.Visible = $isJump -and $jumpPass
        $jumpKeyRow.Label.Visible  = $isJump -and $jumpKey
        $jumpKeyRow.Input.Visible  = $isJump -and $jumpKey
        $jumpKeyRow.Button.Visible = $isJump -and $jumpKey

        $targetAuth = $targetAuthRow.Input.SelectedItem
        $targetPass = $targetAuth -eq 'Password'
        $targetKey  = $targetAuth -eq 'Key File'
        $targetPassRow.Label.Visible = $targetPass
        $targetPassRow.Input.Visible = $targetPass
        $targetKeyRow.Label.Visible  = $targetKey
        $targetKeyRow.Input.Visible  = $targetKey
        $targetKeyRow.Button.Visible = $targetKey
    }

    $modeRow.Input.add_SelectedIndexChanged($UpdateVisibility)
    $jumpAuthRow.Input.add_SelectedIndexChanged($UpdateVisibility)
    $targetAuthRow.Input.add_SelectedIndexChanged($UpdateVisibility)
    & $UpdateVisibility

    if ($form.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return $null }

    return @{
        Mode           = $modeRow.Input.SelectedItem
        JumpHost       = $jumpHostRow.Input.Text
        JumpUser       = $jumpUserRow.Input.Text
        JumpAuth       = $jumpAuthRow.Input.SelectedItem
        JumpPassword   = $jumpPassRow.Input.Text
        JumpKeyFile    = $jumpKeyRow.Input.Text
        TargetHost     = $targetHostRow.Input.Text
        TargetUser     = $targetUserRow.Input.Text
        TargetAuth     = $targetAuthRow.Input.SelectedItem
        TargetPassword = $targetPassRow.Input.Text
        TargetKeyFile  = $targetKeyRow.Input.Text
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
    if ($ef) {
        return "${sudo}tcpdump -i `"$ei`" -U -s $SnapLength -w - -- `"$ef`""
    } else {
        return "${sudo}tcpdump -i `"$ei`" -U -s $SnapLength -w -"
    }
}

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

# Returns extra ssh args for a given auth mode, and optionally sets SSH_ASKPASS.
# Caller must clean up the returned AskPassPath when done.
function New-SshAuthArgs {
    param([string]$AuthMode, [string]$Password, [string]$KeyFile)
    $extraArgs   = @()
    $askPassPath = $null

    switch ($AuthMode) {
        'Password' {
            if ($Password) { $askPassPath = Set-SshAskPass -Password $Password }
        }
        'SSH Key (Agent)' {
            $extraArgs += '-A'
        }
        'Key File' {
            if ($KeyFile -and (Test-Path $KeyFile)) {
                $extraArgs += '-i', $KeyFile
            }
        }
    }

    return @{ Args = $extraArgs; AskPassPath = $askPassPath }
}

# Binary-safe capture: wires ssh.exe stdout directly to Wireshark stdin.
function Start-Capture {
    param([string]$SshExe, [string[]]$SshArgs, [string]$WiresharkPath)

    Write-Host "Starting capture -- press Ctrl+C or close Wireshark to stop." -ForegroundColor Yellow

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
        # Stream closed -- normal shutdown path
    } finally {
        try { $wsStream.Close()         } catch {}
        try { $sshProc.Kill()           } catch {}
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
        "RemoteTrace -- Missing ssh.exe",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
Write-Host "SSH:       $sshExe" -ForegroundColor Gray

$wsPath = Find-Wireshark -Hint $cfg.WiresharkPath
if (-not $wsPath) {
    [System.Windows.Forms.MessageBox]::Show(
        "Wireshark not found.`n`nDownload from https://www.wireshark.org/`nor update the path in the form.",
        "RemoteTrace -- Missing Wireshark",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
Write-Host "Wireshark: $wsPath" -ForegroundColor Gray

$baseOpts   = @('-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10', '-o', 'LogLevel=ERROR')
$tcpdumpCmd = Build-TcpdumpCommand -Interface $cfg.Interface -Filter $cfg.Filter `
                                   -SnapLength $cfg.SnapLength -UseSudo $cfg.UseSudo

Write-Host ""
Write-Host "=== RemoteTrace v$VERSION ===" -ForegroundColor Green
Write-Host "Mode:      $($cfg.Mode)"        -ForegroundColor Cyan
Write-Host "Interface: $($cfg.Interface)"   -ForegroundColor Cyan
Write-Host "Filter:    $($cfg.Filter)"      -ForegroundColor Cyan
Write-Host ""

$askPassPaths = @()

try {
    switch ($cfg.Mode) {

        'Direct Connection' {
            $auth = New-SshAuthArgs -AuthMode $cfg.TargetAuth `
                                    -Password $cfg.TargetPassword `
                                    -KeyFile  $cfg.TargetKeyFile
            if ($auth.AskPassPath) { $askPassPaths += $auth.AskPassPath }

            $sshArgs = $baseOpts + $auth.Args + @(
                '-p', $cfg.TargetPort,
                "$($cfg.TargetUser)@$($cfg.TargetHost)",
                $tcpdumpCmd
            )
            Start-Capture -SshExe $sshExe -SshArgs $sshArgs -WiresharkPath $wsPath
        }

        'Jump Server' {
            $jumpAuth = New-SshAuthArgs -AuthMode $cfg.JumpAuth `
                                        -Password $cfg.JumpPassword `
                                        -KeyFile  $cfg.JumpKeyFile
            if ($jumpAuth.AskPassPath) { $askPassPaths += $jumpAuth.AskPassPath }

            $targetAuth = New-SshAuthArgs -AuthMode $cfg.TargetAuth `
                                          -Password $cfg.TargetPassword `
                                          -KeyFile  $cfg.TargetKeyFile
            # Note: SSH_ASKPASS handles one hop only; target password auth via jump
            # will fall through to ssh's interactive prompt if no key is configured.

            $sshArgs = $baseOpts + $jumpAuth.Args + $targetAuth.Args + @(
                '-J', "$($cfg.JumpUser)@$($cfg.JumpHost)",
                '-p', $cfg.TargetPort,
                "$($cfg.TargetUser)@$($cfg.TargetHost)",
                $tcpdumpCmd
            )
            Start-Capture -SshExe $sshExe -SshArgs $sshArgs -WiresharkPath $wsPath
        }
    }
} catch {
    Write-Host "Error: $_" -ForegroundColor Red
} finally {
    foreach ($p in $askPassPaths) { Remove-SshAskPass -Path $p }
}

Write-Host ""
Write-Host "Capture session ended." -ForegroundColor Green
