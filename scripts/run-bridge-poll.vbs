' FDE-Bridge-Poll hidden launcher (P2: no console window on scheduled runs).
' wscript.exe is a GUI-subsystem host, and Run(..., 0, ...) hides the cmd child,
' so the node collector runs fully silent while its output is captured to a log.
Dim fso, shell, scriptDir, logDir, logFile, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
logDir = fso.GetParentFolderName(scriptDir) & "\logs"
If Not fso.FolderExists(logDir) Then
  fso.CreateFolder(logDir)
End If
logFile = logDir & "\bridge-poll.log"
If fso.FileExists(logFile) Then
  If fso.GetFile(logFile).Size > 1048576 Then
    fso.DeleteFile(logFile)
  End If
End If
' cmd /c strips the first and last quote when the text after /c starts with a
' quote — the old string led the & segment with doubled quotes and ended with a
' stray one, so cmd treated the mangled token as the command name and the
' collector never ran (silent since 10/26). chcp stays unquoted up front to
' keep the strip rule out of play; each path gets single-level quoting only.
cmd = "cmd /d /c chcp 65001>nul & ""D:\software\nodejs\node.exe"" """ & scriptDir & "\bridge-poll.mjs"" >> """ & logFile & """ 2>&1"
shell.Run cmd, 0, False
