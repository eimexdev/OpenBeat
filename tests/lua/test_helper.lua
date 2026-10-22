-- How OpenBeat runs its helper: failures must be detected without an exit status,
-- temporary files must not collide or linger, and output names must keep their folder.
local directory = assert(arg[1])
local open_file = io.open
io.open = function(path, mode)
  if tostring(path):match("OpenBeat%.log$") then return nil end
  return open_file(path, mode)
end

local OpenBeat = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatCommon.lua")
local function upvalue(fn, name)
  for index = 1, 200 do
    local key, value = debug.getupvalue(fn, index)
    if key == name then return value end
    if not key then break end
  end
  error("Missing upvalue " .. name)
end
local analyze_source = upvalue(upvalue(OpenBeat.run, "create_timeline_markers"), "analyze_source")
local render_click_track = upvalue(upvalue(OpenBeat.run, "create_click_audio"), "render_click_track")
local run_command = upvalue(upvalue(analyze_source, "run_helper"), "run_command")
local temp_path = upvalue(analyze_source, "temp_path")
local output_path_for = upvalue(render_click_track, "output_path_for")

local function exists(path)
  local handle = open_file(path, "rb")
  if handle then handle:close() end
  return handle ~= nil
end
local function write(path, text)
  local handle = assert(open_file(path, "wb")); handle:write(text); handle:close()
end
local function read(path)
  local handle = assert(open_file(path, "rb")); local text = handle:read("*a"); handle:close(); return text
end
local function fails(fn, ...)
  local ok, message = pcall(fn, ...)
  assert(not ok, "Expected a failure")
  return tostring(message)
end

-- Fake helper. `behavior` decides what it writes and prints and how it exits; like the
-- shell, the success marker is printed only when the helper exits 0.
local behavior
local commands = {}
io.popen = function(command)
  table.insert(commands, command)
  local marker = assert(command:match("&& echo (OPENBEAT_HELPER_OK_%x+)$"), "Missing success marker")
  local output_path = assert(command:match("%-%-output '([^']+)'"))
  local result = behavior(output_path, command)
  local output = result.output or ""
  if (result.exit or 0) == 0 then output = output .. marker .. "\r\n" end
  return {
    read = function() return output end,
    close = function()
      if result.lua52 then
        if (result.exit or 0) == 0 then return true, "exit", 0 end
        return nil, "exit", result.exit
      end
      return true -- Lua 5.1 and LuaJIT
    end,
  }
end

local analysis_text = "return { duration_seconds = 2, raw_beats = { 0.5 }, quantized_beats = { 0.5 } }"
local traceback = table.concat({
  "Traceback (most recent call last):",
  '  File "openbeat/cli.py", line 154, in analyze_command',
  "    analysis = load_or_analyze(args.audio)",
  "soundfile.LibsndfileError: Error opening 'song.wav': Format not recognised.",
  "[PYI-4242:ERROR] Failed to execute script 'cli' due to unhandled exception!",
}, "\n")

-- Success: the analysis is read and its temporary file removed.
local analysis_path
behavior = function(path) analysis_path = path; write(path, analysis_text); return {} end
local analysis = analyze_source("/Media/song.wav")
assert(analysis.raw_beats[1] == 0.5 and analysis.duration_seconds == 2)
assert(not exists(analysis_path), "Analysis file must be removed")

-- The analysis file gets no access to globals.
behavior = function(path) write(path, "return { raw_beats = { os and 1 or 0 }, quantized_beats = {} }"); return {} end
assert(analyze_source("/Media/song.wav").raw_beats[1] == 0)

-- A crashing helper reports its error, not the traceback or a missing temporary file.
behavior = function(path) analysis_path = path; return { output = traceback, exit = 1 } end
local message = fails(analyze_source, "/Media/song.wav")
assert(message:find("Format not recognised", 1, true), message)
assert(not message:find("Traceback", 1, true) and not message:find("cli.py", 1, true), message)
assert(not message:find("PYI", 1, true) and not message:find("cannot open", 1, true), message)
assert(not exists(analysis_path))

-- A helper that failed after writing part of its output is still a failure.
behavior = function(path) analysis_path = path; write(path, analysis_text); return { output = "Killed", exit = 137 } end
message = fails(analyze_source, "/Media/song.wav")
assert(message:find("Killed", 1, true), message)
assert(not exists(analysis_path), "Analysis file must be removed after a failure")

-- An unreadable analysis file is reported and removed.
behavior = function(path) analysis_path = path; write(path, "return {"); return {} end
message = fails(analyze_source, "/Media/song.wav")
assert(message:find("could not read the beat analysis", 1, true), message)
assert(not exists(analysis_path))
behavior = function(path) analysis_path = path; write(path, "local boom = nil; return boom.beats"); return {} end
message = fails(analyze_source, "/Media/song.wav")
assert(message:find("boom", 1, true), message)
assert(not exists(analysis_path))

-- Missing analysis output despite success.
behavior = function() return { output = "done" } end
assert(fails(analyze_source, "/Media/song.wav"):find("could not read the beat analysis", 1, true))

-- A runtime that reports exit codes (Lua 5.2+) is honored as well.
behavior = function(path) write(path, analysis_text); return { output = "usage: openbeat\nopenbeat: error: bad", exit = 2, lua52 = true } end
message = fails(analyze_source, "/Media/song.wav")
assert(message:find("exit code 2", 1, true) and message:find("openbeat: error: bad", 1, true), message)
behavior = function(path) write(path, analysis_text); return { lua52 = true } end
assert(analyze_source("/Media/song.wav").quantized_beats[1] == 0.5)

-- Without a traceback, the last lines of output are shown; empty output is explained.
behavior = function() return { output = "one\ntwo\nthree\nfour\n", exit = 1 } end
message = fails(run_command, "helper --output '/x'")
assert(message:find("two\nthree\nfour", 1, true) and not message:find("one", 1, true), message)
behavior = function() return { exit = 1 } end
assert(fails(run_command, "helper --output '/x'"):find("printed no error message", 1, true))
behavior = function() return { output = "progress\n" } end
assert(run_command("helper --output '/x'") == "progress")

-- A failed click track render must not hand back the previous file.
local source = directory .. "/song.wav"
local stale = directory .. "/song.openbeat-clicks.wav"
write(stale, "previous click track")
behavior = function() return { output = "OSError: [Errno 28] No space left on device", exit = 1 } end
message = fails(render_click_track, source, "quantized")
assert(message:find("No space left on device", 1, true), message)
behavior = function(path) write(path, ""); return {} end
assert(fails(render_click_track, source, "quantized"):find("did not write the click track", 1, true))
behavior = function(path) write(path, "new click track"); return {} end
assert(render_click_track(source, "quantized") == stale and read(stale) == "new click track")

-- Temporary names never repeat, even within one second, and skip existing files.
local seen = {}
for _ = 1, 200 do
  local path = temp_path("openbeat_analysis", ".lua")
  assert(not seen[path], "Temporary path repeated: " .. path)
  assert(path:match("openbeat_analysis_[^/\\]+%.lua$"), path)
  seen[path] = true
end
local getenv = os.getenv
os.getenv = function(name) if name == "TMPDIR" then return directory .. "/" end return getenv(name) end
local first = temp_path("openbeat_analysis", ".lua")
assert(first:sub(1, #directory + 1) == directory .. "/" and not first:find("//", 1, true), first)
os.getenv = getenv

-- Output names only replace the extension of the file name.
local cases = {
  { "/Media/song.mp3", "/Media/song.openbeat-clicks.wav" },
  { "/Media/my.music/track", "/Media/my.music/track.openbeat-clicks.wav" },
  { "C:\\Media\\my.music\\track", "C:\\Media\\my.music\\track.openbeat-clicks.wav" },
  { "C:\\Media\\my.music\\song.final.wav", "C:\\Media\\my.music\\song.final.openbeat-clicks.wav" },
  { "/Media/.hidden", "/Media/.hidden.openbeat-clicks.wav" },
  { "song.wav", "song.openbeat-clicks.wav" },
}
for _, case in ipairs(cases) do
  local actual = output_path_for(case[1], ".openbeat-clicks", ".wav")
  assert(actual == case[2], case[1] .. " -> " .. actual)
end
