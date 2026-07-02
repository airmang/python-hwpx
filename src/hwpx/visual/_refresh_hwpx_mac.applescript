-- SPDX-License-Identifier: Apache-2.0
-- Mac Hancom field-refresh backend (M7 native TOC / cross-references).
--
-- Opens an .hwpx IN PLACE, lets Hancom regenerate any dirty="1" fields
-- (measured semantics: a dirty TABLEOFCONTENTS is rebuilt on open — entries,
-- styles, and page numbers recomputed by Hancom itself; CROSSREF caches
-- recompute automatically), saves the document back over the same path
-- (파일 > 저장하기), and closes it.
--
-- Why save-then-close instead of exporting a PDF from the regenerating
-- session: this Hancom build crashes when PDF export runs right after an
-- open-time TOC regeneration (measured: deterministic %%EOF-less torsos, then
-- the process dies). The refreshed FILE is stable; render it in a fresh
-- session afterwards.
--
-- Usage:  osascript _refresh_hwpx_mac.applescript <doc.hwpx> [timeoutSecs]
-- Output: "OK" on success; "ERR: <reason>" otherwise.

property procName : "Hancom Office HWP"
property appName : "Hancom Office HWP"
property fileMenuName : "파일"
property saveItemName : "저장하기"
property closeDocPrefix : "문서 닫기"

on run argv
	if (count of argv) < 1 then return "ERR: usage: <doc.hwpx> [timeoutSecs]"
	set inputPath to item 1 of argv
	set timeoutSecs to 90
	if (count of argv) ≥ 2 then
		try
			set timeoutSecs to (item 2 of argv) as integer
		end try
	end if
	set inputBase to do shell script "basename " & quoted form of inputPath

	try
		do shell script "open -a " & quoted form of appName & " " & quoted form of inputPath
		if not (waitForWindowNamed(inputBase, timeoutSecs)) then
			return "ERR: document window did not open: " & inputBase
		end if
		-- Let the dirty-field regeneration settle before saving.
		delay 3

		clickFileMenuItem(saveItemName, false)
		delay 2
		-- A compat/format sheet may appear on save: accept the default.
		pressReturnOnAnySheet()
		delay 1

		clickFileMenuItem(closeDocPrefix, true)
		delay 1
		-- If a save-changes sheet still appears, discard (we already saved).
		dismissDontSaveSheetIfPresent()
		return "OK"
	on error errMsg number errNum
		try
			clickFileMenuItem(closeDocPrefix, true)
			dismissDontSaveSheetIfPresent()
		end try
		return "ERR: " & errMsg & " (" & errNum & ")"
	end try
end run

on clickFileMenuItem(itemName, prefixMatch)
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
				set miName to (name of mi as string)
				if (prefixMatch and miName starts with itemName) or (not prefixMatch and miName is itemName) then
					click mi
					return
				end if
			end try
		end repeat
		error "menu item not found: " & itemName
	end tell
end clickFileMenuItem

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

on pressReturnOnAnySheet()
	repeat 4 times
		set found to false
		try
			tell application "System Events" to tell process procName
				repeat with i from 1 to (count of windows)
					try
						if (count of sheets of window i) > 0 then
							set frontmost to true
							key code 36 -- Return = default button
							set found to true
						end if
					end try
				end repeat
			end tell
		end try
		if not found then return false
		delay 0.8
	end repeat
	return true
end pressReturnOnAnySheet

on dismissDontSaveSheetIfPresent()
	repeat 6 times
		set handled to false
		try
			tell application "System Events" to tell process procName
				repeat with i from 1 to (count of windows)
					try
						if (count of sheets of window i) > 0 then
							repeat with b in buttons of (sheet 1 of window i)
								try
									set bn to (name of b as string)
									if bn contains "안 함" or bn contains "안함" then
										click b
										set handled to true
									end if
								end try
							end repeat
						end if
					end try
				end repeat
			end tell
		end try
		if handled then return true
		delay 0.3
	end repeat
	return false
end dismissDontSaveSheetIfPresent
