-- On Windows, Resolve's Lua starts processes through the ANSI code page, so UTF-8 text from
-- Resolve must reach the helper in a file, and the runtime is found by its ANSI spelling.
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
    if key == name then return value, index end
    if not key then break end
  end
  error("Missing upvalue " .. name)
end
local analyze_source = upvalue(upvalue(OpenBeat.run, "create_timeline_markers"), "analyze_source")
local render_click_track = upvalue(upvalue(OpenBeat.run, "create_click_audio"), "render_click_track")
local run_helper = upvalue(analyze_source, "run_helper")
local python_bin = upvalue(upvalue(run_helper, "command_prefix"), "python_bin")
local function exists(path)
  local handle = open_file(path, "rb")
  if handle then handle:close() end
  return handle ~= nil
end
local function read(path)
  local handle = assert(open_file(path, "rb")); local text = handle:read("*a"); handle:close(); return text
end

-- Installed configuration: the UTF-8 runtime path does not open through the ANSI code page,
-- so the ANSI spelling the installer recorded is used.
local ansi_runtime = directory .. "/openbeat~1.exe"
local utf8_runtime = directory .. "/Jos\195\169/openbeat.exe"
local _, config_index = upvalue(python_bin, "local_config")
debug.setupvalue(python_bin, config_index, { python_bin = utf8_runtime, python_bin_ansi = ansi_runtime })
local handle = assert(open_file(ansi_runtime, "wb"))
handle:close()

local posix_config = package.config
local getenv = os.getenv
package.config = "\\" .. posix_config:sub(2)
-- On Linux the backslash makes "tmp\\<name>" a file inside the test folder.
os.getenv = function(name) if name == "TEMP" then return directory .. "/tmp" end return getenv(name) end
assert(python_bin() == ansi_runtime)

local media = "C:\\M\195\186sica\\canci\195\179n.wav"
local behavior
local seen = {}
io.popen = function(command)
  assert(not command:find("[\128-\255]"), "Non-ASCII text on the command line: " .. command)
  local prefix = '""' .. ansi_runtime .. '" --args-file "'
  assert(command:sub(1, #prefix) == prefix, command)
  local args_path = assert(command:match('%-%-args%-file "([^"]+)"'))
  local marker = assert(command:match('&& echo (OPENBEAT_HELPER_OK_%x+)"$'), command)
  seen.args_path, seen.args, seen.command = args_path, read(args_path), command
  local result = behavior(command)
  local output = result.output or ""
  if not result.fail then output = output .. marker .. "\r\n" end
  return { read = function() return output end, close = function() return true end }
end

-- Analysis: the media path travels as UTF-8 JSON; the temporary output stays on the command line.
behavior = function(command)
  local output = assert(command:match('%-%-format lua %-%-output "([^"]+)" 2>&1'), command)
  assert(output:sub(1, #directory + 5) == directory .. "/tmp\\", output)
  local file = assert(open_file(output, "wb"))
  file:write("return { raw_beats = { 1 }, quantized_beats = { 2 } }")
  file:close()
  return {}
end
assert(analyze_source(media).quantized_beats[1] == 2)
assert(seen.args == '["analyze", "--audio", "C:\\\\M\195\186sica\\\\canci\195\179n.wav"]\n', seen.args)
assert(not exists(seen.args_path), "The arguments file must be removed")

-- Click track: every argument comes from Resolve, and Lua cannot check the non-ASCII output path.
behavior = function(command)
  assert(command:match('%-%-args%-file "[^"]+" 2>&1'), command)
  return { output = '{"output_path": "C:\\\\M\\u00fasica\\\\canci\\u00f3n.openbeat-clicks.wav"}' }
end
local click = render_click_track(media, "raw")
assert(click == "C:\\M\195\186sica\\canci\195\179n.openbeat-raw-clicks.wav", click)
assert(seen.args == '["click-track", "--audio", "C:\\\\M\195\186sica\\\\canci\195\179n.wav", "--mode", "raw", "--output", '
  .. '"C:\\\\M\195\186sica\\\\canci\195\179n.openbeat-raw-clicks.wav"]\n', seen.args)
assert(not exists(seen.args_path))

-- ...but an ASCII output path is still checked, and failures still remove the arguments file.
assert(not pcall(render_click_track, "C:\\Music\\missing.wav", "raw"))
behavior = function() return { output = "LibsndfileError: Error opening", fail = true } end
local ok, message = pcall(analyze_source, media)
assert(not ok and message:find("LibsndfileError", 1, true), message)
assert(not exists(seen.args_path))

-- JSON escaping of quotes and control characters.
behavior = function() return {} end
pcall(run_helper, { "a\"b", "tab\tnew\nline\1" }, {})
assert(seen.args == '["a\\"b", "tab\\tnew\\nline\\u0001"]\n', seen.args)

-- Elsewhere the ANSI spelling is ignored and arguments stay on the command line.
package.config = posix_config
os.getenv = getenv
assert(python_bin() ~= ansi_runtime)
