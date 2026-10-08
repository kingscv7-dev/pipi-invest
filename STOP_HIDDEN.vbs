Option Explicit
Dim sh, fso, base, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "cmd.exe /c """ & base & "\STOP_SERVER.bat"""
sh.Run cmd, 0, True
