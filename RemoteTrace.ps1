# Remote TCPDump to Wireshark PowerShell Script with GUI Input
# This script connects through an intermediate SSH host to run tcpdump on a target host
# and pipes the output directly to Wireshark

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Function to create input form
function Get-UserInputs {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Remote TCPDump to Wireshark Configuration'
    $form.Size = New-Object System.Drawing.Size(500, 700)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    # Create input controls
    $y = 20
    $labelWidth = 140
    $inputWidth = 300
    $spacing = 35

    # Connection mode selection
    $connectionModeLabel = New-Object System.Windows.Forms.Label
    $connectionModeLabel.Location = New-Object System.Drawing.Point(20, $y)
    $connectionModeLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $connectionModeLabel.Text = 'Connection Mode:'
    $form.Controls.Add($connectionModeLabel)

    $connectionModeCombo = New-Object System.Windows.Forms.ComboBox
    $connectionModeCombo.Location = New-Object System.Drawing.Point(160, $y)
    $connectionModeCombo.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $connectionModeCombo.DropDownStyle = 'DropDownList'
    $connectionModeCombo.Items.AddRange(@('Jump Server + Auto-Discovery', 'Jump Server + Manual Target', 'Direct Connection'))
    $connectionModeCombo.SelectedIndex = 0
    $form.Controls.Add($connectionModeCombo)

    $y += $spacing

    # Jump Host settings
    $jumpHostLabel = New-Object System.Windows.Forms.Label
    $jumpHostLabel.Location = New-Object System.Drawing.Point(20, $y)
    $jumpHostLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $jumpHostLabel.Text = 'Jump Host:'
    $form.Controls.Add($jumpHostLabel)

    $jumpHostInput = New-Object System.Windows.Forms.TextBox
    $jumpHostInput.Location = New-Object System.Drawing.Point(160, $y)
    $jumpHostInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $jumpHostInput.Text = '***REMOVED***'
    $form.Controls.Add($jumpHostInput)

    $y += $spacing

    $jumpUserLabel = New-Object System.Windows.Forms.Label
    $jumpUserLabel.Location = New-Object System.Drawing.Point(20, $y)
    $jumpUserLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $jumpUserLabel.Text = 'Jump User:'
    $form.Controls.Add($jumpUserLabel)

    $jumpUserInput = New-Object System.Windows.Forms.TextBox
    $jumpUserInput.Location = New-Object System.Drawing.Point(160, $y)
    $jumpUserInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $jumpUserInput.Text = 'jteeuwen'
    $form.Controls.Add($jumpUserInput)

    $y += $spacing

    $jumpPasswordLabel = New-Object System.Windows.Forms.Label
    $jumpPasswordLabel.Location = New-Object System.Drawing.Point(20, $y)
    $jumpPasswordLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $jumpPasswordLabel.Text = 'Jump Password:'
    $form.Controls.Add($jumpPasswordLabel)

    $jumpPasswordInput = New-Object System.Windows.Forms.TextBox
    $jumpPasswordInput.Location = New-Object System.Drawing.Point(160, $y)
    $jumpPasswordInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $jumpPasswordInput.PasswordChar = '*'
    $form.Controls.Add($jumpPasswordInput)

    $y += $spacing

    # Target Host settings with dynamic visibility
    $targetNameLabel = New-Object System.Windows.Forms.Label
    $targetNameLabel.Location = New-Object System.Drawing.Point(20, $y)
    $targetNameLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $targetNameLabel.Text = 'Target Name:'
    $form.Controls.Add($targetNameLabel)

    $targetNameInput = New-Object System.Windows.Forms.TextBox
    $targetNameInput.Location = New-Object System.Drawing.Point(160, $y)
    $targetNameInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $targetNameInput.Text = 'demo'
    $form.Controls.Add($targetNameInput)

    $y += $spacing

    $targetHostLabel = New-Object System.Windows.Forms.Label
    $targetHostLabel.Location = New-Object System.Drawing.Point(20, $y)
    $targetHostLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $targetHostLabel.Text = 'Target Host:'
    $form.Controls.Add($targetHostLabel)

    $targetHostInput = New-Object System.Windows.Forms.TextBox
    $targetHostInput.Location = New-Object System.Drawing.Point(160, $y)
    $targetHostInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $targetHostInput.Text = '(will be auto-discovered)'
    $form.Controls.Add($targetHostInput)

    $y += $spacing

    $targetUserLabel = New-Object System.Windows.Forms.Label
    $targetUserLabel.Location = New-Object System.Drawing.Point(20, $y)
    $targetUserLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $targetUserLabel.Text = 'Target User:'
    $form.Controls.Add($targetUserLabel)

    $targetUserInput = New-Object System.Windows.Forms.TextBox
    $targetUserInput.Location = New-Object System.Drawing.Point(160, $y)
    $targetUserInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $targetUserInput.Text = 'root'
    $form.Controls.Add($targetUserInput)

    $y += $spacing

    $targetPasswordLabel = New-Object System.Windows.Forms.Label
    $targetPasswordLabel.Location = New-Object System.Drawing.Point(20, $y)
    $targetPasswordLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $targetPasswordLabel.Text = 'Target Password:'
    $form.Controls.Add($targetPasswordLabel)

    $targetPasswordInput = New-Object System.Windows.Forms.TextBox
    $targetPasswordInput.Location = New-Object System.Drawing.Point(160, $y)
    $targetPasswordInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $targetPasswordInput.Text = '(will be auto-discovered)'
    $targetPasswordInput.PasswordChar = '*'
    $form.Controls.Add($targetPasswordInput)

    $y += $spacing

    $targetPortLabel = New-Object System.Windows.Forms.Label
    $targetPortLabel.Location = New-Object System.Drawing.Point(20, $y)
    $targetPortLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $targetPortLabel.Text = 'Target Port:'
    $form.Controls.Add($targetPortLabel)

    $targetPortInput = New-Object System.Windows.Forms.TextBox
    $targetPortInput.Location = New-Object System.Drawing.Point(160, $y)
    $targetPortInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $targetPortInput.Text = '22'
    $form.Controls.Add($targetPortInput)

    $y += $spacing

    # Capture settings
    $networkInterfaceLabel = New-Object System.Windows.Forms.Label
    $networkInterfaceLabel.Location = New-Object System.Drawing.Point(20, $y)
    $networkInterfaceLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $networkInterfaceLabel.Text = 'Network Interface:'
    $form.Controls.Add($networkInterfaceLabel)

    $networkInterfaceInput = New-Object System.Windows.Forms.TextBox
    $networkInterfaceInput.Location = New-Object System.Drawing.Point(160, $y)
    $networkInterfaceInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $networkInterfaceInput.Text = 'eth0'
    $form.Controls.Add($networkInterfaceInput)

    $y += $spacing

    $captureFilterLabel = New-Object System.Windows.Forms.Label
    $captureFilterLabel.Location = New-Object System.Drawing.Point(20, $y)
    $captureFilterLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $captureFilterLabel.Text = 'Capture Filter:'
    $form.Controls.Add($captureFilterLabel)

    $captureFilterInput = New-Object System.Windows.Forms.TextBox
    $captureFilterInput.Location = New-Object System.Drawing.Point(160, $y)
    $captureFilterInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $captureFilterInput.Text = 'icmp'
    $form.Controls.Add($captureFilterInput)

    $y += $spacing

    $snapLengthLabel = New-Object System.Windows.Forms.Label
    $snapLengthLabel.Location = New-Object System.Drawing.Point(20, $y)
    $snapLengthLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $snapLengthLabel.Text = 'Snap Length:'
    $form.Controls.Add($snapLengthLabel)

    $snapLengthInput = New-Object System.Windows.Forms.TextBox
    $snapLengthInput.Location = New-Object System.Drawing.Point(160, $y)
    $snapLengthInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $snapLengthInput.Text = '0'
    $form.Controls.Add($snapLengthInput)

    $y += $spacing

    # Use sudo checkbox
    $useSudoLabel = New-Object System.Windows.Forms.Label
    $useSudoLabel.Location = New-Object System.Drawing.Point(20, $y)
    $useSudoLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $useSudoLabel.Text = 'Use Sudo:'
    $form.Controls.Add($useSudoLabel)

    $useSudoCheckbox = New-Object System.Windows.Forms.CheckBox
    $useSudoCheckbox.Location = New-Object System.Drawing.Point(160, $y)
    $useSudoCheckbox.Size = New-Object System.Drawing.Size(20, 20)
    $useSudoCheckbox.Checked = $false
    $form.Controls.Add($useSudoCheckbox)

    $useSudoDescription = New-Object System.Windows.Forms.Label
    $useSudoDescription.Location = New-Object System.Drawing.Point(185, $y)
    $useSudoDescription.Size = New-Object System.Drawing.Size(280, 20)
    $useSudoDescription.Text = '(Check if tcpdump requires sudo on target host)'
    $useSudoDescription.ForeColor = [System.Drawing.Color]::Gray
    $form.Controls.Add($useSudoDescription)

    $y += $spacing

    # Paths
    $plinkPathLabel = New-Object System.Windows.Forms.Label
    $plinkPathLabel.Location = New-Object System.Drawing.Point(20, $y)
    $plinkPathLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $plinkPathLabel.Text = 'Plink Path:'
    $form.Controls.Add($plinkPathLabel)

    $plinkPathInput = New-Object System.Windows.Forms.TextBox
    $plinkPathInput.Location = New-Object System.Drawing.Point(160, $y)
    $plinkPathInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $plinkPathInput.Text = "$env:USERPROFILE\Downloads\plink.exe"
    $form.Controls.Add($plinkPathInput)

    $y += $spacing

    $wiresharkPathLabel = New-Object System.Windows.Forms.Label
    $wiresharkPathLabel.Location = New-Object System.Drawing.Point(20, $y)
    $wiresharkPathLabel.Size = New-Object System.Drawing.Size($labelWidth, 20)
    $wiresharkPathLabel.Text = 'Wireshark Path:'
    $form.Controls.Add($wiresharkPathLabel)

    $wiresharkPathInput = New-Object System.Windows.Forms.TextBox
    $wiresharkPathInput.Location = New-Object System.Drawing.Point(160, $y)
    $wiresharkPathInput.Size = New-Object System.Drawing.Size($inputWidth, 20)
    $wiresharkPathInput.Text = 'C:\Program Files\Wireshark\Wireshark.exe'
    $form.Controls.Add($wiresharkPathInput)

    $y += 50

    # Buttons
    $okButton = New-Object System.Windows.Forms.Button
    $okButton.Location = New-Object System.Drawing.Point(300, $y)
    $okButton.Size = New-Object System.Drawing.Size(75, 23)
    $okButton.Text = 'OK'
    $okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $okButton
    $form.Controls.Add($okButton)

    $cancelButton = New-Object System.Windows.Forms.Button
    $cancelButton.Location = New-Object System.Drawing.Point(385, $y)
    $cancelButton.Size = New-Object System.Drawing.Size(75, 23)
    $cancelButton.Text = 'Cancel'
    $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $cancelButton
    $form.Controls.Add($cancelButton)

    # Function to update form based on connection mode
    $UpdateFormVisibility = {
        $mode = $connectionModeCombo.SelectedItem
        
        if ($mode -eq 'Direct Connection') {
            # Direct connection mode
            $jumpHostLabel.Visible = $false
            $jumpHostInput.Visible = $false
            $jumpUserLabel.Visible = $false
            $jumpUserInput.Visible = $false
            $jumpPasswordLabel.Visible = $false
            $jumpPasswordInput.Visible = $false
            
            $targetNameLabel.Visible = $false
            $targetNameInput.Visible = $false
            
            $targetHostLabel.Text = 'Target Host:'
            $targetHostInput.Text = '192.168.1.100'
            $targetHostInput.ReadOnly = $false
            $targetHostInput.BackColor = [System.Drawing.SystemColors]::Window
            $targetHostLabel.ForeColor = [System.Drawing.Color]::Black
            
            $targetPasswordLabel.ForeColor = [System.Drawing.Color]::Black
            $targetPasswordInput.Text = ''
            $targetPasswordInput.ReadOnly = $false
            $targetPasswordInput.BackColor = [System.Drawing.SystemColors]::Window
        }
        elseif ($mode -eq 'Jump Server + Manual Target') {
            # Manual target mode
            $jumpHostLabel.Visible = $true
            $jumpHostInput.Visible = $true
            $jumpUserLabel.Visible = $true
            $jumpUserInput.Visible = $true
            $jumpPasswordLabel.Visible = $true
            $jumpPasswordInput.Visible = $true
            
            $targetNameLabel.Visible = $false
            $targetNameInput.Visible = $false
            
            $targetHostLabel.Text = 'Target Host:'
            $targetHostInput.Text = '192.168.1.100'
            $targetHostInput.ReadOnly = $false
            $targetHostInput.BackColor = [System.Drawing.SystemColors]::Window
            $targetHostLabel.ForeColor = [System.Drawing.Color]::Black
            
            $targetPasswordLabel.ForeColor = [System.Drawing.Color]::Black
            $targetPasswordInput.Text = ''
            $targetPasswordInput.ReadOnly = $false
            $targetPasswordInput.BackColor = [System.Drawing.SystemColors]::Window
        }
        else {
            # Auto-discovery mode (default)
            $jumpHostLabel.Visible = $true
            $jumpHostInput.Visible = $true
            $jumpUserLabel.Visible = $true
            $jumpUserInput.Visible = $true
            $jumpPasswordLabel.Visible = $true
            $jumpPasswordInput.Visible = $true
            
            $targetNameLabel.Visible = $true
            $targetNameInput.Visible = $true
            
            $targetHostLabel.Text = 'Target Host:'
            $targetHostInput.Text = '(will be auto-discovered)'
            $targetHostInput.ReadOnly = $true
            $targetHostInput.BackColor = [System.Drawing.SystemColors]::Control
            $targetHostLabel.ForeColor = [System.Drawing.Color]::Gray
            
            $targetPasswordLabel.ForeColor = [System.Drawing.Color]::Gray
            $targetPasswordInput.Text = '(will be auto-discovered)'
            $targetPasswordInput.ReadOnly = $true
            $targetPasswordInput.BackColor = [System.Drawing.SystemColors]::Control
        }
    }

    # Attach event handler and initialize
    $connectionModeCombo.add_SelectedIndexChanged($UpdateFormVisibility)
    & $UpdateFormVisibility

    # Show form and return values
    $result = $form.ShowDialog()
    
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        return @{
            ConnectionMode = $connectionModeCombo.SelectedItem
            JumpHost = $jumpHostInput.Text
            JumpUser = $jumpUserInput.Text
            JumpPassword = $jumpPasswordInput.Text
            TargetName = $targetNameInput.Text
            TargetHost = $targetHostInput.Text
            TargetUser = $targetUserInput.Text
            TargetPassword = $targetPasswordInput.Text
            TargetPort = $targetPortInput.Text
            NetworkInterface = $networkInterfaceInput.Text
            CaptureFilter = $captureFilterInput.Text
            SnapLength = $snapLengthInput.Text
            UseSudo = $useSudoCheckbox.Checked
            PlinkPath = $plinkPathInput.Text
            WiresharkPath = $wiresharkPathInput.Text
        }
    } else {
        return $null
    }
}

# Function to find Wireshark executable
function Find-WiresharkPath {
    param([string]$InputPath)
    
    # If the input path is a directory, look for Wireshark.exe inside it
    if (Test-Path $InputPath -PathType Container) {
        $wiresharkExe = Join-Path $InputPath "Wireshark.exe"
        if (Test-Path $wiresharkExe) {
            return $wiresharkExe
        }
    }
    
    # If the input path is already a file and exists, use it
    if (Test-Path $InputPath -PathType Leaf) {
        return $InputPath
    }
    
    # Try common installation paths
    $commonPaths = @(
        "C:\Program Files\Wireshark\Wireshark.exe",
        "C:\Program Files (x86)\Wireshark\Wireshark.exe",
        "${env:ProgramFiles}\Wireshark\Wireshark.exe",
        "${env:ProgramFiles(x86)}\Wireshark\Wireshark.exe"
    )
    
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            Write-Host "Found Wireshark at: $path" -ForegroundColor Green
            return $path
        }
    }
    
    return $null
}

# Function to discover target details using the 'f' script on jump server
function Get-TargetDetails {
    param(
        [string]$JumpHost,
        [string]$JumpUser,
        [string]$JumpPassword,
        [string]$TargetName,
        [string]$PlinkPath
    )
    
    Write-Host "Discovering target details for: $TargetName" -ForegroundColor Yellow
    
    try {
        # Execute the 'f' script on the jump server with limited output
        $fCommand = "/usr/bin/f $TargetName all 2>/dev/null | head -200"
        $PlinkCommand = "`"$PlinkPath`" -batch -ssh -l $JumpUser -pw `"$JumpPassword`" $JumpHost `"$fCommand`""
        
        Write-Host "Running discovery command: f $TargetName all" -ForegroundColor Gray
        
        # Capture the output and ignore stderr for exit code checking
        $output = cmd.exe /c "$PlinkCommand 2>nul"
        $exitCode = $LASTEXITCODE
        
        # Don't fail on exit code 1 if we got some output (f script might return 1 but still work)
        if ($exitCode -ne 0 -and ($output -eq $null -or $output.Length -eq 0)) {
            # Try without error redirection to see what's happening
            Write-Host "First attempt failed, trying without error suppression..." -ForegroundColor Yellow
            $debugCommand = "`"$PlinkPath`" -batch -ssh -l $JumpUser -pw `"$JumpPassword`" $JumpHost `"/usr/bin/f $TargetName all`""
            $debugOutput = cmd.exe /c $debugCommand 2>&1
            
            Write-Host "Debug output:" -ForegroundColor Yellow
            $debugOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
            
            throw "Failed to execute 'f' script. Exit code: $exitCode"
        }
        
        # Parse the output to extract ssh_ip and access_pwd
        $sshIp = $null
        $accessPwd = $null
        
        foreach ($line in $output) {
            $line = $line.ToString().Trim()
            
            # Remove ANSI escape codes that might be in the output
            $line = $line -replace '\x1b\[[0-9;]*[a-zA-Z]', ''
            $line = $line -replace '\\033\[[0-9;]*[a-zA-Z]', ''
            
            # Look for ssh_ip line with format "ssh_ip:       212.57.62.104"
            if ($line -match "^ssh_ip:\s*(.+)$") {
                $sshIp = $matches[1].Trim()
                # Remove any remaining escape codes or special characters
                $sshIp = $sshIp -replace '[^\w\.\-]', ''
                Write-Host "Found SSH IP: $sshIp" -ForegroundColor Green
            }
            # Look for access_pwd line with format "access_pwd:   password"
            elseif ($line -match "^access_pwd:\s*(.+)$") {
                $accessPwd = $matches[1].Trim()
                Write-Host "Found Access Password: [HIDDEN]" -ForegroundColor Green
            }
        }
        
        if (-not $sshIp -or -not $accessPwd) {
            Write-Host "" -ForegroundColor Yellow
            Write-Host "Raw output from 'f' script:" -ForegroundColor Yellow
            Write-Host "================================================" -ForegroundColor Yellow
            $output | ForEach-Object { Write-Host "  $_" }
            Write-Host "================================================" -ForegroundColor Yellow
            Write-Host "" -ForegroundColor Yellow
            
            if (-not $sshIp) {
                Write-Host "Could not find 'ssh_ip' in the output" -ForegroundColor Red
            }
            if (-not $accessPwd) {
                Write-Host "Could not find 'access_pwd' in the output" -ForegroundColor Red
            }
            
            throw "Could not parse ssh_ip or access_pwd from 'f' script output"
        }
        
        return @{
            TargetHost = $sshIp
            TargetPassword = $accessPwd
        }
    }
    catch {
        Write-Error "Failed to discover target details: $_"
        return $null
    }
}

# Get user inputs
$inputs = Get-UserInputs

if ($inputs -eq $null) {
    Write-Host "Operation cancelled by user." -ForegroundColor Yellow
    exit
}

# Assign variables from input
$ConnectionMode = $inputs.ConnectionMode
$JumpHost = $inputs.JumpHost
$JumpUser = $inputs.JumpUser
$JumpPassword = $inputs.JumpPassword
$TargetName = $inputs.TargetName
$TargetUser = $inputs.TargetUser
$TargetPort = $inputs.TargetPort
$NetworkInterface = $inputs.NetworkInterface
$CaptureFilter = $inputs.CaptureFilter
$SnapLength = $inputs.SnapLength
$UseSudo = $inputs.UseSudo
$PlinkPath = $inputs.PlinkPath
$WiresharkPath = $inputs.WiresharkPath

# Handle target discovery based on connection mode
if ($ConnectionMode -eq 'Jump Server + Auto-Discovery') {
    # Discover target details using the 'f' script
    $targetDetails = Get-TargetDetails -JumpHost $JumpHost -JumpUser $JumpUser -JumpPassword $JumpPassword -TargetName $TargetName -PlinkPath $PlinkPath
    
    if ($targetDetails -eq $null) {
        Write-Host "Failed to discover target details. Please check:" -ForegroundColor Red
        Write-Host "1. Jump server connection details are correct" -ForegroundColor Red
        Write-Host "2. Target name '$TargetName' exists in the system" -ForegroundColor Red
        Write-Host "3. The 'f' script is available at /usr/bin/f on the jump server" -ForegroundColor Red
        exit 1
    }
    
    # Use discovered details
    $TargetHost = $targetDetails.TargetHost
    $TargetPassword = $targetDetails.TargetPassword
}
else {
    # Use manual target details (both manual and direct modes)
    $TargetHost = $inputs.TargetHost
    $TargetPassword = $inputs.TargetPassword
}

# Fixed settings
$BufferMode = "-U"  # Unbuffered mode

# Validate that required executables exist
if (-not (Test-Path $PlinkPath)) {
    Write-Error "plink.exe not found at: $PlinkPath"
    Write-Host "Please download PuTTY/plink.exe or update the path in the script."
    exit 1
}

# Find and validate Wireshark path
$WiresharkPath = Find-WiresharkPath -InputPath $WiresharkPath
if (-not $WiresharkPath) {
    Write-Error "Wireshark not found at the specified location or common installation paths."
    Write-Host "Please install Wireshark or update the path in the script."
    Write-Host "Common locations to check:"
    Write-Host "  - C:\Program Files\Wireshark\Wireshark.exe"
    Write-Host "  - C:\Program Files (x86)\Wireshark\Wireshark.exe"
    exit 1
}

# Build the command components with comprehensive SSH options
$SshOptions = @(
    "-o StrictHostKeyChecking=no",
    "-o UserKnownHostsFile=/dev/null",
    "-o GlobalKnownHostsFile=/dev/null",
    "-o LogLevel=ERROR",
    "-o ConnectTimeout=30"
)
$SshOptionsString = $SshOptions -join " "

# Build tcpdump command with optional sudo
$SudoPrefix = if ($UseSudo) { "sudo " } else { "" }
$TcpdumpCommand = "${SudoPrefix}tcpdump -i $NetworkInterface $BufferMode -s $SnapLength -w - '$CaptureFilter' 2>/dev/null"

# Build the SSH command based on connection mode
if ($ConnectionMode -eq 'Direct Connection') {
    # Direct connection - no jump server
    $SshCommand = "sshpass -p '$TargetPassword' ssh $SshOptionsString -p $TargetPort $TargetUser@$TargetHost '$TcpdumpCommand'"
} else {
    # Through jump server (both auto-discovery and manual modes)
    $SshCommand = "sshpass -p '$TargetPassword' ssh $SshOptionsString -p $TargetPort $TargetUser@$TargetHost '$TcpdumpCommand'"
}

# Display information
Write-Host "=== Remote TCPDump to Wireshark ===" -ForegroundColor Green
Write-Host "Connection Mode: $ConnectionMode" -ForegroundColor Cyan
if ($ConnectionMode -ne 'Direct Connection') {
    Write-Host "Jump Host: $JumpUser@$JumpHost" -ForegroundColor Cyan
}
Write-Host "Target Host: $TargetUser@${TargetHost}:$TargetPort" -ForegroundColor Cyan
Write-Host "Interface: $NetworkInterface" -ForegroundColor Cyan
Write-Host "Filter: $CaptureFilter" -ForegroundColor Cyan
Write-Host "Using Sudo: $(if ($UseSudo) { 'Yes' } else { 'No' })" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting capture... Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

# Test the connection based on mode
if ($ConnectionMode -eq 'Direct Connection') {
    Write-Host "Testing direct connection to target host..." -ForegroundColor Yellow
    $TestSudoPrefix = if ($UseSudo) { "sudo " } else { "" }
    
    Write-Host "Step 1: Testing basic SSH connection..." -ForegroundColor Gray
    $BasicTestCommand = "`"$PlinkPath`" -batch -ssh -l $TargetUser -pw `"$TargetPassword`" -P $TargetPort $TargetHost `"echo SSH_CONNECTION_OK`""
    $BasicTestOutput = cmd.exe /c $BasicTestCommand 2>&1
    Write-Host "Basic connection result:" -ForegroundColor Gray
    $BasicTestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    
    Write-Host "Step 2: Testing tcpdump availability..." -ForegroundColor Gray
    $DetailedTestCommand = "`"$PlinkPath`" -batch -ssh -l $TargetUser -pw `"$TargetPassword`" -P $TargetPort $TargetHost `"which tcpdump && ${TestSudoPrefix}tcpdump --version 2>/dev/null | head -1`""
    $DetailedTestOutput = cmd.exe /c $DetailedTestCommand 2>&1
    Write-Host "tcpdump test result:" -ForegroundColor Gray
    $DetailedTestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    
    Write-Host "Step 3: Testing network interface..." -ForegroundColor Gray
    $InterfaceTestCommand = "`"$PlinkPath`" -batch -ssh -l $TargetUser -pw `"$TargetPassword`" -P $TargetPort $TargetHost `"ip link show $NetworkInterface 2>/dev/null || ifconfig $NetworkInterface 2>/dev/null | head -1`""
    $InterfaceTestOutput = cmd.exe /c $InterfaceTestCommand 2>&1
    Write-Host "Interface test result:" -ForegroundColor Gray
    $InterfaceTestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
} else {
    # Test through jump server (existing code)
    Write-Host "Testing connection to target host..." -ForegroundColor Yellow
    $TestSudoPrefix = if ($UseSudo) { "sudo " } else { "" }

    Write-Host "Step 1: Testing basic SSH connection..." -ForegroundColor Gray
    $BasicTestCommand = "`"$PlinkPath`" -batch -ssh -l $JumpUser -pw `"$JumpPassword`" $JumpHost `"sshpass -p '$TargetPassword' ssh $SshOptionsString -p $TargetPort $TargetUser@$TargetHost 'echo SSH_CONNECTION_OK'`""
    $BasicTestOutput = cmd.exe /c $BasicTestCommand 2>&1
    Write-Host "Basic connection result:" -ForegroundColor Gray
    $BasicTestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

    Write-Host "Step 2: Testing tcpdump availability..." -ForegroundColor Gray
    $DetailedTestCommand = "`"$PlinkPath`" -batch -ssh -l $JumpUser -pw `"$JumpPassword`" $JumpHost `"sshpass -p '$TargetPassword' ssh $SshOptionsString -p $TargetPort $TargetUser@$TargetHost 'which tcpdump && ${TestSudoPrefix}tcpdump --version 2>/dev/null | head -1'`""
    $DetailedTestOutput = cmd.exe /c $DetailedTestCommand 2>&1
    Write-Host "tcpdump test result:" -ForegroundColor Gray
    $DetailedTestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

    Write-Host "Step 3: Testing network interface..." -ForegroundColor Gray
    $InterfaceTestCommand = "`"$PlinkPath`" -batch -ssh -l $JumpUser -pw `"$JumpPassword`" $JumpHost `"sshpass -p '$TargetPassword' ssh $SshOptionsString -p $TargetPort $TargetUser@$TargetHost 'ip link show $NetworkInterface 2>/dev/null || ifconfig $NetworkInterface 2>/dev/null | head -1'`""
    $InterfaceTestOutput = cmd.exe /c $InterfaceTestCommand 2>&1
    Write-Host "Interface test result:" -ForegroundColor Gray
    $InterfaceTestOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
}

Write-Host ""

# Execute the command using cmd.exe to handle the pipe properly
try {
    if ($ConnectionMode -eq 'Direct Connection') {
        # Direct connection to target host
        $PlinkOptions = @(
            "-batch",
            "-ssh", 
            "-l", $TargetUser,
            "-pw", "`"$TargetPassword`"",
            "-P", $TargetPort,
            $TargetHost,
            "`"$TcpdumpCommand`""
        )
        
        $PlinkCommand = "`"$PlinkPath`" " + ($PlinkOptions -join " ")
        $CmdCommand = "$PlinkCommand | `"$WiresharkPath`" -k -i -"
        
        Write-Host "Executing direct command..." -ForegroundColor Gray
        Write-Host "Note: Host keys will be automatically accepted (first connection may prompt)" -ForegroundColor Yellow
        cmd.exe /c $CmdCommand
    } else {
        # Through jump server
        $PlinkOptions = @(
            "-batch",
            "-ssh", 
            "-l", $JumpUser,
            "-pw", "`"$JumpPassword`"",
            $JumpHost,
            "`"$SshCommand`""
        )
        
        $PlinkCommand = "`"$PlinkPath`" " + ($PlinkOptions -join " ")
        $CmdCommand = "$PlinkCommand | `"$WiresharkPath`" -k -i -"
        
        Write-Host "Executing command through jump server..." -ForegroundColor Gray
        Write-Host "Note: Host keys will be automatically accepted (first connection may prompt)" -ForegroundColor Yellow
        cmd.exe /c $CmdCommand
    }
}
catch {
    Write-Error "Failed to execute command: $_"
    Write-Host "Command that was attempted:"
    Write-Host $CmdCommand
}

Write-Host "Capture session ended." -ForegroundColor Green