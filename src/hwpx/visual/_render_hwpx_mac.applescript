-- SPDX-License-Identifier: Apache-2.0
-- Mac Hancom (한컴오피스 한글) render backend for the VisualComplete oracle.
--
-- This build of Hancom Office HWP (com.hancom.office.hwp12.mac.general) ships
-- NO AppleScript dictionary (sdef) and NO headless convert CLI, so PDF export is
-- GUI-only. This script drives that GUI deterministically through System Events
-- (UI scripting), the Mac analogue of the Windows COM backend (_render_hwpx.ps1).
--
-- Flow, anchored on STABLE MENU-ITEM NAMES (prefix match), not pixels:
--   open <input>  ->  파일 (File) > "PDF로 저장하기..."  ->  NSSavePanel
--   -> Return (= the default 저장 button)  ->  파일 > "문서 닫기"
--
-- Why no typing is needed: the save panel is document-relative — it pre-fills
--   위치 (location) = the input file's directory and the name field = the input
--   stem. The Python caller therefore STAGES the input as <out_dir>/<out_stem>.hwpx,
--   so pressing 저장 writes exactly <out_dir>/<out_stem>.pdf. The caller also
--   pre-deletes the target, so the "대치(replace)?" sheet never appears in normal
--   operation; it is still dismissed defensively here. A "문서 닫기" save-changes
--   prompt is likewise discarded (we only exported; the doc is unmodified).
--
-- Usage:  osascript _render_hwpx_mac.applescript <input.hwpx> <out.pdf> [timeoutSecs]
-- Output: prints "OK" on success; prints "ERR: <reason>" and exits 1 otherwise.

property procName : "Hancom Office HWP"
property appName : "Hancom Office HWP"
property pdfDialogTitle : "PDF로 저장하기"
property fileMenuName : "파일"
property savePdfPrefix : "PDF로 저장하기"
property closeDocPrefix : "문서 닫기"

on run argv
	if (count of argv) < 2 then return "ERR: usage: <input.hwpx> <out.pdf> [timeoutSecs]"
	set inputPath to item 1 of argv
	set outPdf to item 2 of argv
	set timeoutSecs to 90
	if (count of argv) ≥ 3 then
		try
			set timeoutSecs to (item 3 of argv) as integer
		end try
	end if

	set inputBase to do shell script "basename " & quoted form of inputPath

	try
		-- 1) Open the staged input. LaunchServices focuses Hancom (launching it
		--    if needed) and opens the document.
		do shell script "open -a " & quoted form of appName & " " & quoted form of inputPath

		-- 2) Wait for the document window to exist.
		if not (waitForWindowNamed(inputBase, timeoutSecs)) then
			return "ERR: document window did not open: " & inputBase
		end if

		-- 3) 파일 > "PDF로 저장하기..."  (open the export save panel)
		clickFileMenuItemByPrefix(savePdfPrefix)

		-- 4) Wait for the export dialog.
		if not (waitForWindowNamed(pdfDialogTitle, 30)) then
			return "ERR: PDF save dialog did not appear"
		end if
		delay 0.4

		-- 5) Press Return = the default 저장 button (no typing: panel is
		--    pre-filled with 위치=out_dir, name=out_stem from the staged input).
		tell application "System Events" to tell process procName
			set frontmost to true
			delay 0.3
			key code 36 -- Return
		end tell

		-- 6) Defensive: a "대치(replace)?" sheet only appears if the target still
		--    exists. Dismiss it (대치) if present, then wait for the file.
		dismissOverwriteSheetIfPresent()

		-- 7) The render is asynchronous — wait until the PDF lands at out_pdf and
		--    the dialog has closed.
		set wrote to waitForFile(outPdf, timeoutSecs)
		waitForWindowGone(pdfDialogTitle, 15)

		-- 8) Always close the document so the next render starts from a clean
		--    session, even if the wait above was noisy. Discard any save-changes
		--    prompt (we only exported; the doc content is unmodified).
		try
			clickFileMenuItemByPrefix(closeDocPrefix)
			dismissCloseSheetIfPresent()
		end try

		if not wrote then return "ERR: PDF not written to " & outPdf
		return "OK"
	on error errMsg number errNum
		-- Best-effort cleanup so a mid-flow error doesn't leak an open document.
		try
			clickFileMenuItemByPrefix(closeDocPrefix)
			dismissCloseSheetIfPresent()
		end try
		return "ERR: " & errMsg & " (" & errNum & ")"
	end try
end run

-- Find the 파일 menu by name, then click the first menu item whose name starts
-- with `prefix`. Name-based so it survives index drift across Hancom versions.
on clickFileMenuItemByPrefix(prefix)
	tell application "System Events" to tell process procName
		set frontmost to true
		delay 0.2
		set fileMenu to missing value
		repeat with mbi in menu bar items of menu bar 1
			if (name of mbi as string) is fileMenuName then
				set fileMenu to menu 1 of mbi
				exit repeat
			end if
		end repeat
		if fileMenu is missing value then error "menu '" & fileMenuName & "' not found"
		repeat with mi in menu items of fileMenu
			try
				if (name of mi as string) starts with prefix then
					click mi
					return
				end if
			end try
		end repeat
		error "menu item not found: " & prefix
	end tell
end clickFileMenuItemByPrefix

-- Window polling uses the ATOMIC ``name of windows`` string list (never a held
-- ``repeat with w in windows`` element reference): the save dialog appears and
-- disappears mid-flow, so a lazily-resolved ``item N of every window`` can become
-- an invalid index (-1719). Snapshotting names and guarding with ``try`` is
-- race-safe.
on windowNames()
	try
		tell application "System Events" to tell process procName
			return (name of windows) as list
		end tell
	on error
		return {}
	end try
end windowNames

on listContains(theList, theValue)
	repeat with x in theList
		if (x as string) is theValue then return true
	end repeat
	return false
end listContains

on waitForWindowNamed(winName, secs)
	repeat (secs * 2) times
		if listContains(windowNames(), winName) then return true
		delay 0.5
	end repeat
	return false
end waitForWindowNamed

on waitForWindowGone(winName, secs)
	repeat (secs * 2) times
		if not (listContains(windowNames(), winName)) then return true
		delay 0.5
	end repeat
	return false
end waitForWindowGone

on waitForFile(p, secs)
	-- size>0 alone is NOT completion: Hancom streams the PDF asynchronously and
	-- closing the document mid-write truncates it (measured: a TOC-regenerating
	-- document produced a deterministic %%EOF-less torso). Require the PDF
	-- trailer marker so the export has actually finished before we move on.
	repeat (secs * 2) times
		if (do shell script "test -s " & quoted form of p & " && tail -c 64 " & quoted form of p & " | grep -q '%%EOF' && echo 1 || echo 0") is "1" then
			return true
		end if
		delay 0.5
	end repeat
	return false
end waitForFile

-- The overwrite confirmation is a SHEET of the PDF dialog window; its buttons are
-- directly accessible (unlike the save panel's own nested buttons). Re-fetch the
-- window by name each pass and guard, since it is being torn down concurrently.
on dismissOverwriteSheetIfPresent()
	repeat 6 times
		try
			tell application "System Events" to tell process procName
				set dlg to (first window whose name is pdfDialogTitle)
				if (count of sheets of dlg) > 0 then
					tell sheet 1 of dlg
						if (exists button "대치") then
							click button "대치"
							return true
						end if
					end tell
				end if
			end tell
		end try
		delay 0.3
	end repeat
	return false
end dismissOverwriteSheetIfPresent

-- If closing surfaces a save-changes sheet, discard (저장 안 함 / 안 함). We only
-- exported a PDF, so the document content is unchanged.
on dismissCloseSheetIfPresent()
	repeat 6 times
		set handled to false
		try
			tell application "System Events" to tell process procName
				repeat with wn in windowNames()
					set w to (first window whose name is (wn as string))
					if (count of sheets of w) > 0 then
						repeat with b in buttons of (sheet 1 of w)
							set bn to (name of b as string)
							if bn contains "안 함" or bn contains "안함" then
								click b
								set handled to true
							end if
						end repeat
					end if
				end repeat
			end tell
		end try
		if handled then return true
		delay 0.3
	end repeat
	return false
end dismissCloseSheetIfPresent
