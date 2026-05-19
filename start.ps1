function Start-All {
    $backend = Start-Process powershell -ArgumentList "-File ./start-backend.ps1" -PassThru
    $frontend = Start-Process powershell -ArgumentList "-File ./start-frontend.ps1" -PassThru

    return @{ backend = $backend; frontend = $frontend }
}

function Stop-All($procs) {
    taskkill /PID $procs.backend.Id /T /F
    taskkill /PID $procs.frontend.Id /T /F
}

$procs = Start-All

Write-Host "commands:"
Write-Host "  kill    -> stop both"
Write-Host "  restart -> restart both"

try {
    while ($true) {
        $input = Read-Host "enter command"

        if ($input -eq "kill") {
            Stop-All $procs
            break
        }

        elseif ($input -eq "restart") {
            Stop-All $procs
            $procs = Start-All
        }

        else {
            Write-Host "valid commands: kill, restart"
        }
    }
}
finally {
    Stop-All $procs
}
