// The commands behind the alerts: sound players and the desktop notification, per OS. Pure
// (no `$`, no `process`): the OS is a parameter (`rt.windows`, lib/os.ts). On Windows every
// script is fixed text and the wav name, title and body travel in env only, so nothing the
// model wrote can reach a command line or the toast XML as markup (tests/toast.test.ts).

import { clip } from './format'
import { system32 } from './os'

export type AlertKind = 'done' | 'error' | 'input'
export type Cmd = { argv: string[]; env?: Record<string, string> }

/** Windows Media wavs on every desktop edition ($env:SystemRoot\Media), 0.97-1.29 s each. */
const WAV: Record<AlertKind, string> = { done: 'Windows Ding.wav', error: 'Windows Error.wav', input: 'Windows Notify System Generic.wav' }
const SYSTEM_SOUND: Record<AlertKind, string> = { done: 'Asterisk', error: 'Hand', input: 'Exclamation' }

// No double quote and no drive literal in any script: Windows quoting stays trivial, the paths come from $env:SystemRoot.
// GetFileName blocks a traversal name; a missing wav or unset env exits 1 and the next player is tried.
const SOUND_PS =
  "$ErrorActionPreference='Stop'; $n=[IO.Path]::GetFileName($env:MERCY_WAV); (New-Object System.Media.SoundPlayer (Join-Path $env:SystemRoot ('Media\\'+$n))).PlaySync()"
// SystemSounds plays async: the sleep keeps the process alive until the sound is out.
const SYSTEM_SOUND_PS = "$ErrorActionPreference='Stop'; [System.Media.SystemSounds]::($env:MERCY_SYS).Play(); Start-Sleep -Milliseconds 700"
// The PowerShell AUMID: the toast shows as "Windows PowerShell"; a branded one needs a Start-menu shortcut.
const AUMID = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
// Text is XML-escaped and control-stripped here too (defence in depth). MERCY_URGENT=1: scenario reminder with a
// Dismiss button (it stays until dismissed); MERCY_LONG=1: duration long. Tag/Group replace the previous toast.
const TOAST_PS =
  "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; " +
  '[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]; ' +
  '[void][Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]; ' +
  "$k='[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F\\uFFFE\\uFFFF]'; " +
  "$t=[Security.SecurityElement]::Escape(($env:MERCY_TITLE -replace $k,'')); $b=[Security.SecurityElement]::Escape(($env:MERCY_BODY -replace $k,'')); " +
  "$a=''; $c=''; $d=''; if($env:MERCY_URGENT -eq '1'){$a=' scenario=''reminder'''; $c='<actions><action content=''Dismiss'' arguments=''dismiss'' activationType=''system''/></actions>'}; " +
  "if($env:MERCY_LONG -eq '1'){$d=' duration=''long'''}; " +
  '$x=New-Object Windows.Data.Xml.Dom.XmlDocument; ' +
  "$x.LoadXml('<toast'+$a+$d+'><visual><binding template=''ToastGeneric''><text>'+$t+'</text><text>'+$b+'</text></binding></visual>'+$c+'</toast>'); " +
  "$n=New-Object Windows.UI.Notifications.ToastNotification $x; $n.Tag='mercy'; $n.Group='mercy'; " +
  `[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('${AUMID}').Show($n)`

// powershell.exe is Windows PowerShell 5.1: pwsh 7 cannot load the WinRT toast types. By absolute path when the
// SystemRoot is known (SEC1-04): no PATH or cwd lookup of the name.
const ps = (root: string | undefined): string[] => [system32(root, 'WindowsPowerShell\\v1.0\\powershell.exe', 'powershell.exe'), '-NoProfile', '-NonInteractive', '-Command']

export function windowsPlayers(kind: AlertKind, root?: string): Cmd[] {
  return [
    { argv: [...ps(root), SOUND_PS], env: { MERCY_WAV: WAV[kind] } },
    { argv: [...ps(root), SYSTEM_SOUND_PS], env: { MERCY_SYS: SYSTEM_SOUND[kind] } },
  ]
}

/** XML 1.0 forbids C0 controls (but tab, LF, CR) and lone surrogates; LoadXml fails (0xC00CE508) on them. */
export function sanitizeXmlText(text: string): string {
  return text
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, '')
    .replace(/([\uD800-\uDBFF][\uDC00-\uDFFF])|[\uD800-\uDFFF]/g, (m, pair: string | undefined) => (pair ? m : '�'))
}

/**
 * The desktop notification: `notify-send` (title and body after `--`: text starting with `-` is never an
 * option) or the Windows toast. `kind` 'error' is a long toast instead of a reminder on Windows.
 */
export function toastCmd(title: string, body: string, urgency: 'normal' | 'critical', windows: boolean, kind?: AlertKind, root?: string): Cmd {
  if (!windows) return { argv: ['notify-send', '-a', 'Claude Code', '-i', 'utilities-terminal', '-u', urgency, '-t', '10000', '--', title, clip(body, 240)] }
  return {
    argv: [...ps(root), TOAST_PS],
    env: {
      MERCY_TITLE: clip(sanitizeXmlText(title), 120),
      MERCY_BODY: clip(sanitizeXmlText(body), 240),
      MERCY_URGENT: urgency === 'critical' && kind !== 'error' ? '1' : '0',
      MERCY_LONG: kind === 'error' ? '1' : '0',
    },
  }
}
