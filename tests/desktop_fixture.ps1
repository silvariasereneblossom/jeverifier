# A throwaway WinForms window with a unique title, so desktop tests never touch the user's apps.
param([string]$Title = "jevauto-fixture")
Add-Type -AssemblyName System.Windows.Forms
# Open WITHOUT taking focus, so the user's typing in other apps is never redirected into this window.
Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @"
public class QuietForm : System.Windows.Forms.Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override System.Windows.Forms.CreateParams CreateParams {
        get { var p = base.CreateParams; p.ExStyle |= 0x08000000; return p; }  // WS_EX_NOACTIVATE
    }
}
"@
$form = New-Object QuietForm
$form.Text = $Title
$box = New-Object System.Windows.Forms.TextBox
$box.Name = "query"; $box.AccessibleName = "Query"; $box.Top = 10; $box.Left = 10; $box.Width = 200
$btn = New-Object System.Windows.Forms.Button
$btn.Text = "Search"; $btn.Top = 40; $btn.Left = 10
$lbl = New-Object System.Windows.Forms.Label
$lbl.Text = "idle"; $lbl.Top = 75; $lbl.Left = 10; $lbl.Width = 250
$btn.Add_Click({ $lbl.Text = "searched " + $box.Text })
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 30000; $timer.Add_Tick({ $form.Close() }); $timer.Start()  # never outlives the test
$form.Controls.AddRange(@($box, $btn, $lbl))
[System.Windows.Forms.Application]::Run($form)
