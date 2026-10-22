local OpenBeat = {}

local function is_windows()
  return package.config:sub(1, 1) == "\\"
end

local function path_sep()
  if is_windows() then
    return "\\"
  end
  return "/"
end

local function dirname(path)
  local normalized = tostring(path):gsub("\\", "/")
  return normalized:match("^(.*)/[^/]+$") or "."
end

local function join_path(...)
  local items = { ... }
  return table.concat(items, path_sep())
end

local function file_exists(path)
  local handle = io.open(path, "r")
  if handle then
    handle:close()
    return true
  end
  return false
end

local function first_value(items)
  if type(items) ~= "table" then
    return nil
  end
  for _, value in pairs(items) do
    return value
  end
  return nil
end

local function shell_quote(value)
  local as_string = tostring(value)
  if is_windows() then
    return '"' .. as_string:gsub('"', '\\"') .. '"'
  end
  return "'" .. as_string:gsub("'", [['"'"']]) .. "'"
end

local function current_script_path()
  local info = debug.getinfo(2, "S") or debug.getinfo(3, "S")
  if not info or not info.source or info.source:sub(1, 1) ~= "@" then
    error("Unable to determine current script path")
  end
  return info.source:sub(2)
end

local function script_dir()
  return dirname(current_script_path())
end

local function load_local_config()
  local config_path = join_path(script_dir(), "OpenBeatConfig.local.lua")
  if file_exists(config_path) then
    return dofile(config_path)
  end
  return {}
end

local local_config = load_local_config()
local Timing = dofile(join_path(script_dir(), "OpenBeatTiming.lua"))
local Source = dofile(join_path(script_dir(), "OpenBeatSource.lua"))
local Subtitles = dofile(join_path(script_dir(), "OpenBeatSubtitles.lua"))
local Markers = dofile(join_path(script_dir(), "OpenBeatMarkers.lua"))

local function repo_root()
  if local_config.repo_root then
    return local_config.repo_root
  end
  local path = script_dir()
  for _ = 1, 4 do
    path = dirname(path)
  end
  return path
end

local function log(message)
  local home = os.getenv("HOME")
  if not home or home == "" then
    home = os.getenv("USERPROFILE")
  end
  if not home or home == "" then
    return
  end

  local path
  if is_windows() then
    local appdata = os.getenv("APPDATA")
    if appdata and appdata ~= "" then
      path = join_path(appdata, "Blackmagic Design", "DaVinci Resolve", "Support", "logs", "OpenBeat.log")
    else
      path = join_path(home, "AppData", "Roaming", "Blackmagic Design", "DaVinci Resolve", "Support", "logs", "OpenBeat.log")
    end
  else
    path = join_path(home, "Library", "Application Support", "Blackmagic Design", "DaVinci Resolve", "logs", "OpenBeat.log")
  end
  local handle = io.open(path, "a")
  if not handle then
    return
  end
  handle:write(os.date("%Y-%m-%d %H:%M:%S "), tostring(message), "\n")
  handle:close()
end

local random_seeded = false

local function seed_random()
  if random_seeded then
    return
  end
  random_seeded = true
  -- A fresh table's address varies between processes (ASLR), unlike os.time() alone.
  local address = tonumber(tostring({}):match("(%x+)$") or "0", 16) or 0
  math.randomseed((os.time() + math.floor(os.clock() * 1000000) + address) % 2147483647)
  for _ = 1, 4 do
    math.random()
  end
end

local function random_token()
  seed_random()
  return string.format("%06x%06x", math.random(0, 0xffffff), math.random(0, 0xffffff))
end

-- Lua 5.1 and LuaJIT, which Resolve runs, return only `true` from a popen handle's
-- close(), so the helper's exit status is not available there. The shell echoes this
-- marker only when the helper exits with status 0 (`&&` is evaluated at run time by
-- both sh and cmd.exe), so a missing marker means the helper failed.
local SUCCESS_MARKER = "OPENBEAT_HELPER_OK"
local MAX_DETAIL_LENGTH = 600

-- The helper's error, without the Python traceback frames around it.
local function failure_detail(output)
  local lines = {}
  local traceback = false
  for line in tostring(output or ""):gmatch("[^\r\n]+") do
    if line:match("^Traceback %(most recent call last%)") then
      traceback = true
    elseif line:match("^%s") or (traceback and line:match("^%[PYI%-")) then
      -- Traceback frames, and the bootloader's note that the script raised.
    elseif line:match("%S") then
      table.insert(lines, line)
    end
  end
  if #lines == 0 then
    return "it printed no error message"
  end
  local keep = traceback and 1 or 3
  local detail = table.concat(lines, "\n", math.max(1, #lines - keep + 1))
  if #detail > MAX_DETAIL_LENGTH then
    detail = "..." .. detail:sub(-MAX_DETAIL_LENGTH)
  end
  return detail
end

local function run_command(command)
  log("RUN " .. command)
  local marker = SUCCESS_MARKER .. "_" .. random_token()
  local popen_command = command .. " 2>&1 && echo " .. marker
  if is_windows() and command:sub(1, 1) == '"' then
    popen_command = '"' .. popen_command .. '"'
  end
  local handle, open_error = io.popen(popen_command, "r")
  if not handle then
    error("OpenBeat could not start its helper: " .. tostring(open_error), 0)
  end
  local output = handle:read("*a") or ""
  -- Lua 5.2+ (and LuaJIT built with 5.2 compatibility) also report the exit status.
  local _, _, code = handle:close()
  log(output)
  local helper_output, succeeded = output:gsub("%s*" .. marker .. "%s*$", "")
  local failed_code = type(code) == "number" and code ~= 0 and code or nil
  if succeeded == 0 or failed_code then
    local status = failed_code and (" (exit code " .. tostring(failed_code) .. ")") or ""
    error("OpenBeat's helper failed" .. status .. ": " .. failure_detail(helper_output)
      .. "\nThe full output is in OpenBeat.log.", 0)
  end
  return helper_output
end

local function temp_dir()
  local names = is_windows() and { "TEMP", "TMP" } or { "TMPDIR", "TMP", "TEMP" }
  for _, name in ipairs(names) do
    local value = os.getenv(name)
    if value and value ~= "" then
      return (value:gsub("[/\\]+$", ""))
    end
  end
  if is_windows() then
    local local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata and local_appdata ~= "" then
      return join_path(local_appdata, "Temp")
    end
    return "C:\\Windows\\Temp"
  end
  return "/tmp"
end

local temp_counter = 0

-- Lua 5.1 cannot create files exclusively, so the name must not be guessable or reused:
-- it combines the time, a per-session counter and a random token.
local function temp_path(prefix, extension)
  local base = temp_dir()
  for _ = 1, 20 do
    temp_counter = temp_counter + 1
    local name = string.format("%s_%d_%d_%s%s", prefix, os.time(), temp_counter, random_token(), extension or "")
    local path = join_path(base, name)
    if not file_exists(path) then
      return path
    end
  end
  error("OpenBeat could not choose an unused temporary file name in " .. base, 0)
end

local function file_size(path)
  local handle = io.open(path, "rb")
  if not handle then
    return nil
  end
  local size = handle:seek("end")
  handle:close()
  return size
end

local function python_bin()
  if local_config.python_bin and file_exists(local_config.python_bin) then
    return local_config.python_bin
  end
  local candidates = {
    join_path(repo_root(), ".venv", "bin", "python"),
    join_path(repo_root(), ".venv", "Scripts", "python.exe"),
  }
  for _, candidate in ipairs(candidates) do
    if file_exists(candidate) then
      return candidate
    end
  end
  return "python3"
end

local function command_prefix()
  local bin = python_bin()
  local name = string.lower(bin):match("[^/\\]+$") or ""
  name = name:gsub("%.exe$", "")
  if name == "python" or name:match("^python%d[%d%.]*$") then
    return shell_quote(bin) .. " -m openbeat.cli"
  end
  return shell_quote(bin)
end

local function project_context()
  local resolve_app = resolve or (app and app:GetResolve())
  if not resolve_app then
    error("Resolve API unavailable")
  end

  local project_manager = resolve_app:GetProjectManager()
  local project = project_manager and project_manager:GetCurrentProject()
  if not project then
    error("Open a project before running OpenBeat.")
  end

  local timeline = project:GetCurrentTimeline()
  if not timeline then
    error("Open a timeline before running OpenBeat.")
  end

  local setting = timeline:GetSetting("timelineFrameRate") or project:GetSetting("timelineFrameRate")
  local fps, drop_frame = Timing.frame_rate(setting)
  return resolve_app, project, timeline, fps, drop_frame
end

local function get_clip_property_value(clip, key)
  local value = clip:GetClipProperty(key)
  if type(value) == "table" then
    return value[key]
  end
  return value
end

local function numeric_clip_property(clip, key, fallback)
  local value = tonumber(get_clip_property_value(clip, key))
  if value and value > 0 then
    return value
  end
  return fallback
end

-- The analysis file holds only a data table, so it runs without access to any globals.
local function load_analysis(path)
  local chunk, load_error = loadfile(path, "t", {})
  if not chunk then
    return nil, load_error
  end
  if setfenv then
    setfenv(chunk, {})
  end
  local ok, analysis = pcall(chunk)
  if not ok then
    return nil, analysis
  end
  if type(analysis) ~= "table" or type(analysis.raw_beats) ~= "table" or type(analysis.quantized_beats) ~= "table" then
    return nil, "the analysis file does not contain beat data"
  end
  return analysis
end

local function analyze_source(source_path)
  local output = temp_path("openbeat_analysis", ".lua")
  local final_command = command_prefix()
    .. " analyze --audio "
    .. shell_quote(source_path)
    .. " --format lua --output "
    .. shell_quote(output)
  local ran, run_error = pcall(run_command, final_command)
  local analysis, load_error
  if ran then
    analysis, load_error = load_analysis(output)
  end
  os.remove(output)
  if not ran then
    error(run_error, 0)
  end
  if not analysis then
    error("OpenBeat could not read the beat analysis of " .. source_path .. ": " .. tostring(load_error), 0)
  end
  return analysis
end

local function beats_for_mode(analysis, mode)
  if mode == "raw" then
    return analysis.raw_beats
  end
  return analysis.quantized_beats
end

local function create_timeline_markers(mode)
  local _, _, timeline, fps, drop_frame = project_context()
  local source_path = Source.at_playhead(timeline, fps, drop_frame)
  local analysis = analyze_source(source_path)
  local beats = beats_for_mode(analysis, mode)
  local segments = Source.segments_for_path(timeline, source_path)
  local created, skipped = Markers.replace_many({ {
    holder = timeline,
    plan = Markers.timeline_plan(beats, segments, fps, timeline:GetStartFrame()),
    custom_data = Markers.custom_data("timeline", source_path),
  } })
  local message = string.format("OpenBeat created %d timeline markers for %s; skipped %d occupied frames", created, source_path, skipped)
  print(message)
  log(message)
end

local function create_clip_markers(mode)
  local _, _, timeline, fps, drop_frame = project_context()
  local source_path, _, media = Source.at_playhead(timeline, fps, drop_frame)
  local analysis = analyze_source(source_path)
  local beats = beats_for_mode(analysis, mode)
  local segments = Source.segments_for_path(timeline, source_path)
  local clip_fps = numeric_clip_property(media, "FPS", fps)
  local groups = { {
    holder = media,
    plan = Markers.source_plan(beats, clip_fps, analysis.duration_seconds),
    custom_data = Markers.custom_data("clip", source_path),
    legacy_custom_data = "OpenBeat:clip",
  } }
  for _, segment in ipairs(segments) do
    table.insert(groups, {
      holder = segment.timeline_item,
      plan = Markers.clip_plan(beats, segment, fps, clip_fps),
      custom_data = Markers.custom_data("clip-item", source_path),
      legacy_custom_data = "OpenBeat:clip-item",
    })
  end
  local created, skipped = Markers.replace_many(groups)
  local message = string.format("OpenBeat created %d source and timeline clip markers for %s; skipped %d occupied frames", created, source_path, skipped)
  print(message)
  log(message)
end

-- Replaces the extension of the file name only, never a dot in a folder name.
local function output_path_for(source_path, suffix, extension)
  local folder, name = source_path:match("^(.*[/\\])([^/\\]*)$")
  if not folder then
    folder, name = "", source_path
  end
  local stem = name:match("^(.+)%.[^%.]+$") or name
  return folder .. stem .. suffix .. extension
end

local function render_click_track(source_path, mode)
  local suffix = mode == "raw" and ".openbeat-raw-clicks" or ".openbeat-clicks"
  local output = output_path_for(source_path, suffix, ".wav")
  local command = command_prefix()
    .. " click-track --audio "
    .. shell_quote(source_path)
    .. " --mode "
    .. shell_quote(mode)
    .. " --output "
    .. shell_quote(output)
  run_command(command)
  if (file_size(output) or 0) == 0 then
    error("OpenBeat's helper finished but did not write the click track " .. output, 0)
  end
  return output
end

local function find_media_pool_item_by_path(resolve_app, source_path)
  local imported = resolve_app:GetMediaStorage():AddItemListToMediaPool(source_path)
  return first_value(imported)
end

local function create_click_audio(mode)
  local resolve_app, project, timeline, fps, drop_frame = project_context()
  local source_path = Source.at_playhead(timeline, fps, drop_frame)
  local click_path = render_click_track(source_path, mode)
  local click_item = find_media_pool_item_by_path(resolve_app, click_path)
  if not click_item then
    error("OpenBeat could not import the generated click track.")
  end
  print("OpenBeat created beat click audio at " .. click_path .. " and imported it into the Media Pool.")
  log("Created beat click audio " .. click_path)
end

local function ensure_track_count(timeline, track_type, target_count)
  while timeline:GetTrackCount(track_type) < target_count do
    local added = timeline:AddTrack(track_type)
    if not added then
      return false
    end
  end
  return true
end

local function track_item_count(timeline, track_type, track_index)
  local items = timeline:GetItemListInTrack(track_type, track_index) or {}
  return #items, items
end

local function capture_track_enabled(timeline, track_type)
  local states = {}
  for track_index = 1, timeline:GetTrackCount(track_type) do
    local enabled = timeline:GetIsTrackEnabled(track_type, track_index)
    if type(enabled) ~= "boolean" then
      error("Could not read the " .. track_type .. " track state before subtitle placement.")
    end
    states[track_index] = enabled
  end
  return states
end

local function restore_track_enabled(timeline, track_type, states)
  local restored = true
  for track_index, enabled in pairs(states) do
    local ok, result = pcall(timeline.SetTrackEnable, timeline, track_type, track_index, enabled)
    if not ok or not result then restored = false end
  end
  return restored
end

local function import_subtitles_to_timeline(resolve_app, project, timeline, subtitle_path)
  local subtitle_item = first_value(project:GetMediaPool():ImportMedia({ subtitle_path }))
  if not subtitle_item then
    return false, "Resolve did not import the generated subtitle file."
  end

  resolve_app:OpenPage("edit")
  local target_track = timeline:GetTrackCount("subtitle") + 1
  if not ensure_track_count(timeline, "subtitle", target_track) then
    return false, "Resolve did not create a subtitle track."
  end

  if timeline.SetTrackName then
    timeline:SetTrackName("subtitle", target_track, "OpenBeat Subtitles")
  end

  local video_states = capture_track_enabled(timeline, "video")
  local subtitle_states = capture_track_enabled(timeline, "subtitle")
  local before_count = 0
  local clip_info = {
    mediaPoolItem = subtitle_item,
    startFrame = 0,
    recordFrame = timeline:GetStartFrame(),
    trackIndex = target_track,
  }
  local appended = nil
  local after_count = before_count
  local append_ok, append_error = pcall(function()
    for track_index = 1, timeline:GetTrackCount("video") do
      if not timeline:SetTrackEnable("video", track_index, false) then
        error("Could not disable a video track for subtitle placement.")
      end
    end
    for track_index = 1, timeline:GetTrackCount("subtitle") do
      if not timeline:SetTrackEnable("subtitle", track_index, track_index == target_track) then
        error("Could not select the subtitle track for placement.")
      end
    end
    before_count = track_item_count(timeline, "subtitle", target_track)
    appended = project:GetMediaPool():AppendToTimeline({ clip_info })
    after_count = track_item_count(timeline, "subtitle", target_track)
  end)

  local video_restored = restore_track_enabled(timeline, "video", video_states)
  local subtitles_restored = restore_track_enabled(timeline, "subtitle", subtitle_states)
  if not video_restored or not subtitles_restored then
    return false, "Resolve could not restore all track-enable states after subtitle placement. Check the video and subtitle tracks."
  end

  if not append_ok then
    return false, "Resolve failed while placing the subtitle file on the timeline: " .. tostring(append_error)
  end

  if after_count <= before_count then
    local append_text = appended and "returned a result" or "returned nil"
    return false, "Resolve imported the subtitle file but did not place it on the timeline (" .. append_text .. ")."
  end

  return true, nil
end

local function export_subtitles(mode)
  local resolve_app, project, timeline, fps, drop_frame = project_context()
  local source_path = Source.at_playhead(timeline, fps, drop_frame)
  local analysis = analyze_source(source_path)
  local beats = beats_for_mode(analysis, mode)
  local segments = Source.segments_for_path(timeline, source_path)
  local cues = Subtitles.plan(beats, segments, fps, timeline:GetStartFrame())

  local suffix = mode == "raw" and ".openbeat-raw" or ".openbeat"
  local output = output_path_for(source_path, suffix, ".srt")
  local handle = assert(io.open(output, "w"))
  handle:write(Subtitles.to_srt(cues))
  handle:close()
  local import_ok, imported, reason = pcall(import_subtitles_to_timeline, resolve_app, project, timeline, output)
  if not import_ok then
    reason = "Resolve could not place the generated subtitle file: " .. tostring(imported)
    imported = false
  end
  if imported then
    print("OpenBeat wrote subtitles to " .. output .. " and placed them on a subtitle track.")
    log("Exported subtitles to " .. output .. " and placed them on timeline")
  else
    print("OpenBeat wrote subtitles to " .. output .. ". " .. reason)
    log("Exported subtitles to " .. output .. " but did not place them on timeline: " .. reason)
  end
end

function OpenBeat.run(action, mode)
  if mode ~= "raw" and mode ~= "quantized" then
    error("Unknown OpenBeat mode: " .. tostring(mode))
  end
  local ok, result = pcall(function()
    if action == "timeline_markers" then
      return create_timeline_markers(mode)
    end
    if action == "clip_markers" then
      return create_clip_markers(mode)
    end
    if action == "click_track" then
      return create_click_audio(mode)
    end
    if action == "subtitles" then
      return export_subtitles(mode)
    end
    error("Unknown OpenBeat action: " .. tostring(action))
  end)

  if not ok then
    log("ERROR " .. tostring(result))
    error(result, 0)
  end

  return result
end

return OpenBeat
