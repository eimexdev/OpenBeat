local OpenBeat = {}

local function dirname(path)
  return path:match("^(.*)/[^/]+$") or "."
end

local function join_path(...)
  local items = { ... }
  return table.concat(items, "/")
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
  return "'" .. tostring(value):gsub("'", [['"'"']]) .. "'"
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
  local path = os.getenv("HOME") .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/OpenBeat.log"
  local handle = io.open(path, "a")
  if not handle then
    return
  end
  handle:write(os.date("%Y-%m-%d %H:%M:%S "), tostring(message), "\n")
  handle:close()
end

local function run_command(command)
  log("RUN " .. command)
  local handle = assert(io.popen(command .. " 2>&1", "r"))
  local output = handle:read("*a")
  local _, _, code = handle:close()
  log(output)
  if code ~= 0 and code ~= nil then
    error(output)
  end
  return output
end

local function temp_path(prefix, extension)
  local name = string.format("%s_%d_%d%s", prefix, os.time(), math.random(1000, 9999), extension or "")
  return "/tmp/" .. name
end

local function python_bin()
  if local_config.python_bin and file_exists(local_config.python_bin) then
    return local_config.python_bin
  end
  local candidate = join_path(repo_root(), ".venv", "bin", "python")
  if file_exists(candidate) then
    return candidate
  end
  return "python3"
end

local function project_context()
  local resolve_app = resolve or app:GetResolve()
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

  local fps = timeline:GetSetting("timelineFrameRate") or project:GetSetting("timelineFrameRate")
  if type(fps) == "table" then
    fps = fps.timelineFrameRate or fps.FPS
  end
  fps = tonumber(fps)
  if not fps or fps <= 0 then
    error("Could not determine timeline frame rate.")
  end

  return resolve_app, project, timeline, fps
end

local function parse_timecode(tc, fps)
  local h, m, s, f = tc:match("(%d+):(%d+):(%d+):(%d+)")
  if not h then
    error("Unsupported timecode: " .. tostring(tc))
  end
  return (((tonumber(h) * 60) + tonumber(m)) * 60 + tonumber(s)) * fps + tonumber(f)
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

local function media_pool_path(item)
  local path = get_clip_property_value(item, "File Path")
  if not path or path == "" then
    error("Selected timeline item has no file path")
  end
  return path
end

local function clip_contains_frame(clip, frame)
  return clip:GetStart() <= frame and frame <= clip:GetEnd()
end

local function all_audio_segments_for_path(timeline, source_path)
  local matches = {}
  local track_count = timeline:GetTrackCount("audio")
  for track_index = 1, track_count do
    local items = timeline:GetItemListInTrack("audio", track_index)
    for _, item in ipairs(items) do
      local media = item:GetMediaPoolItem()
      if media then
        local path = media_pool_path(media)
        if path == source_path then
          table.insert(matches, {
            track_index = track_index,
            timeline_item = item,
            media_pool_item = media,
            start_frame = item:GetStart(),
            end_frame = item:GetEnd(),
            left_offset = item:GetLeftOffset() or 0,
          })
        end
      end
    end
  end
  return matches
end

local function source_at_playhead(timeline, fps)
  local playhead_frame = parse_timecode(timeline:GetCurrentTimecode(), fps)
  local track_count = timeline:GetTrackCount("audio")
  for track_index = 1, track_count do
    local items = timeline:GetItemListInTrack("audio", track_index)
    for _, item in ipairs(items) do
      if clip_contains_frame(item, playhead_frame) then
        local media = item:GetMediaPoolItem()
        if media then
          local path = media_pool_path(media)
          return path, item, media
        end
      end
    end
  end
  error("Place the playhead over a timeline audio clip before running OpenBeat.")
end

local function colors()
  return { "Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia" }
end

local function remove_openbeat_markers(holder)
  local markers = holder:GetMarkers() or {}
  for frame_id, _ in pairs(markers) do
    local custom = holder.GetMarkerCustomData and holder:GetMarkerCustomData(frame_id) or ""
    if type(custom) == "string" and custom:match("^OpenBeat:") then
      holder:DeleteMarkerAtFrame(frame_id)
    end
  end
end

local function round(value)
  return math.floor(value + 0.5)
end

local function analyze_source(source_path)
  local output = temp_path("openbeat_analysis", ".lua")
  local final_command = shell_quote(python_bin())
    .. " -m openbeat.cli analyze --audio "
    .. shell_quote(source_path)
    .. " --format lua --output "
    .. shell_quote(output)
  run_command(final_command)
  local analysis = dofile(output)
  os.remove(output)
  return analysis
end

local function beats_for_mode(analysis, mode)
  if mode == "raw" then
    return analysis.raw_beats
  end
  return analysis.quantized_beats
end

local function create_timeline_markers(mode)
  local _, _, timeline, fps = project_context()
  local source_path = source_at_playhead(timeline, fps)
  local analysis = analyze_source(source_path)
  local beats = beats_for_mode(analysis, mode)
  local segments = all_audio_segments_for_path(timeline, source_path)
  local marker_colors = colors()

  remove_openbeat_markers(timeline)

  local timeline_start = timeline:GetStartFrame()
  local created = 0
  for _, segment in ipairs(segments) do
    local source_zero_frame = segment.start_frame - segment.left_offset - timeline_start
    for index, beat in ipairs(beats) do
      local frame = round(beat * fps) + source_zero_frame
      local segment_start = segment.start_frame - timeline_start
      local segment_end = segment.end_frame - timeline_start
      if frame >= segment_start and frame <= segment_end then
        local color = marker_colors[((index - 1) % #marker_colors) + 1]
        timeline:AddMarker(frame, color, "OpenBeat " .. index, "Created by OpenBeat", 1.0, "OpenBeat:timeline")
        created = created + 1
      end
    end
  end

  print(string.format("OpenBeat created %d timeline markers for %s", created, source_path))
  log(string.format("Created %d timeline markers for %s", created, source_path))
end

local function create_clip_markers(mode)
  local _, _, timeline, fps = project_context()
  local source_path, _, media = source_at_playhead(timeline, fps)
  local analysis = analyze_source(source_path)
  local beats = beats_for_mode(analysis, mode)
  local segments = all_audio_segments_for_path(timeline, source_path)
  local marker_colors = colors()
  local clip_fps = numeric_clip_property(media, "FPS", fps)

  remove_openbeat_markers(media)
  for _, segment in ipairs(segments) do
    remove_openbeat_markers(segment.timeline_item)
  end

  for index, beat in ipairs(beats) do
    local frame = round(beat * clip_fps)
    local color = marker_colors[((index - 1) % #marker_colors) + 1]
    media:AddMarker(frame, color, "OpenBeat " .. index, "Created by OpenBeat", 1.0, "OpenBeat:clip")
    for _, segment in ipairs(segments) do
      local source_start = segment.timeline_item:GetSourceStartFrame()
      local source_end = segment.timeline_item:GetSourceEndFrame()
      if source_start and source_end and frame >= source_start and frame <= source_end then
        local clip_offset = frame - source_start
        segment.timeline_item:AddMarker(clip_offset, color, "OpenBeat " .. index, "Created by OpenBeat", 1.0, "OpenBeat:clip-item")
      end
    end
  end

  print(string.format("OpenBeat created %d clip markers for %s", #beats, source_path))
  log(string.format("Created %d clip markers for %s", #beats, source_path))
end

local function output_path_for(source_path, suffix, extension)
  local base = source_path:gsub("%.[^%.]+$", "")
  return base .. suffix .. extension
end

local function render_click_track(source_path, mode)
  local suffix = mode == "raw" and ".openbeat-raw-clicks" or ".openbeat-clicks"
  local output = output_path_for(source_path, suffix, ".wav")
  local command = shell_quote(python_bin())
    .. " -m openbeat.cli click-track --audio "
    .. shell_quote(source_path)
    .. " --mode "
    .. shell_quote(mode)
    .. " --output "
    .. shell_quote(output)
  run_command(command)
  return output
end

local function find_media_pool_item_by_path(resolve_app, source_path)
  local imported = resolve_app:GetMediaStorage():AddItemListToMediaPool(source_path)
  return first_value(imported)
end

local function create_click_audio(mode)
  local resolve_app, project, timeline, fps = project_context()
  local source_path = source_at_playhead(timeline, fps)
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
    states[track_index] = timeline:GetIsTrackEnabled(track_type, track_index)
  end
  return states
end

local function restore_track_enabled(timeline, track_type, states)
  for track_index, enabled in pairs(states) do
    timeline:SetTrackEnable(track_type, track_index, enabled)
  end
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
  for track_index = 1, timeline:GetTrackCount("video") do
    timeline:SetTrackEnable("video", track_index, false)
  end
  for track_index = 1, timeline:GetTrackCount("subtitle") do
    timeline:SetTrackEnable("subtitle", track_index, track_index == target_track)
  end

  local before_count = track_item_count(timeline, "subtitle", target_track)
  local clip_info = {
    mediaPoolItem = subtitle_item,
    startFrame = 0,
    recordFrame = timeline:GetStartFrame(),
    trackIndex = target_track,
  }
  local appended = project:GetMediaPool():AppendToTimeline({ clip_info })
  local after_count = track_item_count(timeline, "subtitle", target_track)

  restore_track_enabled(timeline, "video", video_states)
  restore_track_enabled(timeline, "subtitle", subtitle_states)

  if after_count <= before_count then
    local append_text = appended and "returned a result" or "returned nil"
    return false, "Resolve imported the subtitle file but did not place it on the timeline (" .. append_text .. ")."
  end

  return true, nil
end

local function format_srt_time(seconds)
  local total_ms = math.floor(seconds * 1000)
  local ms = total_ms % 1000
  local total_s = math.floor(total_ms / 1000)
  local s = total_s % 60
  local total_m = math.floor(total_s / 60)
  local m = total_m % 60
  local h = math.floor(total_m / 60)
  return string.format("%02d:%02d:%02d,%03d", h, m, s, ms)
end

local function unique_sorted(list)
  table.sort(list)
  local result = {}
  local last = nil
  for _, value in ipairs(list) do
    if last == nil or math.abs(value - last) > 0.0005 then
      table.insert(result, value)
      last = value
    end
  end
  return result
end

local function export_subtitles(mode)
  local resolve_app, project, timeline, fps = project_context()
  local source_path = source_at_playhead(timeline, fps)
  local analysis = analyze_source(source_path)
  local beats = beats_for_mode(analysis, mode)
  local segments = all_audio_segments_for_path(timeline, source_path)
  local timeline_start = timeline:GetStartFrame()
  local subtitle_beats = {}

  for _, segment in ipairs(segments) do
    local source_zero = segment.start_frame - segment.left_offset - timeline_start
    local rel_start = segment.start_frame - timeline_start
    local rel_end = segment.end_frame - timeline_start
    for _, beat in ipairs(beats) do
      local beat_time = beat + (source_zero / fps)
      if beat_time >= (rel_start / fps) and beat_time <= (rel_end / fps) then
        table.insert(subtitle_beats, beat_time)
      end
    end
  end

  subtitle_beats = unique_sorted(subtitle_beats)
  local output_lines = {}
  local counter = 1
  local absolute_offset = timeline_start / fps
  if subtitle_beats[1] and subtitle_beats[1] > 0 then
    table.insert(output_lines, tostring(counter))
    table.insert(output_lines, format_srt_time(absolute_offset) .. " --> " .. format_srt_time(absolute_offset + subtitle_beats[1]))
    table.insert(output_lines, "before first beat")
    table.insert(output_lines, "")
    counter = counter + 1
  end

  local beat_number = 1
  local previous = nil
  for _, beat_time in ipairs(subtitle_beats) do
    if previous ~= nil then
      table.insert(output_lines, tostring(counter))
      table.insert(output_lines, format_srt_time(absolute_offset + previous) .. " --> " .. format_srt_time(absolute_offset + beat_time))
      table.insert(output_lines, "beat " .. beat_number)
      table.insert(output_lines, ((beat_number - 1) % 4 + 1) .. "/4")
      table.insert(output_lines, ((beat_number - 1) % 8 + 1) .. "/8")
      table.insert(output_lines, ((beat_number - 1) % 16 + 1) .. "/16")
      table.insert(output_lines, "")
      counter = counter + 1
      beat_number = beat_number + 1
    end
    previous = beat_time
  end

  local suffix = mode == "raw" and ".openbeat-raw" or ".openbeat"
  local output = output_path_for(source_path, suffix, ".srt")
  local handle = assert(io.open(output, "w"))
  handle:write(table.concat(output_lines, "\n"))
  handle:close()
  local imported, reason = import_subtitles_to_timeline(resolve_app, project, timeline, output)
  if imported then
    print("OpenBeat wrote subtitles to " .. output .. " and placed them on a subtitle track.")
    log("Exported subtitles to " .. output .. " and placed them on timeline")
  else
    print("OpenBeat wrote subtitles to " .. output .. ". " .. reason)
    log("Exported subtitles to " .. output .. " but did not place them on timeline: " .. reason)
  end
end

function OpenBeat.run(action, mode)
  math.randomseed(os.time())
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
    error(result)
  end

  return result
end

return OpenBeat
