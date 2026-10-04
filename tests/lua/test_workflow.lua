local directory = assert(arg[1])
local source_path = directory .. "/test music 音楽.wav"
local open_file = io.open
io.open = function(path, mode)
  if tostring(path):match("OpenBeat%.log$") then return nil end
  return open_file(path, mode)
end
local function holder()
  return {
    markers = {},
    GetMarkers = function(self)
      local copy = {}
      for frame, marker in pairs(self.markers) do copy[frame] = marker end
      return copy
    end,
    DeleteMarkerAtFrame = function(self, frame) self.markers[frame] = nil; return true end,
    AddMarker = function(self, frame, color, name, note, duration, custom)
      if self.markers[frame] then return false end
      self.markers[frame] = { color = color, name = name, note = note, duration = duration, customData = custom }
      return true
    end,
  }
end
local media = holder()
media.GetClipProperty = function(_, key) return key == "File Path" and source_path or "24" end
local function segment(start_frame)
  local item = holder()
  item.GetMediaPoolItem = function() return media end
  item.GetStart = function() return start_frame end
  item.GetEnd = function() return start_frame + 36 end
  item.GetLeftOffset = function() return 12 end
  item.GetSourceStartFrame = function() return 12 end
  return item
end
local clips = { segment(86400), segment(86640) }
local states = { video = { true, false }, subtitle = { false } }
local subtitle_items = {}
local timeline = holder()
timeline.GetSetting = function() return "24" end
timeline.GetCurrentTimecode = function() return "01:00:00:06" end
timeline.GetStartFrame = function() return 86400 end
timeline.GetTrackCount = function(_, kind) return kind == "audio" and 1 or #states[kind] end
timeline.GetItemListInTrack = function(_, kind, index)
  if kind == "audio" then return clips end
  return subtitle_items[index] or {}
end
timeline.GetCurrentVideoItem = function() error("Video selection should never be used") end
timeline.AddTrack = function(_, kind) table.insert(states[kind], true); return true end
timeline.GetIsTrackEnabled = function(_, kind, index) return states[kind][index] end
timeline.SetTrackEnable = function(_, kind, index, enabled) states[kind][index] = enabled; return true end
local placement_fails = true
local pool = {
  ImportMedia = function(_, paths)
    local handle = assert(io.open(paths[1])); handle:close()
    return { {} }
  end,
  AppendToTimeline = function(_, info)
    assert(info[1].recordFrame == 86400 and info[1].startFrame == 0)
    if placement_fails then error("Simulated placement failure") end
    subtitle_items[info[1].trackIndex] = { {} }
    return { {} }
  end,
}
local project = { GetCurrentTimeline = function() return timeline end, GetMediaPool = function() return pool end }
local imports = {}
resolve = {
  GetProjectManager = function() return { GetCurrentProject = function() return project end } end,
  GetMediaStorage = function() return { AddItemListToMediaPool = function(_, path)
    local handle = assert(io.open(path)); handle:close()
    table.insert(imports, path)
    return { {} }
  end } end,
  OpenPage = function() return true end,
}

local commands = {}
io.popen = function(command)
  table.insert(commands, command)
  local output = assert(command:match("%-%-output '([^']+)'"))
  local file = assert(io.open(output, "w"))
  if command:find(" analyze ", 1, true) then
    file:write("return { duration_seconds = 2, raw_beats = {0.25, 0.75, 1.25, 1.75}, quantized_beats = {0, 0.5, 1, 1.5} }")
  else
    assert(command:find(" click-track ", 1, true))
    file:write("mock click audio")
  end
  file:close()
  return { read = function() return "" end, close = function() return true, "exit", 0 end }
end

local OpenBeat = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatCommon.lua")
timeline:AddMarker(42, "Red", "user", "", 1, "user")
timeline:AddMarker(48, "Blue", "other song", "", 1, "OpenBeat:timeline:other.wav")
for _, mode in ipairs({ "raw", "quantized" }) do
  OpenBeat.run("timeline_markers", mode)
  local count = 0
  for frame, marker in pairs(timeline.markers) do
    if marker.customData == "OpenBeat:timeline:" .. source_path then
      count = count + 1
      assert(frame < 36 or (frame >= 240 and frame < 276), "Marker outside used ranges")
    end
  end
  assert(count == 6 and timeline.markers[42].customData == "user" and timeline.markers[48])
  OpenBeat.run("clip_markers", mode)
  count = 0
  for _ in pairs(media.markers) do count = count + 1 end
  assert(count == 4)
  for _, clip in ipairs(clips) do
    count = 0
    for frame in pairs(clip.markers) do count = count + 1; assert(frame >= 0 and frame < 36) end
    assert(count == 3)
  end
  OpenBeat.run("click_track", mode)
  OpenBeat.run("subtitles", mode)
  local output = source_path:gsub("%.wav$", mode == "raw" and ".openbeat-raw.srt" or ".openbeat.srt")
  local file = assert(io.open(output)); local srt = file:read("*a"); file:close()
  assert(srt:find("00:00:00,000", 1, true) and not srt:find("01:00:", 1, true))
  assert(not srt:find("00:00:01,500 --> 00:00:10,000", 1, true))
  assert(states.video[1] == true and states.video[2] == false and states.subtitle[1] == false)
  placement_fails = false
end
assert(#commands == 8 and #imports == 2)
assert(imports[1]:find(".openbeat-raw-clicks.wav", 1, true) and imports[2]:find(".openbeat-clicks.wav", 1, true))
assert(not pcall(OpenBeat.run, "timeline_markers", "invalid"))
assert(not pcall(OpenBeat.run, "invalid", "raw"))

-- Resolve can indicate drop-frame in the setting while returning colon timecode.
timeline.GetSetting = function() return "29.97 DF" end
timeline.GetCurrentTimecode = function() return "01:00:00:06" end
timeline.GetStartFrame = function() return 107892 end
for index, clip in ipairs(clips) do
  local start_frame = 107892 + (index - 1) * 240
  clip.GetStart = function() return start_frame end
  clip.GetEnd = function() return start_frame + 36 end
end
OpenBeat.run("timeline_markers", "raw")
local count = 0
for _, marker in pairs(timeline.markers) do
  if marker.customData == "OpenBeat:timeline:" .. source_path then count = count + 1 end
end
assert(count == 4, "Drop-frame settings must reach source selection and frame conversion")
