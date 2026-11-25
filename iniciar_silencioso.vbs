' Postuladorsito: abre la app sin dejar una ventana negra de consola.
' Doble clic para iniciar. Para cerrarla, usá el botón "Cerrar Postuladorsito" en Configuración.
Option Explicit
Dim shell, fso, carpeta, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta

' Busca pythonw (Python sin consola). Si no está, prueba con el lanzador "pyw".
cmd = ""
If ExisteComando("pythonw") Then
  cmd = "pythonw"
ElseIf ExisteComando("pyw") Then
  cmd = "pyw"
End If

If cmd = "" Then
  MsgBox "No encontré Python en esta PC." & vbCrLf & _
         "Instalalo desde python.org (tildá 'Add Python to PATH') y volvé a intentar.", vbExclamation, "Postuladorsito"
  WScript.Quit 1
End If

' 0 = ventana oculta, False = no esperar a que termine
shell.Run cmd & " """ & carpeta & "\app_postulador.py""", 0, False

Function ExisteComando(nombre)
  Dim r
  On Error Resume Next
  r = shell.Run("cmd /c where " & nombre & " >nul 2>nul", 0, True)
  ExisteComando = (Err.Number = 0 And r = 0)
  On Error GoTo 0
End Function
